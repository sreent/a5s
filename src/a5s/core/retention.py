"""Retention: how long a5s keeps what people and agents say, and the values runs handle.

A conversation, everything one person and one agent have said to each other, is kept for 12
months after the last thing either said, and then deleted: its turns and summaries, the messages
the core received and sent for it, and what waited for a digest or a batch. a5s's own notices go
12 months after they were written, and so do the notes on how someone likes to work, and the
reminders, 12 months after they ended, as do what someone said they were waiting on, offers
nobody said yes to, the record of each day's report, and the changes agents asked for, with
their decisions, 12 months after they ended, and samples of agents' work 12 months after they
were graded, or, if nobody graded them, drawn. A task, with its children, goes 12 months after
the last of them ended, or passed its deadline. The counts of changes go once their 30 days are
past, and what someone owed goes 12 months after the records stopped owing it, or, in a scenario
the deployment no longer runs, after it last changed. Each person's use of a day's budget, and
the log of their digests, go once the day's past, by the core's clock, which stamps them. A
change a5s left marked as being made, which someone ends by hand (`a5s proposals`), goes 12
months after that. What a5s keeps for someone who left is archived where it is, a day after the
directory stops naming them (core/departures.py), and goes on the same clocks. The chats a5s
wrote to them in go 12 months after, and the record of whose archive it was once nothing is left
under its name. A note people ask to forget goes at once (core/profiles.py). The ledger keeps
what people and agents wrote only by hash and length (core/ledger.py), so retention needn't
touch it. The values a run was handed as handles, what it read, and the documents from outside
it read, go once the run has been over for an hour: a handle works only in its run, and nothing
reads them after.

The core sweeps every hour, by the database's clock, and the ledger records what each sweep
deleted, in counts, never what was said. The ledger itself is evidence, kept as long as the
records it supports, and so are runs, which it names.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import psycopg

from a5s.core import departures

KEPT = "12 months"  # after a conversation's last message [TBC: the data protection officer]
OVER = "1 hour"  # after a run closes, before its handles and what it read go
LOCK = 7_310_018  # so two sweeps don't work at once

# Where conversations' words are, and when each was said
SAID = (("turns", "at"), ("inbound", "received_at"), ("outbox", "at"), ("digest_items", "at"),
        ("urgent_held", "at"))
# Whose conversation each is: a person's own, or a group chat's (core/groups.py), whose
# messages are kept under whoever sent them, and its answers under whoever asked
WHOSE = {"inbound": "coalesce(conversation, person)",
         "outbox": "coalesce((select conversation from inbound i where i.id = outbox.inbound_id), "
                   "person)"}


def sweep(conn: psycopg.Connection, now: datetime, scenario: str) -> dict[str, int]:
    """Delete what's past its time, in the caller's transaction, with `now` the core's clock,
    which stamps a day's use and the digest log, and `scenario` the scenario it runs. How many
    of each kind went, leaving out the kinds where none did."""
    if not conn.execute("select pg_try_advisory_xact_lock(%s) as got", (LOCK,)).fetchone()["got"]:
        return {}  # another sweep is at work
    gone: dict[str, int] = {}

    def delete(kind: str, sql: str, params: tuple = ()) -> None:
        if count := conn.execute(sql, params).rowcount:
            gone[kind] = gone.get(kind, 0) + count

    over = f"(select id from runs where closed_at < now() - interval '{OVER}')"
    delete("handles", f"delete from run_handles where run_id in {over}")
    delete("reads", f"delete from run_reads where run_id in {over}")
    delete("documents", f"delete from run_documents where run_id in {over}")

    said = " union all ".join(f"select {WHOSE.get(table, 'person')} as person, agent, {at} as at "
                              f"from {table}" for table, at in SAID)
    idle = conn.execute(
        f"select person, agent from ({said}) said where agent is not null "
        f"group by person, agent having max(at) < now() - interval '{KEPT}'").fetchall()
    if idle:  # and only what's old, should someone write again as the sweep works
        people, agents = [r["person"] for r in idle], [r["agent"] for r in idle]
        for table, at in sorted(SAID, key=lambda t: t[0] != "outbox"):  # answers before the
            ended = (f"({WHOSE.get(table, 'person')}, agent) in "  # messages they answer
                     "(select * from unnest(%s::text[], %s::text[]))")
            delete("messages" if table != "turns" else "turns",
                   f"delete from {table} where {ended} and {at} < now() - interval '{KEPT}'",
                   (people, agents))
        ended = "(person, agent) in (select * from unnest(%s::text[], %s::text[]))"
        delete("summaries", f"delete from summaries where {ended} "
                            f"and updated_at < now() - interval '{KEPT}'", (people, agents))
    for table, at in SAID[2:]:  # a5s's own notices, about no agent
        delete("messages", f"delete from {table} where agent is null "
                           f"and {at} < now() - interval '{KEPT}'")
    delete("notes", f"delete from profile_notes where ended_at < now() - interval '{KEPT}'")
    delete("notes", "delete from profile_notes where confirmed_at is null and ended_at is null "
                    f"and offered_at < now() - interval '{KEPT}'")  # offers nobody said yes to
    delete("waiting", "update obligations set waiting_on = null where waiting_on is not null "
                      f"and waiting_noted_at < now() - interval '{KEPT}'")  # in their words
    delete("reports", f"delete from report_fires where fired_at < now() - interval '{KEPT}'")
    delete("reminders", "delete from reminders where greatest(reminded_at, cancelled_at, "
                        "case when confirmed_at is null then offered_at end) "
                        f"< now() - interval '{KEPT}'")
    delete("counts", "delete from urgent_sent where day < (now() - interval '2 days')::date")
    ended_changes = f"select digest from proposals where ended_at < now() - interval '{KEPT}'"
    delete("decisions", f"delete from proposal_decisions where digest in ({ended_changes})")
    delete("changes", f"delete from proposals where ended_at < now() - interval '{KEPT}'")
    delete("samples", f"delete from samples where graded_at < now() - interval '{KEPT}'")
    delete("samples", "delete from samples where grade is null "
                      f"and drawn_at < now() - interval '{KEPT}'")  # nobody graded them
    delete("counts", "delete from action_counts where at < now() - interval '31 days'")
    delete("chats", "delete from chats where person in (select archived_as from departures "
                    f"where archived_at < now() - interval '{KEPT}')")  # an archive's, with it
    held = " or ".join([f"exists (select 1 from {table} x where x.person = d.archived_as)"
                        for table in departures.KEPT]
                       + ["exists (select 1 from turns x where x.speaker = d.archived_as)",
                          "exists (select 1 from tasks x where x.owner = d.archived_as)"])
    delete("departures", "delete from departures d where archived_at < now() - interval "  # once
           f"'{KEPT}' and not ({held})")  # nothing's left under the archive's name, such as in a
    # group chat, whose conversation goes by its own last message
    delete("questions", f"delete from questions where asked_at < now() - interval '{KEPT}'")
    done = (f"(status in ('done', 'cancelled', 'failed') and updated_at < now() - interval "
            f"'{KEPT}') or deadline < now() - interval '{KEPT}'")  # it can't run past its deadline
    delete("tasks", "delete from tasks where root in (select root from tasks group by root "
                    f"having bool_and({done}))")  # a task with its children, all ended long ago
    delete("obligations", "delete from obligations where done_at < now() - interval "
                          f"'{KEPT}'")  # with what the records called it, and whose it was
    delete("obligations", "delete from obligations where scenario <> %s and updated_at < "  # a
           f"now() - interval '{KEPT}'", (scenario,))  # scenario it no longer runs: nothing
    # syncs what it owed. Each person's day: only today's is asked after, in any time zone
    delete("days", "delete from spend where day < %s", ((now - timedelta(days=2)).date(),))
    delete("days", "delete from digests where due_at < %s", (now - timedelta(days=3),))
    delete("requests", "delete from officer_requests where asked_at < now() - interval "
                       "'1 day'")  # the officer's, carried out or not (core/officer.py)
    return gone
