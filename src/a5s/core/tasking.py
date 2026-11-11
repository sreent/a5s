"""Tasks as people ask agents for them, and as a5s runs them (docs/phase-4.md).

Someone asks an agent, in their own chat with it, for work that takes more than one run, such
as going through a quarter's disputed invoices. The agent offers it with offer_task, and it
starts only once they say yes in a later message, with confirm_task, as a reminder does: with
the release's budget for a task, and the days it has (definitions.Tasks). It's theirs, so it
acts for them alone, and they can list and cancel it, through the agent or on their own
page (core/inbox.py), and when it needs them, have it go on with what they say.

The core works on it a slice at a time, each slice one of the agent's runs, which the
scheduler opens like any other (`kind: task`). The run is told the task, its plan, what its
earlier slices found, and the most it may spend: what's left of the task's budget, which the
model gateway holds each of its calls to (core/budgets.py). It keeps what it does with
checkpoint_task as it goes, and says what the slice came to with finish_task: done, waiting
for a person, or to go on in a later run. Each run is given what the task's earlier runs
read, with where each value came from, and opens marked if any read content from outside, so
a value its agent writes is traced to wherever it came from, whichever run read it, and
nothing an earlier run made up passes as the records' (core/provenance.py). The slice's lease
lasts as long as the run may, and what it spent is the run's own count of its tokens, so
nothing a worker says is counted. Only once it's done or waiting for them may the run write
to its owner, and then only to them; when it ends without a word from its agent, such as when
its deadline passes, a5s tells them itself, in its own words (core/tasks.py has the engine).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Person
from a5s.core import studio
from a5s.core.coretools import Call, CoreTool, Refused, one_to_one
from a5s.core.reminders import CONFIRM_WITHIN, say
from a5s.core.tasks import ENDED, OFFERED, TaskError, TaskService, TaskSpec, planned

KIND = "task"
HELD = "a-task-writes-once-it-ends"  # the policy's id when a task's run would write too soon
MOST_CHARS = 2000  # the most a task's words may be
MOST_PARTIAL = 4000  # the most of what its earlier slices found that a run is shown, in characters
SAID = ("done", "blocked", "waiting")  # what a slice may say it came to


def name(row: dict) -> str:
    return f"T-{row['number']}"


def _number(given: Any) -> int:
    try:
        return int(str(given).strip().upper().removeprefix("T-"))
    except ValueError:
        raise Refused(f"name the task, such as T-12, not {given!r}") from None


def service(url: str, clock: Any, run_minutes: int) -> TaskService:
    """The engine, as the core runs it: each slice's lease as long as its run may last."""
    tasks = TaskService(url, lease_seconds=run_minutes * 60)
    tasks.clock = clock
    return tasks


def _tasks(call: Call) -> TaskService:
    tasks = TaskService("", lease_seconds=3600)  # always in the call's own transaction
    tasks.clock = lambda: call.now
    return tasks


# What people ask for, through the agent, in their own chat with it

def offer(call: Call) -> dict:
    tasks_of = getattr(call.release, "tasks", None)
    if tasks_of is None:
        raise Refused("this agent doesn't take on long tasks")
    person = call.asker
    text = " ".join(str(call.args.get("task", "")).split())
    if not text or len(text) > MOST_CHARS:
        raise Refused(f"say what the task is, in a sentence or two, at most {MOST_CHARS:,} "
                      "characters")
    call.conn.execute(  # one offer at a time, as a reply's tool calls run together
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"task-offer/{call.run['id']}/{person.id}",))
    again = call.conn.execute(  # the same task, offered before: it waits for their yes
        "select number from tasks where owner = %s and instance_id = %s and status = %s "
        "and task = %s and asked_at > %s order by number desc limit 1",
        (person.id, call.run["id"], OFFERED, text, call.asked_at - CONFIRM_WITHIN)).fetchone()
    if again:
        return {"task": name(again), "what": text,
                "offered": "you offered this already: if they've said yes, start it with "
                           "confirm_task"}
    deadline = call.now + timedelta(days=tasks_of.days)
    task_id = _tasks(call).create(
        TaskSpec(instance=call.run["id"], owner=person.id, task=text, audience=(person.id,),
                 token_budget=tasks_of.budget_tokens, deadline=deadline),
        offered_run=call.run["run"], asked_at=call.asked_at, within=call.conn)
    carry(call.conn, task_id, call.run["run"])  # what the run that offered it had read
    studio.handled(call.conn, call.run["run"], studio.named(call.scenario, text))
    row = call.conn.execute("select number from tasks where id = %s", (task_id,)).fetchone()
    return {"task": name(row), "what": text, "has until": say(person, deadline),
            "offered": "it starts only once they say yes, in their next message: ask them"}


def confirm(call: Call) -> dict:
    person, asked = call.asker, call.asked_at
    named = _number(call.args["task"]) if call.args.get("task") else None
    row = call.conn.execute(  # one they said yes to after it was offered, not in this message
        "select id::text as id, number, deadline from tasks where owner = %s and instance_id = %s "
        "and status = %s and offered_run <> %s and asked_at < %s and asked_at > %s "
        "and (%s::bigint is null or number = %s) order by asked_at desc, number desc limit 1 "
        "for update", (person.id, call.run["id"], OFFERED, call.run["run"], asked,
                       asked - CONFIRM_WITHIN, named, named)).fetchone()
    if row is None:
        raise Refused("no task is waiting for them to say yes here. Offer it first, and start "
                      "it once they say yes in a later message")
    _tasks(call).confirm(row["id"], person.id, within=call.conn)
    return {"task": name(row), "started": True, "has until": say(person, row["deadline"]),
            "note": "a5s works on it in runs of its own, and tells them when it's done or "
                    "needs them"}


def mine(call: Call) -> dict:
    person = call.person
    rows = call.conn.execute(
        "select number, task, status, progress, plan, last_error, deadline, updated_at, "
        "asked_at from tasks where owner = %s and instance_id = %s and parent is null "
        "order by updated_at desc limit 20", (person.id, call.run["id"])).fetchall()
    studio.handled(call.conn, call.run["run"], studio.named(
        call.scenario, [r["task"] for r in rows]))
    lapsed = call.asked_at - CONFIRM_WITHIN  # an offer not said yes to by then, as for
    # confirm_task: by when the messages came
    return {"tasks": [{"task": name(r), "what": r["task"], "status": (
                           "offered, and lapsed: offer it again if they still want it"
                           if r["status"] == OFFERED and r["asked_at"]
                           and r["asked_at"] <= lapsed else r["status"]),
                       "progress": f"{round(100 * r['progress'])}%",
                       "steps done": f"{sum(s['status'] == 'completed' for s in r['plan'])} of "
                                     f"{len(r['plan'])}" if r["plan"] else None,
                       **({"why": r["last_error"]} if r["last_error"] else {}),
                       "has until": say(person, r["deadline"])} for r in rows]}


def cancel(call: Call) -> dict:
    person = call.person
    row = call.conn.execute("select id::text as id, number from tasks where owner = %s "
                            "and instance_id = %s and number = %s",
                            (person.id, call.run["id"], _number(call.args.get("task")))).fetchone()
    if row is None:
        raise Refused(f"{call.args['task']} isn't one of their tasks with you")
    try:
        _tasks(call).cancel(row["id"], person.id, within=call.conn)
    except TaskError as exc:
        raise Refused(str(exc)) from None
    return {"task": name(row), "cancelled": True}


def resume(call: Call) -> dict:
    """Go on with a task that needed its owner, with what they said it needs, which its
    next run is told, and whose values are theirs."""
    person = call.person
    row = call.conn.execute("select id::text as id, number, status, last_error from tasks "
                            "where owner = %s and instance_id = %s and number = %s for update",
                            (person.id, call.run["id"], _number(call.args.get("task")))
                            ).fetchone()
    if row is None:
        raise Refused(f"{call.args['task']} isn't one of their tasks with you")
    if row["status"] != "blocked":
        raise Refused(f"{name(row)} is {row['status']}: only a task that needs them goes on "
                      "with what they say")
    answer = " ".join(str(call.args.get("answer") or "").split())
    if not answer or len(answer) > MOST_CHARS:
        raise Refused("say what they said it needs, in a sentence or two, at most "
                      f"{MOST_CHARS:,} characters")
    try:
        _tasks(call).resume(row["id"], person.id, within=call.conn)
    except TaskError as exc:
        raise Refused(str(exc)) from None
    call.conn.execute("update tasks set answered = %s where id = %s",
                      (Jsonb({"needed": row["last_error"], "said": answer}), row["id"]))
    carry(call.conn, row["id"], call.run["run"])  # what they said, as theirs
    return {"task": name(row), "goes on": True,
            "note": "a5s works on it again in a run of its own, with what they said"}


# Their own page (core/inbox.py): every task someone asked agents for, wherever they asked

PAGE_MOST = 50  # the most tasks their page shows, the latest first


def theirs(conn: psycopg.Connection, scenario: Any, person: Person,
           now: datetime) -> list[dict]:
    """Someone's own tasks, with every agent, for their page: how each stands, what it
    waits on, and what it has spent. A task whose words name a record they may no longer
    see shows how it stands alone, never its words."""
    rows = conn.execute(
        "select t.number, t.task, t.status, t.progress, t.plan, t.last_error, t.answered, "
        "t.deadline, t.tokens, t.token_budget, t.asked_at, t.updated_at, i.definition as agent "
        "from tasks t join instances i on i.id = t.instance_id where t.owner = %s "
        "and t.parent is null order by t.updated_at desc, t.number desc limit %s",
        (person.id, PAGE_MOST)).fetchall()
    lapsed = now - CONFIRM_WITHIN  # an offer not said yes to by then
    shown = []
    for r in rows:
        about: dict[str, Any] = {
            "task": name(r), "agent": r["agent"],
            "status": "offered, and lapsed" if r["status"] == OFFERED and r["asked_at"]
                      and r["asked_at"] <= lapsed else r["status"],
            "ended": r["status"] in ENDED, "progress": round(100 * r["progress"]),
            "has until": say(person, r["deadline"]),
            "spent": f"{r['tokens']:,} of {r['token_budget']:,} tokens",
            "updated": r["updated_at"].date().isoformat()}
        words = [r["task"], r["plan"], r["last_error"], r["answered"]]
        if not all(scenario.sees(person.id, k) for k in studio.named(scenario, words)):
            shown.append({**about, "withheld": True})
            continue
        about |= {"what": r["task"], "plan": r["plan"] or []}
        if r["last_error"]:
            about["why"] = r["last_error"]
        if answered := r["answered"]:
            about |= {"needed": answered.get("needed"), "said": answered.get("said")}
        shown.append(about)
    return shown


def cancel_theirs(conn: psycopg.Connection, person: Person, task: str,
                  now: datetime) -> dict:
    """Cancel one of someone's tasks at their word, on their page, as the agent would at
    their asking. TaskError if it isn't theirs, or has ended."""
    number = task.strip().upper().removeprefix("T-")
    row = conn.execute("select id::text as id, number from tasks where owner = %s "
                       "and number = %s", (person.id, int(number))
                       ).fetchone() if number.isdigit() else None
    if row is None:
        raise TaskError(f"{task} isn't one of your tasks")
    tasks = TaskService("", lease_seconds=3600)  # in the page's own transaction
    tasks.clock = lambda: now
    tasks.cancel(row["id"], person.id, within=conn)
    return {"cancelled": name(row)}


# What a task's own run keeps, and says

def _slice(call: Call) -> tuple[str, str]:
    trigger = call.run["trigger"]
    if trigger.get("kind") != KIND or not trigger.get("lease"):
        raise Refused("only a run of a task keeps its work")
    return str(trigger["task"]), str(trigger["lease"])


def keep(call: Call) -> dict:
    task_id, lease = _slice(call)
    change = {k: call.args[k] for k in ("step", "progress", "partial", "plan") if k in call.args}
    stopped, refused = _tasks(call).kept(call.conn, task_id, lease, change)
    if refused:
        raise Refused(refused)
    if stopped:  # what it did is kept: it stops, and writes to nobody
        return {"stop": f"{stopped}: stop now, and write to nobody"}
    return {"kept": {k: v for k, v in change.items() if k != "partial"}}


def finish(call: Call) -> dict:
    task_id, _ = _slice(call)
    status = call.args.get("status")
    if status not in SAID:
        raise Refused("say it's done, blocked on a person, or waiting to go on in a later run")
    if status == "blocked" and not str(call.args.get("reason") or "").strip():
        raise Refused("say what it needs of them to go on")
    row = call.conn.execute("select owner, plan from tasks where id = %s",
                            (task_id,)).fetchone()
    if row is None:  # gone meanwhile, as an erasure takes it
        raise Refused("the task is gone: stop now, and write to nobody")
    said: dict[str, Any] = {"status": status}
    for field in ("result", "reason", "partial"):
        if call.args.get(field) is not None:
            said[field] = call.args[field]
    if "plan" in call.args:
        try:
            said["plan"] = planned(row["plan"], call.args["plan"])
        except TaskError as exc:
            raise Refused(str(exc)) from None
    call.conn.execute("update runs set task_result = %s where id = %s",
                      (Jsonb(said), call.run["run"]))
    owner = call.scenario.person(row["owner"])
    return {"noted": status,
            "next": "stop now: a5s runs it again later" if status == "waiting" else
                    f"write to {owner.name if owner else 'its owner'} now, in one short message, "
                    "what it came to, and nothing more"}


def carry(conn: psycopg.Connection, task_id: str, run: str) -> None:
    """Keep with a task what one of its runs read, with where each value came from, and
    whether it read content from outside: the run that offered it, the one its owner said
    what it needed in, and each of its slices, for its later runs to be given."""
    conn.execute("insert into task_reads (task_id, source, kind, norm, text) "
                 "select t.id, r.source, r.kind, r.norm, r.text from run_reads r "
                 "join tasks t on t.id = %s where r.run_id = %s on conflict do nothing",
                 (task_id, run))  # unless it's gone meanwhile, as an erasure takes it
    conn.execute("update tasks set read_outside = true where id = %s and not read_outside "
                 "and exists (select 1 from runs where id = %s and read_outside)",
                 (task_id, run))


def given(conn: psycopg.Connection, task_id: str, run: str) -> None:
    """Give a task's run what its earlier runs read, with where each value came from: only
    that, so what one of them wrote itself, in what it kept, stays its agent's own."""
    conn.execute("insert into run_reads (run_id, source, kind, norm, text) "
                 "select %s, source, kind, norm, text from task_reads where task_id = %s "
                 "on conflict do nothing", (run, task_id))


def _theirs(run: dict) -> bool:
    return one_to_one(run) and (run.get("trigger") or {}).get("kind") == "message"


def _sliced(run: dict) -> bool:
    return (run.get("trigger") or {}).get("kind") == KIND


_PLAN = {"type": "array", "description": "Its steps, each with its content and whether it's "
                                         "pending, in_progress or completed",
         "items": {"type": "object", "properties": {"content": {"type": "string"},
                                                    "status": {"type": "string"}}}}
_TASK = {"type": "string", "description": "Such as T-12"}

TOOLS = {t.name: t for t in (
    CoreTool("offer_task",
             "Offer to take on a long task for the person you're answering: work that takes "
             "more than one run, which a5s works on in runs of its own. It starts only once "
             "they say yes in their next message: ask them.",
             {"type": "object", "required": ["task"], "properties": {
                 "task": {"type": "string", "description": "What to do, in a sentence or two"}}},
             offer, text_fields=("task",), offered=_theirs,
             sourced=lambda result: {k: v for k, v in result.items() if k != "what"}),
    CoreTool("confirm_task",
             "Start a task you offered the person, once they've said yes to it.",
             {"type": "object", "properties": {"task": _TASK}}, confirm,
             sourced=lambda result: result, offered=_theirs),
    CoreTool("list_tasks", "The person's tasks with you, and how each stands.",
             {"type": "object", "properties": {}}, mine, offered=_theirs,
             sourced=lambda result: [  # never what its agent wrote, nor why it's blocked
                 {k: v for k, v in t.items() if k not in ("what", "why")}
                 for t in result["tasks"]]),
    CoreTool("cancel_task", "Stop one of the person's tasks, when they ask you to.",
             {"type": "object", "required": ["task"], "properties": {"task": _TASK}}, cancel,
             sourced=lambda result: result, offered=_theirs),
    CoreTool("resume_task",
             "Go on with one of the person's tasks that needed them, once they've said what it "
             "needs.",
             {"type": "object", "required": ["task", "answer"], "properties": {
                 "task": _TASK,
                 "answer": {"type": "string",
                            "description": "What they said it needs, in their words"}}},
             resume, text_fields=("answer",), sourced=lambda result: result,
             offered=_theirs),
    CoreTool("checkpoint_task",
             "Keep what you've done of the task so far, so a later run picks up from it: its "
             "step, how far it's come, what you've found, and its plan.",
             {"type": "object", "properties": {
                 "step": {"type": "integer"},
                 "progress": {"type": "number", "description": "From 0 to 1"},
                 "partial": {"description": "What you've found so far"},
                 "plan": _PLAN}},
             keep, offered=_sliced),
    CoreTool("finish_task",
             "Say what this run's work on the task came to: done, blocked on the person, or "
             "waiting to go on in a later run.",
             {"type": "object", "required": ["status"], "properties": {
                 "status": {"type": "string", "enum": list(SAID)},
                 "result": {"description": "What it came to, if it's done"},
                 "reason": {"type": "string", "description": "What it needs of them, if blocked"},
                 "partial": {"description": "What you've found so far"},
                 "plan": _PLAN}},
             finish, offered=_sliced),
)}


# A task's slices, as runs

def brief(task: dict, owner: Person | None) -> str:
    """What a task's run is told: what its owner asked for, its plan, what its earlier slices
    found, and the most it may spend."""
    who = owner.name if owner else task["owner"]
    said = [f"Work on {who}'s task, {name(task)}, which they asked you for: {task['task']}"]
    if task["plan"]:
        said.append("Its plan: " + "; ".join(f"{s['content']} ({s['status'].replace('_', ' ')})"
                                              for s in task["plan"]) + ".")
    if answered := task.get("answered"):
        said.append(f"It needed {who}: {answered.get('needed') or 'them'}. They said: "
                    f"{answered['said']}")
    if task["partial"] not in (None, [], {}, ""):
        found = str(task["partial"])
        said.append("What its earlier runs found: " + (found if len(found) <= MOST_PARTIAL
                                                       else found[:MOST_PARTIAL] + "..."))
    said.append(f"This run may spend {task['tokens_left']:,} tokens at most. Keep what you do "
                "with checkpoint_task as you go, so a later run picks up from it. A handle an "
                "earlier run was given works only in that run: look its value up again if you "
                "need it. When it's done, "
                "or you can't go on without them, say so with finish_task, and then write to "
                f"{who}, in one short message. Otherwise say it's waiting, and write to nobody: "
                "a5s runs it again later.")
    return "\n\n".join(said)


def begin(conn: psycopg.Connection, tasks: TaskService, task_id: str) -> tuple[str | None, dict]:
    """Begin a task's next slice, as its run opens: its lease and the task, or None and the
    task, ended, or None and a reason if it can't run now."""
    try:
        return tasks.begin(task_id, within=conn)
    except TaskError as exc:
        return None, {"id": task_id, "status": None, "last_error": str(exc)}


def end(conn: psycopg.Connection, tasks: TaskService, run_id: str, run: dict,
        outcome: str) -> dict | None:
    """End the slice a task's run was, as the run closes: with what it said the slice came to,
    or, if it said nothing, waiting to go on, or failed, if the run did, and what the run spent,
    counted whatever came of it, keeping what it read for the task's later runs. The task as
    it then stands, or None if the run was no slice."""
    trigger = run.get("trigger") or {}
    if trigger.get("kind") != KIND or not trigger.get("lease"):
        return None
    carry(conn, str(trigger["task"]), run_id)
    said = run.get("task_result")
    if said is None and outcome.startswith("done"):
        said = {"status": "waiting"}
    try:
        return tasks.end(str(trigger["task"]), str(trigger["lease"]), said,
                         None if said else f"its run ended as {outcome}",
                         spent=int(run.get("tokens") or 0), within=conn)
    except TaskError:  # it's gone, as an erasure takes it
        return None


def ended(task: dict | None) -> bool:
    return bool(task) and task.get("status") in (*ENDED, "blocked")


def notice(task: dict, agent: str) -> str:
    """a5s's own words to a task's owner when it ended without a word from its agent: never
    the agent's words, which only its own message carries."""
    what = f"{name(task)}, the task you asked the {agent} for"
    if task["status"] == "done":
        return f"{what}, is done. Ask the {agent} what it found."
    if task["status"] == "blocked":
        return f"{what}, needs you before it can go on. Ask the {agent} what it needs."
    if task["status"] == "cancelled":
        return f"{what}, was cancelled."
    return f"{what}, has stopped: {task.get('last_error') or 'it could not go on'}."
