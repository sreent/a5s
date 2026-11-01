"""Retention: how long a5s keeps what people and agents say, and the values runs handle.

A conversation, everything one person and one agent have said to each other, is kept for 12
months after the last thing either said, and then deleted: its turns and summaries, the
messages the core received and sent for it, and what waited for a digest or a batch. a5s's
own notices go 12 months after they were written, and so do the notes on how someone likes to
work, and the reminders, 12 months after they ended, as do what someone said they were
waiting on, offers nobody said yes to, the record of each day's report, and the changes agents
asked for, with their decisions, 12 months after they ended, and samples of agents' work 12
months after they were graded, or, if nobody graded them, drawn. The counts of changes go once
their 30 days are past. A change a5s left marked as being made, which someone ends by hand
(`a5s proposals`), goes 12 months after that. What a5s keeps for someone who left is archived
where it is, a day after the directory stops naming them (core/departures.py), and goes on
the same clocks, as does the record of whose archive it was. A note people ask
to forget goes at once (core/profiles.py). The ledger keeps what people and agents wrote only
by hash and length (core/ledger.py), so retention needn't touch it. The values a run was handed as handles, what it read, and the documents from
outside it read, go once the run has been over for an hour: a handle works only in its run, and nothing reads them after.

The core sweeps every hour, by the database's clock, and the ledger records what each sweep
deleted, in counts, never what was said. The ledger itself is evidence, kept as long as the
records it supports, and so are runs, which it names.
"""

from __future__ import annotations

import psycopg

KEPT = "12 months"  # after a conversation's last message [TBC: the data protection officer]
OVER = "1 hour"  # after a run closes, before its handles and what it read go
LOCK = 7_310_018  # so two sweeps don't work at once

# Where conversations' words are, and when each was said
SAID = (("turns", "at"), ("inbound", "received_at"), ("outbox", "at"), ("digest_items", "at"),
        ("urgent_held", "at"))


def sweep(conn: psycopg.Connection) -> dict[str, int]:
    """Delete what's past its time, in the caller's transaction. How many of each kind went,
    leaving out the kinds where none did."""
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

    said = " union all ".join(f"select person, agent, {at} as at from {table}"
                              for table, at in SAID)
    idle = conn.execute(
        f"select person, agent from ({said}) said where agent is not null "
        f"group by person, agent having max(at) < now() - interval '{KEPT}'").fetchall()
    if idle:  # and only what's old, should someone write again as the sweep works
        people, agents = [r["person"] for r in idle], [r["agent"] for r in idle]
        ended = "(person, agent) in (select * from unnest(%s::text[], %s::text[]))"
        for table, at in SAID:
            delete("messages" if table != "turns" else "turns",
                   f"delete from {table} where {ended} and {at} < now() - interval '{KEPT}'",
                   (people, agents))
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
    delete("departures", f"delete from departures where archived_at < now() - interval '{KEPT}'")
    return gone
