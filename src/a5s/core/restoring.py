"""Restoring a5s's database from a backup (docs/runbooks.md#restoring-from-a-backup; round 15,
D1).

A database restored from a backup lacks what a5s did since: its ledger stops where the backup
was taken, though the ledger's locked copies go on, and what it sent since looks unsent. So
a5s's copier copies nothing more while the copies hold entries the ledger lacks, rather than
fork them for good (core/anchor.py), and a core that reads the copies won't start. `a5s
restore`, run as the core before any part of a5s starts, then:

- puts back into the ledger the entries its copies hold beyond it, each as its copy has it and
  chained as the copies chain it, from the copies the copier marked alone, so the trail of what
  agents did since the backup is whole and the copier goes on from it. The ledger takes each as
  the core's, since the copies don't say which part wrote it: the restore's own entry names
  them;
- takes as answered each message, and as worked on each event, whose run opened since the
  backup, as those entries say, and as fired each schedule that fired, so no agent answers or
  acts on one again, nor makes again a change it made;
- erases again each person an erasure since the backup erased, whom the backup brings back:
  the officer asked for it then, and it holds. It keeps nothing of theirs, not even where a5s
  writes to them first, which comes back once they write. An archive's erasure, by a name a
  later archive doesn't take, or one whose person a run looks at work for, is listed for the
  officer to ask for again;
- holds what a5s was to send through a chat, which may have gone already: it waits in each
  person's local inbox instead, saying so, so nobody hears anything twice;
- starts each mailbox afresh from now, as at its first look, so mail read since the backup
  starts no run again: mail that came since is for the team to look through in the mailbox;
- and says so in the ledger.

What the database held beyond the ledger, such as runs, held changes and conversations since
the backup, is gone with it: the runbook says what to look through.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from a5s import db
from a5s.core import anchor, departures, erasure, ledger
from a5s.core.stores import Store

HELD = "held after a restore from a backup: it may have gone already"


def restore(conn: db.Connection, store: Store) -> dict[str, Any]:
    """Restore what a5s keeps after its database was restored from a backup, in the caller's
    transaction: how many entries it put back, through which, how many messages, events and
    schedules it took as done, whom it erased again and whom the officer must, how many sends
    it held, and how many mailboxes start afresh."""
    rows = anchor.beyond(conn, store)
    for row in rows:
        conn.execute("insert into ledger (seq, entry, prev_hash, hash) values (%s, %s, %s, %s)",
                     (row["seq"], row["entry"], bytes.fromhex(row["prev_hash"]),
                      bytes.fromhex(row["hash"])))
    entries = [json.loads(r["entry"]) for r in rows]
    done = {"put_back": len(rows), "through": rows[-1]["seq"] if rows else None,
            **_done(conn, entries), **_erased(conn, entries)}
    done["held"] = conn.execute(
        "update outbox set channel = 'local', inbound_id = null, retry_at = null, problem = %s "
        "where delivered_at is null and channel <> 'local'", (HELD,)).rowcount
    done["mailboxes"] = conn.execute("delete from mail_state").rowcount
    ledger.append(conn, {"kind": "restore", "action": "restore", "run": None, "instance": None,
                         "acts_for": [], "decision": "record", "args": done})
    return done


def _done(conn: db.Connection, entries: list[dict]) -> dict[str, int]:
    """Take as done what the runs that opened since the backup were for, as their entries say:
    each message answered, each event worked on, and each schedule fired, as when they opened."""
    answered = taken = fired = 0
    for entry in entries:
        args = entry.get("args") or {}
        if (entry.get("kind"), entry.get("action")) != ("run", "open"):
            continue
        at = datetime.fromisoformat(entry["at"])
        if args.get("inbound"):  # taken as its run opened, whatever came of it
            answered += conn.execute(
                "update inbound set answered_at = %s where id = %s::uuid and answered_at is null",
                (at, args["inbound"])).rowcount
        elif args.get("event") and entry.get("decision") == "allow":
            taken += conn.execute(
                "update events set taken_at = %s, instance_id = %s, run_id = %s::uuid, "
                "outcome = 'run' where id = %s::uuid and taken_at is null",
                (at, entry.get("instance"), entry.get("run"), args["event"])).rowcount
        elif args.get("trigger") == "schedule" and args.get("due") and entry.get("instance"):
            fired += conn.execute(
                "insert into schedule_fires (instance_id, schedule, due_at, fired_at, run_id, "
                "outcome) select %s, %s, %s, %s, %s::uuid, %s where exists (select 1 from "
                "instances where id = %s) on conflict do nothing",
                (entry["instance"], args["schedule"], datetime.fromisoformat(args["due"]), at,
                 entry.get("run"), "; ".join(entry.get("reasons") or []) or "run",
                 entry["instance"])).rowcount
    return {"answered": answered, "worked_on": taken, "fired": fired}


def _erased(conn: db.Connection, entries: list[dict]) -> dict[str, Any]:
    """Erase again each person an erasure since the backup erased, as the entries say, as the
    officer asked then (core/erasure.py), keeping nothing of theirs, as for someone who has
    left: how many, and whom the officer must ask for again."""
    again, left, now = 0, [], datetime.now(UTC)
    for entry in entries:
        person = (entry.get("args") or {}).get("person")
        if (entry.get("kind"), entry.get("action")) != ("admin", "erase") or not person:
            continue
        if person.startswith(departures.FORMER):  # a later archive takes another name
            left.append(person)
            continue
        try:
            erasure.erase(conn, person, now)
        except erasure.Busy:  # a run the backup kept open, which the sweep will close
            left.append(person)
            continue
        again += 1
    return {"erased_again": again, "erase_again": left}


def told(done: dict[str, Any]) -> str:
    """What `a5s restore` did, in words."""
    back = (f"Put back {done['put_back']} entries of the ledger from its copies, through "
            f"{done['through']}." if done["put_back"] else
            "The ledger's copies hold nothing it lacks.")
    return (f"{back} Took {done['answered']} messages as answered, {done['worked_on']} events "
            f"as worked on and {done['fired']} schedules as fired, as their runs since the "
            f"backup were. Erased {done['erased_again']} people again, as erasures since the "
            "backup had." + (f" Ask the data protection officer to ask again to erase "
                             f"{', '.join(done['erase_again'])}, which a5s can't erase again "
                             "now." if done["erase_again"] else "") +
            f" Held {done['held']} messages a5s was to send, which wait in each person's local "
            f"inbox. {done['mailboxes']} mailboxes start afresh from now. Look through what the "
            "runbook lists before you start a5s (docs/runbooks.md#restoring-from-a-backup).")
