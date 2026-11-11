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
from a5s.core import repeats, studio
from a5s.core.coretools import Call, CoreTool, Refused, one_to_one
from a5s.core.reminders import CONFIRM_WITHIN, say
from a5s.core.tasks import (
    ENDED,
    MAX_CHILDREN,
    OFFERED,
    TaskError,
    TaskService,
    TaskSpec,
    planned,
)

KIND = "task"
HELD = "a-task-writes-once-it-ends"  # the policy's id when a task's run would write too soon
MOST_CHARS = 2000  # the most a task's words may be
MOST_PARTIAL = 4000  # the most of what its earlier slices found that a run is shown, in characters
SAID = ("done", "blocked", "waiting")  # what a slice may say it came to
LEAST_PART = 5_000  # the fewest tokens a part of a task may have to spend [TBC]


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
    instead = call.args.get("instead_of")
    if call.args.get("days") or call.args.get("at") or instead:  # again and again: a repeat
        try:  # in place of one of theirs, to change it: as that one comes round, unless said
            old = repeats.theirs(call.conn, person, call.run["id"], instead) if instead else None
            found = repeats.offer(call.conn, person, call.run["id"], call.run["run"],
                                  call.asked_at, text, repeats.when(
                                      call.args.get("days") or (old and list(old["days"])),
                                      call.args.get("at") or (old and list(old["at"]))),
                                  instead_of=old)
        except (ValueError, TaskError) as exc:
            raise Refused(str(exc)) from None
        studio.handled(call.conn, call.run["run"], studio.named(call.scenario, text))
        return found
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
    person, asked, wanted = call.asker, call.asked_at, call.args.get("task")
    repeat = None if wanted and not repeats.named(wanted) else repeats.offered(
        call.conn, person, call.run["id"], call.run["run"], asked, repeats.number(wanted))
    named = _number(wanted) if wanted and not repeats.named(wanted) else None
    row = None if repeats.named(wanted) else call.conn.execute(  # one they said yes to
        # after it was offered, not in this message
        "select id::text as id, number, deadline, asked_at from tasks where owner = %s and "
        "instance_id = %s "
        "and status = %s and offered_run <> %s and asked_at < %s and asked_at > %s "
        "and (%s::bigint is null or number = %s) order by asked_at desc, number desc limit 1 "
        "for update", (person.id, call.run["id"], OFFERED, call.run["run"], asked,
                       asked - CONFIRM_WITHIN, named, named)).fetchone()
    if repeat and (row is None or repeat["asked_at"] >= row["asked_at"]):  # the later
        return repeats.start(call.conn, call.scenario, repeat, call.now)  # offered of the two
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
        "asked_at, (select count(*) from tasks c where c.parent = t.id) as parts, "
        "(select count(*) from tasks c where c.parent = t.id and c.status = 'done') as done "
        "from tasks t where owner = %s and instance_id = %s and parent is null "
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
                       **({"parts done": f"{r['done']} of {r['parts']}"} if r["parts"] else {}),
                       **({"why": r["last_error"]} if r["last_error"] else {}),
                       "has until": say(person, r["deadline"])} for r in rows],
            **({"repeats": found} if (found := repeats.listed(call.conn, person,
                                                              call.run["id"])) else {})}


def cancel(call: Call) -> dict:
    person = call.person
    if repeats.named(call.args.get("task")):  # a repeat stops: its last task goes on
        try:
            return repeats.stop(call.conn, person, call.args.get("task"), call.now,
                                call.run["id"])
        except TaskError as exc:
            raise Refused(str(exc)) from None
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
        "t.deadline, t.tokens, t.token_budget, t.asked_at, t.updated_at, i.definition as agent, "
        "(select count(*) from tasks c where c.parent = t.id) as parts, "
        "(select count(*) from tasks c where c.parent = t.id and c.status = 'done') as done "
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
            "updated": r["updated_at"].date().isoformat(),
            **({"parts": f"{r['done']} of {r['parts']} done"} if r["parts"] else {})}
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
    if repeats.named(task):  # a repeat stops, at their word
        return {"stopped": repeats.stop(conn, person, task, now)["repeat"]}
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
    row = call.conn.execute("select owner, plan, parent from tasks where id = %s",
                            (task_id,)).fetchone()
    if row is None:  # gone meanwhile, as an erasure takes it
        raise Refused("the task is gone: stop now, and write to nobody")
    if status == "blocked" and row["parent"]:
        raise Refused("a part of a task can't wait for its owner: say what it found, as "
                      "done, and the task it's part of asks them what it needs")
    if status == "done" and _open_parts(call.conn, task_id):
        raise Refused("its parts are still at work: say it's waiting, and a5s runs it again "
                      "once they're done, with what they found")
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
    if row["parent"]:  # what it found goes to the task it's part of, never to anyone
        return {"noted": status, "next": "stop now, and write to nobody: the task it's "
                                          "part of goes on with what it found"}
    return {"noted": status,
            "next": "stop now: a5s runs it again later" if status == "waiting" else
                    f"write to {owner.name if owner else 'its owner'} now, in one short message, "
                    "what it came to, and nothing more"}


def _open_parts(conn: psycopg.Connection, task_id: str) -> int:
    return conn.execute("select count(*) as n from tasks where parent = %s and status not in "
                        "('done', 'cancelled', 'failed')", (task_id,)).fetchone()["n"]


def split(call: Call) -> dict:
    """Split a task's work into parts, each a task of its own, which a5s works on in runs
    of their own, at once if there's room: each with an equal share of what the task has
    left, keeping one share for its own later runs, and its deadline. The task waits while
    they're at work, and goes on once they've ended, told what each came to."""
    task_id, _ = _slice(call)
    parts = call.args.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_CHILDREN:
        raise Refused(f"name from 1 to {MAX_CHILDREN} parts, each what to do in a sentence or two")
    texts = [" ".join(str(p.get("task", "") if isinstance(p, dict) else p).split())
             for p in parts]
    if any(not t or len(t) > MOST_CHARS for t in texts):
        raise Refused(f"say what each part is, in a sentence or two, at most {MOST_CHARS:,} "
                      "characters")
    row = call.conn.execute("select * from tasks where id = %s for update",
                            (task_id,)).fetchone()
    if row is None:
        raise Refused("the task is gone: stop now, and write to nobody")
    given_out = call.conn.execute("select coalesce(sum(token_budget), 0) as n from tasks "
                                  "where parent = %s", (task_id,)).fetchone()["n"]
    left = min(row["token_budget"] - row["tokens"] - given_out,
               TaskService._tree_left(call.conn, row)) - int(call.run.get("tokens") or 0)
    share = left // (len(texts) + 1)  # and one kept, for this task's own later runs
    if share < LEAST_PART:
        raise Refused(f"what the task has left, {max(left, 0):,} tokens, is too little to split "
                      f"{len(texts)} ways: split it fewer ways, or go on with it whole")
    carry(call.conn, task_id, call.run["run"])  # what this run read, for its parts too
    tasks, made = _tasks(call), []
    try:
        for text in texts:
            made.append(tasks.create(TaskSpec(
                instance=row["instance_id"], owner=row["owner"], task=text,
                audience=tuple(row["audience"]), token_budget=share, deadline=row["deadline"],
                parent=task_id), within=call.conn))
    except TaskError as exc:
        raise Refused(str(exc)) from None
    named = call.conn.execute("select number from tasks where id = any(%s::uuid[]) "
                              "order by number", (made,)).fetchall()
    return {"parts": [name(r) for r in named], "each may spend": share,
            "next": "say it's waiting, with finish_task, and write to nobody: a5s works on "
                    "each part in runs of its own, and runs this task again once they're "
                    "done, with what they found"}


def parts(conn: psycopg.Connection, task_id: str) -> list[dict]:
    """A task's parts, each with what it came to, for its own later runs."""
    return conn.execute("select number, task, status, result, last_error from tasks "
                        "where parent = %s order by number", (task_id,)).fetchall()


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
    """Give a task's run what its earlier runs read, and those of the tasks it's part of or
    split into, with where each value came from: only that, so what one of them wrote
    itself, in what it kept, stays its agent's own."""
    conn.execute("insert into run_reads (run_id, source, kind, norm, text) "
                 "select %s, r.source, r.kind, r.norm, r.text from task_reads r "
                 "join tasks t on t.id = r.task_id where t.root = "
                 "(select root from tasks where id = %s) on conflict do nothing", (run, task_id))


def marked(conn: psycopg.Connection, task: dict) -> bool:
    """Whether a task's run opens marked: whether any run of it, or of the tasks it's part of
    or split into, read content from outside."""
    return bool(conn.execute("select 1 from tasks where root = %s and read_outside limit 1",
                             (task["root"],)).fetchone())


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
             "they say yes in their next message: ask them. To change a repeating one, offer "
             "it as it'll be, instead_of the old one.",
             {"type": "object", "required": ["task"], "properties": {
                 "task": {"type": "string", "description": "What to do, in a sentence or two"},
                 "days": {"description": "Only if they want it done again and again: its days, "
                                         "such as monday, a list of them, weekdays or every day"},
                 "at": {"type": "string",
                        "description": "And its time, in their time zone, such as 09:00"},
                 "instead_of": {"type": "string",
                                "description": "Only to change one of their repeating tasks, "
                                               "such as E-3: the one this takes the place of "
                                               "once they say yes. Say its task, and any days "
                                               "or time that change"}}},
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
    CoreTool("cancel_task", "Stop one of the person's tasks, or a task they asked to repeat, "
             "such as E-3, when they ask you to.",
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
    CoreTool("split_task",
             "Split the task's work into parts that can be done apart, each a task of its own "
             "that a5s works on in runs of its own. Then say it's waiting: a5s runs it again "
             "once they're done, with what each found.",
             {"type": "object", "required": ["parts"], "properties": {
                 "parts": {"type": "array", "items": {
                     "type": "object", "required": ["task"], "properties": {
                         "task": {"type": "string",
                                  "description": "What the part is, in a sentence or two"}}}}}},
             split, text_fields=(), offered=_sliced),
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

def brief(task: dict, owner: Person | None, done: list[dict] | None = None,
          whole: dict | None = None, repeat: dict | None = None) -> str:
    """What a task's run is told: what its owner asked for, or for a part, the task it's
    part of; its plan; what its earlier slices found, and its parts; and the most it may
    spend."""
    who = owner.name if owner else task["owner"]
    said = [f"Work on {name(task)}, a part of {who}'s task {name(whole)}, which is to "
            f"{whole['task']}. This part is to {task['task']}" if whole else
            f"Work on {who}'s task, {name(task)}, which they asked you for: {task['task']}"]
    if repeat:
        again = repeats.said(repeats.when(list(repeat["days"]), list(repeat["at"])))
        said.append(f"It's one of the times they asked for it, {again} ({repeats.name(repeat)}).")
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
    if done:  # what its parts came to, each in runs of its own
        most = MOST_PARTIAL // len(done)
        said.append("Its parts: " + "; ".join(
            f"{name(p)}, to {p['task']}: {p['status']}"
            + (f", and found {_cut(p['result'], most)}" if p["result"] is not None else "")
            + (f", as {p['last_error']}" if p["last_error"] else "") for p in done) + ".")
    said.append(f"This run may spend {task['tokens_left']:,} tokens at most. Keep what you do "
                "with checkpoint_task as you go, so a later run picks up from it. A handle an "
                "earlier run was given works only in that run: look its value up again if you "
                "need it. If it's work in parts that can be done apart, split it with "
                "split_task, and say it's waiting.")
    said.append("When this part is done, say what it found with finish_task, as its result, "
                "and write to nobody: the task it's part of goes on with it. Otherwise say "
                "it's waiting: a5s runs it again later." if whole else
                "When it's done, or you can't go on without them, say so with finish_task, "
                f"and then write to {who}, in one short message. Otherwise say it's waiting, "
                "and write to nobody: a5s runs it again later.")
    return "\n\n".join(said)


def _cut(found: Any, most: int) -> str:
    text = found if isinstance(found, str) else str(found)
    return text if len(text) <= most else text[:most] + "..."


def repeat_of(conn: psycopg.Connection, task: dict) -> dict | None:
    """The repeat that made a task, or None."""
    return conn.execute("select number, days, at from task_repeats where id = %s",
                        (task["repeat"],)).fetchone() if task.get("repeat") else None


def whole(conn: psycopg.Connection, task: dict) -> dict | None:
    """The task a part is part of, or None for a task someone asked for."""
    return conn.execute("select number, task from tasks where id = %s", (task["parent"],)
                        ).fetchone() if task.get("parent") else None


def held(conn: psycopg.Connection, run: dict) -> str | None:
    """Why a task's run may not write to its owner now, if it may not: a part of a task
    writes to nobody, and a task's own run only once it has said it's done or needs them."""
    found = conn.execute("select r.task_result ->> 'status' as said, t.parent from runs r "
                         "left join tasks t on t.id = (r.trigger ->> 'task')::uuid "
                         "where r.id = %s", (run["run"],)).fetchone()
    if found and found["parent"]:
        return "a part of a task writes to nobody: the task it's part of tells its owner"
    if not found or found["said"] not in ("done", "blocked"):
        return ("a task's run writes to its owner only once it's done or needs them, and "
                "has said so with finish_task")
    return None


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
