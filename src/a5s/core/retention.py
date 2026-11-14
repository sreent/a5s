"""Retention: how long a5s keeps what people and agents say, and the values runs handle.

How long is the data protection officer's to choose: `kept_for`, in the signed settings
(docs/data-protection.md). A conversation, everything one person and one agent have said to
each other, is kept that long after the last thing either said, and then deleted: its turns and
summaries, the messages the core received and sent for it, and what waited for a digest or a
batch. a5s's own notices go that long after they were written, and so do the notes on how
someone likes to work, and the reminders, that long after they ended, as do what someone said
they were waiting on, offers nobody said yes to, the record of each day's report, and the
changes agents asked for, with their decisions, that long after they ended, and samples of
agents' work that long after they were graded, or, if nobody graded them, drawn. A task, with
its children, goes that long after the last of them ended, or passed its deadline. The counts
of changes go once their 30 days are past, and what someone owed goes that long after the
records stopped owing it, or, in a scenario the deployment no longer runs, after it last
changed. Each person's use of a day's budget, and the log of their digests, go once the day's
past, by the core's clock, which stamps them. A change a5s left marked as being made, which
someone ends by hand (`a5s proposals`), goes that long after that. What a5s keeps for someone
who left is archived where it is, a day after the directory stops naming them
(core/departures.py), and goes on the same clocks. The chats a5s wrote to them in go that long
after, and the record of whose archive it was once nothing is left under its name. A note
people ask to forget goes at once (core/profiles.py). The ledger keeps what people and agents
wrote only by hash and length (core/ledger.py), so retention needn't touch it. The values a run
was handed as handles, what it read, and the documents from outside it read, go once the run
has been over for an hour: a handle works only in its run, and nothing reads them after.

The core sweeps every hour, by the database's clock, and the ledger records what each sweep
deleted, in counts, never what was said. The period goes to Postgres as a value, never as part
of the SQL. The ledger itself is evidence, kept as long as the records it supports, and so are
runs, which it names.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Final, LiteralString

from a5s import db
from a5s.contract import DataProtection
from a5s.core import departures

KEPT = DataProtection.kept_for  # until the data protection officer chooses otherwise
HORIZON = re.compile(r"[1-9][0-9]{0,3} (hour|day|month)s?")
# Older than the period a5s keeps things for, which goes to Postgres as a value
AGO: Final = "now() - %(kept)s::interval"
OVER: Final = "1 hour"  # after a run closes, before its handles and what it read go
LOCK = 7_310_018  # so two sweeps don't work at once

# Where conversations' words are, and when each was said
SAID: Final[tuple[tuple[LiteralString, LiteralString], ...]] = (
    ("turns", "at"), ("inbound", "received_at"), ("outbox", "at"), ("digest_items", "at"),
    ("urgent_held", "at"))
# Whose conversation each is: a person's own, or a group chat's (core/groups.py), whose
# messages are kept under whoever sent them, and its answers under whoever asked
WHOSE: Final[dict[str, LiteralString]] = {
    "inbound": "coalesce(conversation, person)",
    "outbox": "coalesce((select conversation from inbound i where i.id = outbox.inbound_id), "
              "person)"}


def sweep(conn: db.Connection, now: datetime, scenario: str, kept: str = KEPT) -> dict[str, int]:
    """Delete what's past its time, in the caller's transaction, with `now` the core's clock,
    which stamps a day's use and the digest log, and `scenario` the scenario it runs. How many
    of each kind went, leaving out the kinds where none did. What's kept for KEPT is kept for
    `kept` instead: the data protection officer's choice, in the signed settings in force, or
    the sandbox's hour. It goes to Postgres as a value, never as part of the SQL."""
    if not HORIZON.fullmatch(kept):
        raise ValueError(f"{kept!r} isn't a time to keep things for, such as 12 months")
    if not conn.execute("select pg_try_advisory_xact_lock(%s) as got", (LOCK,)).fetchone()["got"]:
        return {}  # another sweep is at work
    gone: dict[str, int] = {}

    def delete(kind: str, sql: LiteralString, **given: Any) -> None:
        if count := conn.execute(sql, {"kept": kept, **given}).rowcount:
            gone[kind] = gone.get(kind, 0) + count

    over = f"(select id from runs where closed_at < now() - interval '{OVER}')"
    delete("handles", f"delete from run_handles where run_id in {over}")
    delete("reads", f"delete from run_reads where run_id in {over}")
    delete("documents", f"delete from run_documents where run_id in {over}")

    said = " union all ".join(f"select {WHOSE.get(table, 'person')} as person, agent, {at} as at "
                              f"from {table}" for table, at in SAID)
    idle = conn.execute(
        f"select person, agent from ({said}) said where agent is not null "
        f"group by person, agent having max(at) < {AGO}", {"kept": kept}).fetchall()
    if idle:  # and only what's old, should someone write again as the sweep works
        people, agents = [r["person"] for r in idle], [r["agent"] for r in idle]
        for table, at in sorted(SAID, key=lambda t: t[0] != "outbox"):  # answers before the
            ended = (f"({WHOSE.get(table, 'person')}, agent) in "  # messages they answer
                     "(select * from unnest(%(people)s::text[], %(agents)s::text[]))")
            delete("messages" if table != "turns" else "turns",
                   f"delete from {table} where {ended} and {at} < {AGO}",
                   people=people, agents=agents)
        ended = "(person, agent) in (select * from unnest(%(people)s::text[], %(agents)s::text[]))"
        delete("summaries", f"delete from summaries where {ended} and updated_at < {AGO}",
               people=people, agents=agents)
    for table, at in SAID[2:]:  # a5s's own notices, about no agent
        delete("messages", f"delete from {table} where agent is null and {at} < {AGO}")
    delete("notes", f"delete from profile_notes where ended_at < {AGO}")
    delete("notes", "delete from profile_notes where confirmed_at is null and ended_at is null "
                    f"and offered_at < {AGO}")  # offers nobody said yes to
    delete("waiting", "update obligations set waiting_on = null where waiting_on is not null "
                      f"and waiting_noted_at < {AGO}")  # in their words
    delete("reports", f"delete from report_fires where fired_at < {AGO}")
    delete("reminders", "delete from reminders where greatest(reminded_at, cancelled_at, "
                        f"case when confirmed_at is null then offered_at end) < {AGO}")
    delete("counts", "delete from urgent_sent where day < (now() - interval '2 days')::date")
    ended_changes = f"select digest from proposals where ended_at < {AGO}"
    delete("decisions", f"delete from proposal_decisions where digest in ({ended_changes})")
    delete("changes", f"delete from proposals where ended_at < {AGO}")
    delete("samples", f"delete from samples where graded_at < {AGO}")
    delete("samples", f"delete from samples where grade is null and drawn_at < {AGO}")  # nobody
    # graded them
    delete("counts", "delete from action_counts where at < now() - interval '31 days'")
    delete("chats", "delete from chats where person in (select archived_as from departures "
                    f"where archived_at < {AGO})")  # an archive's, with it
    held = " or ".join((*(f"exists (select 1 from {table} x where x.person = d.archived_as)"
                          for table in departures.KEPT),
                        "exists (select 1 from turns x where x.speaker = d.archived_as)",
                        "exists (select 1 from tasks x where x.owner = d.archived_as)"))
    delete("departures", f"delete from departures d where archived_at < {AGO} "  # once
           f"and not ({held})")  # nothing's left under the archive's name, such as in a
    # group chat, whose conversation goes by its own last message
    delete("questions", f"delete from questions where asked_at < {AGO}")
    done = (f"(status in ('done', 'cancelled', 'failed') and updated_at < {AGO}) "
            f"or deadline < {AGO}")  # it can't run past its deadline
    delete("tasks", "delete from tasks where root in (select root from tasks group by root "
                    f"having bool_and({done}))")  # a task with its children, all ended long ago
    delete("repeats", f"delete from task_repeats where (status = 'stopped' and updated_at < {AGO}) "
           f"or (status = 'offered' and asked_at < {AGO})")  # stopped, or never said yes to
    delete("obligations", f"delete from obligations where done_at < {AGO}")  # with what the
    # records called it, and whose it was
    delete("obligations", "delete from obligations where scenario <> %(scenario)s "  # a scenario
           f"and updated_at < {AGO}", scenario=scenario)  # it no longer runs: nothing syncs
    # what it owed. Each person's day: only today's is asked after, in any time zone
    delete("days", "delete from spend where day < %(day)s", day=(now - timedelta(days=2)).date())
    delete("refusals", "delete from second_factor_refusals where day < %(day)s",  # counts alone
           day=(now - timedelta(days=7)).date())
    delete("days", "delete from digests where due_at < %(due)s", due=now - timedelta(days=3))
    delete("requests", "delete from officer_requests where asked_at < now() - interval "
                       "'1 day'")  # the officer's, carried out or not (core/officer.py)
    return gone
