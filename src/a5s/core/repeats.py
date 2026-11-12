"""Tasks people ask an agent to do again and again, such as every Monday at 09:00: repeats
(docs/phase-4.md).

Someone asks for one in their own chat with the agent, which offers it with offer_task, saying
when, and it starts only once they say yes in a later message, with confirm_task, as a task
does. At each of its times, in its owner's time zone, the core makes a task of it, with the
release's budget and days for one, and what the run that offered it had read, with where each
value came from. It makes one only once the last task it made has ended, so they never pile
up, and a time that comes round meanwhile is let go. It acts for its owner alone, who lists
and stops it through the agent or on their own page, and a person has at most MOST of them
with an agent at once. People name one by its number, such as E-3.

To change one's days, time or words, the agent offers it again as it'll be, in place of the
old one, and it takes the old one's place once its owner says yes: the old one stops then, and
the new one waits for the task the old one made last.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from a5s.contract import Person, Scenario
from a5s.core import ledger, registry, schedules
from a5s.core.tasks import ENDED, TaskError, TaskService, TaskSpec
from a5s.definitions import DAYS, Schedule

WAITS = timedelta(days=1)  # an offer waits this long for its owner's yes, then lapses

MOST = 5  # the most repeats someone may have with an agent at once, offered or going [TBC]
PREFIX = "E-"
_DAYS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
         "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


def name(row: dict) -> str:
    return f"{PREFIX}{row['number']}"


def named(given: Any) -> bool:
    """Whether someone named a repeat, such as E-3, rather than a task."""
    return str(given or "").strip().upper().startswith(PREFIX)


def number(given: Any) -> int | None:
    digits = str(given or "").strip().upper().removeprefix(PREFIX)
    return int(digits) if digits.isdigit() else None


def when(days: Any, at: Any) -> Schedule:
    """When a repeat comes round, as a release's schedules say it: days such as monday, a list
    of them, weekdays or every day, and a time, such as "09:00". ValueError if it isn't one."""
    if isinstance(days, str) and days.strip().lower() in ("every day", "daily", "day", "days"):
        days = list(DAYS)
    try:
        return Schedule(name="repeat", task="repeat", at=at or "09:00", days=days or "weekdays")
    except ValidationError:
        raise ValueError("say when it comes round: its days, such as monday, weekdays or every "
                         "day, and its time, such as \"09:00\"") from None


def said(schedule: Schedule) -> str:
    """Such as every Monday at 09:00."""
    days = [d for d in DAYS if d in schedule.days]
    which = ("every day" if days == list(DAYS) else "every weekday" if days == list(DAYS[:5])
             else "every " + " and ".join(_DAYS[d] for d in days))
    return f"{which} at {' and '.join(sorted(schedule.at))}"


def _of(row: dict) -> Schedule:
    return when(list(row["days"]), list(row["at"]))


def _record(conn: psycopg.Connection, row: dict, action: str, **args: Any) -> None:
    ledger.append(conn, {"kind": "repeat", "action": action, "repeat": str(row["id"]),
                         "instance": row["instance_id"], "acts_for": [row["owner"]],
                         "decision": "record", "args": ledger.mask(args)})


def theirs(conn: psycopg.Connection, person: Person, instance: str, wanted: Any) -> dict:
    """One of someone's repeats with an agent that's going or offered, which they named, such
    as E-3, to change. TaskError if it isn't one, or has stopped."""
    found = number(wanted)
    row = conn.execute(
        "select * from task_repeats where owner = %s and instance_id = %s and number = %s",
        (person.id, instance, found)).fetchone() if found is not None else None
    if row is None:
        raise TaskError(f"{wanted} isn't one of their repeating tasks with you")
    if row["status"] == "stopped":
        raise TaskError(f"{name(row)} has stopped: offer a new one instead")
    return row


def offer(conn: psycopg.Connection, person: Person, instance: str, run: str, asked_at: datetime,
          text: str, schedule: Schedule, instead_of: dict | None = None) -> dict:
    """Offer a repeat, which waits for its owner's yes in a later message, with what the run
    offering it has read so far: in place of `instead_of`, one of theirs, if it changes that.
    TaskError if they have as many as they may."""
    replaces = instead_of["id"] if instead_of else None
    instead = {"in place of": name(instead_of)} if instead_of else {}
    again = conn.execute(  # the same, offered before: it waits for their yes
        "select number from task_repeats where owner = %s and instance_id = %s and status = "
        "'offered' and task = %s and days = %s and at = %s and replaces is not distinct from "
        "%s and asked_at > %s order by number desc limit 1",
        (person.id, instance, text, schedule.days, schedule.at, replaces,
         asked_at - timedelta(days=1))).fetchone()
    if again:
        return {"repeat": name(again), "what": text, "when": said(schedule), **instead,
                "offered": "you offered this already: if they've said yes, start it with "
                           "confirm_task"}
    going = conn.execute("select count(*) as n from task_repeats where owner = %s and "
                         "instance_id = %s and (status = 'active' or (status = 'offered' "
                         "and asked_at > %s)) and id is distinct from %s",  # an offer that
                         (person.id, instance, asked_at - WAITS, replaces)  # lapsed, and the
                         ).fetchone()["n"]  # one it changes, make way for it
    if going >= MOST:
        raise TaskError(f"they have {MOST} repeating tasks with you already: they stop one first")
    reads = [dict(r) for r in conn.execute(
        "select source, kind, norm, text from run_reads where run_id = %s", (run,)).fetchall()]
    marked = conn.execute("select read_outside from runs where id = %s", (run,)).fetchone()
    row = conn.execute(
        "insert into task_repeats (id, instance_id, owner, task, days, at, offered_run, "
        "asked_at, reads, read_outside, replaces) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s) returning *", (str(uuid.uuid4()), instance, person.id, text, schedule.days,
                                schedule.at, run, asked_at, Jsonb(reads),
                                bool(marked and marked["read_outside"]), replaces)).fetchone()
    _record(conn, row, "offer", task=text, when=said(schedule),
            **({"instead_of": name(instead_of)} if instead_of else {}))
    return {"repeat": name(row), "what": text, "when": said(schedule), **instead,
            "offered": "it starts only once they say yes, in their next message: ask them"
                       + (f", and {name(instead_of)} stops then" if instead_of else "")}


def offered(conn: psycopg.Connection, person: Person, instance: str, run: str,
            asked_at: datetime, wanted: int | None) -> dict | None:
    """The repeat a later message of its owner's says yes to: the one named, or the latest
    offered, within the time an offer waits."""
    return conn.execute(
        "select * from task_repeats where owner = %s and instance_id = %s and status = "
        "'offered' and offered_run <> %s and asked_at < %s and asked_at > %s and "
        "(%s::bigint is null or number = %s) order by asked_at desc, number desc limit 1 "
        "for update", (person.id, instance, run, asked_at, asked_at - timedelta(days=1),
                       wanted, wanted)).fetchone()


def start(conn: psycopg.Connection, scenario: Scenario, row: dict, now: datetime) -> dict:
    """Start a repeat its owner said yes to: from its next time, not one already past. If it
    changes one of theirs, that one stops now, and this one waits for the task it made last."""
    last = schedules.latest(_of(row), schedules.zone(scenario, row["owner"]), now)
    old = conn.execute("select * from task_repeats where id = %s for update",
                       (row["replaces"],)).fetchone() if row.get("replaces") else None
    conn.execute("update task_repeats set status = 'active', last_due = %s, last_task = %s, "
                 "updated_at = %s where id = %s",
                 (last, old["last_task"] if old else None, now, row["id"]))
    _record(conn, row, "start")
    if old and old["status"] != "stopped":
        conn.execute("update task_repeats set status = 'stopped', updated_at = %s where id = %s",
                     (now, old["id"]))
        _record(conn, old, "stop", by=row["owner"], instead=name(row))
    return {"repeat": name(row), "started": True, "when": said(_of(row)),
            **({"in place of": name(old)} if old else {}),
            "note": "each time, a5s makes it a task of its own, works on it in runs of its own, "
                    "and tells them when it's done or needs them"}


def stop(conn: psycopg.Connection, person: Person, wanted: Any, now: datetime,
         instance: str | None = None) -> dict:
    """Stop one of someone's repeats, at their word: the task it made last goes on, unless
    they stop that too. TaskError if it isn't theirs, or has stopped already."""
    found = number(wanted)
    row = conn.execute(
        "select * from task_repeats where owner = %s and number = %s and (%s::text is null or "
        "instance_id = %s) for update", (person.id, found, instance, instance)
    ).fetchone() if found is not None else None
    if row is None:
        raise TaskError(f"{wanted} isn't one of their repeating tasks")
    if row["status"] == "stopped":
        raise TaskError(f"{name(row)} has stopped already")
    conn.execute("update task_repeats set status = 'stopped', updated_at = %s where id = %s",
                 (now, row["id"]))
    _record(conn, row, "stop", by=person.id)
    return {"repeat": name(row), "stopped": True,
            "note": "the task it made last, if it's still at work, goes on: stop that too if "
                    "they want it stopped"}


def listed(conn: psycopg.Connection, person: Person, instance: str | None = None) -> list[dict]:
    """Someone's repeats, with an agent or with every one, as they stand."""
    rows = conn.execute(
        "select r.*, i.definition as agent, t.number as last_number, t.status as last_status, "
        "r.status = 'offered' and r.asked_at <= now() - %s as lapsed "
        "from task_repeats r join instances i on i.id = r.instance_id left join tasks t on "
        "t.id = r.last_task where r.owner = %s and (%s::text is null or r.instance_id = %s) "
        "order by r.number desc limit 20", (WAITS, person.id, instance, instance)).fetchall()
    return [{"repeat": name(r), "agent": r["agent"], "what": r["task"], "when": said(_of(r)),
             "status": "offered, and lapsed: offer it again if they still want it"
                       if r["lapsed"] else r["status"],
             **({"last task": f"T-{r['last_number']}, {r['last_status']}"}
                if r["last_number"] else {})} for r in rows]


def due(conn: psycopg.Connection, scenario: Scenario, definitions: dict[str, Any],
        tasks: TaskService, now: datetime) -> list[str]:
    """Make a task of each repeat whose time has come, once the last one it made has ended:
    acting for its owner, with the release's budget and days for a task, and what the run
    that offered it had read. A time that comes round while its last task is still at work is
    let go. The tasks it made."""
    made = []
    for row in conn.execute(
            "select r.*, i.definition, i.status as instance_status, i.serves from task_repeats r "
            "join instances i on i.id = r.instance_id where r.status = 'active' and "
            "i.status <> 'suspended' order by r.number for update of r skip locked").fetchall():
        owner = scenario.person(row["owner"])
        tasks_of = getattr(definitions.get(row["definition"]), "tasks", None)
        why = ("its agent was retired" if row["instance_status"] != "active"
               else "its agent takes on no tasks now" if tasks_of is None
               else "its agent no longer serves them"
               if owner is not None and not registry.serving(scenario, row["serves"], owner.id)
               else None)
        if why:  # it can't make a task again: it stops, so what it kept goes in time
            conn.execute("update task_repeats set status = 'stopped', updated_at = %s "
                         "where id = %s", (now, row["id"]))
            _record(conn, row, "stop", why=why)
            continue
        if owner is None:  # gone from the directory: archiving puts what's theirs away
            continue
        at = schedules.due_now(_of(row), schedules.zone(scenario, row["owner"]), now)
        if at is None or (row["last_due"] and at <= row["last_due"]):
            continue
        last = conn.execute("select status from tasks where id = %s",
                            (row["last_task"],)).fetchone() if row["last_task"] else None
        if last and last["status"] not in ENDED:  # it isn't done with the last one yet
            conn.execute("update task_repeats set last_due = %s, updated_at = %s where id = %s",
                         (at, now, row["id"]))
            _record(conn, row, "skip", due=at.isoformat(), why="its last task is still at work")
            continue
        task_id = tasks.create(TaskSpec(
            instance=row["instance_id"], owner=row["owner"], task=row["task"],
            audience=(row["owner"],), token_budget=tasks_of.budget_tokens,
            deadline=now + timedelta(days=tasks_of.days)), within=conn)
        conn.execute("update tasks set repeat = %s, read_outside = %s where id = %s",
                     (row["id"], row["read_outside"], task_id))
        for read in row["reads"] or []:  # what the run that offered it had read, as it read it
            conn.execute("insert into task_reads (task_id, source, kind, norm, text) values "
                         "(%s, %s, %s, %s, %s) on conflict do nothing",
                         (task_id, read["source"], read["kind"], read["norm"], read["text"]))
        conn.execute("update task_repeats set last_due = %s, last_task = %s, updated_at = %s "
                     "where id = %s", (at, task_id, now, row["id"]))
        _record(conn, row, "make", due=at.isoformat(), task=task_id)
        made.append(task_id)
    return made
