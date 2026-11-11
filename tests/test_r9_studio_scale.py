"""Round 9 of the critique: the studio's queries on a ledger and a runs table of a real size,
which both only grow, and paging by where the last page ended (core/studio.py,
a5s/client.py; docs/critique.md, round 9)."""

from __future__ import annotations

import json
import time
import uuid

from a5s import db
from a5s.client import Client
from conftest import SERVICE_TOKEN

OTHER_RUNS = 200_000  # entries of other runs: a busy pilot's year is more


def seed_ledger(admin: str, first: int, count: int, entry_sql: str) -> None:
    """Rows straight into the ledger, after the chain, as many as asked: what they say is
    entry_sql, of g, the row's number. Their hashes don't chain; nothing here verifies."""
    with db.transaction(admin) as conn:
        conn.execute(f"insert into ledger (seq, entry, prev_hash, hash) "
                     f"select g, ({entry_sql})::text, '\\x00'::bytea, '\\x00'::bytea "
                     f"from generate_series(%s::bigint, %s::bigint) g", (first, first + count - 1))
        conn.execute("analyze ledger")


def plan_of(admin: str, sql: str, params: tuple) -> dict:
    with db.transaction(admin) as conn:
        row = conn.execute("explain (analyze, format json) " + sql, params).fetchone()
    found = next(iter(row.values()))
    return (json.loads(found) if isinstance(found, str) else found)[0]["Plan"]


def nodes(plan: dict):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def answered(stack) -> str:
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's open?")
    with stack.client() as c:
        return c.get("/studio/instances/assistant-finance/runs").json()["runs"][0]["run"]


def test_a_runs_page_reads_its_own_entries_not_the_whole_ledger(stack):
    """A run's page reads the ledger by run_id, by an index, not every entry the deployment
    ever made."""
    run = answered(stack)
    seed_ledger(stack.admin, 1_000_000, OTHER_RUNS,
                "json_build_object('kind', 'tool', 'action', 'search_records', 'decision', "
                "'allow', 'run', md5(g::text), 'instance', 'assistant-finance', 'at', "
                "'2026-10-27T12:00:00+00:00', 'args', json_build_object('query', "
                "json_build_object('sha256', md5(g::text) || md5(g::text), 'chars', 7)))")
    started = time.monotonic()
    with stack.client() as c:
        assert c.get(f"/studio/runs/{run}").status_code == 200
    took = time.monotonic() - started
    plan = plan_of(stack.admin, "select entry from ledger where run_id = %s order by seq", (run,))
    removed = sum(n.get("Rows Removed by Filter", 0) * n.get("Actual Loops", 1)
                  for n in nodes(plan))
    indexed = [n for n in nodes(plan) if "run_id" in str(n.get("Index Cond", ""))]
    assert indexed and removed < 1000, (
        f"to find one run's entries it read and threw away {removed:,} others "
        f"({[n['Node Type'] for n in nodes(plan)]}, the page took {took:.2f}s)")


def test_an_instances_denials_arent_lost_behind_another_instances(stack):
    """An instance's denials are read by instance, so another instance's newer ones, however
    many, don't push them out of its dashboard."""
    with db.transaction(stack.admin) as conn:
        top = conn.execute("select coalesce(max(seq), 0) as n from ledger").fetchone()["n"]
    deny = ("json_build_object('kind', 'tool', 'action', 'change_due_date', 'decision', 'deny', "
            "'reasons', json_build_array('lasting-or-outside-effects-need-level-2'), "
            "'run', md5(g::text), 'instance', '{inst}', 'at', '2026-10-27T12:00:00+00:00')")
    seed_ledger(stack.admin, top + 1, 3, deny.format(inst="assistant-finance"))  # its own
    seed_ledger(stack.admin, top + 10, 10_000, deny.format(inst="assistant-ops"))  # newer
    with stack.client() as c:
        denied = c.get("/studio/instances/assistant-finance/measures").json()["denied"]
    assert [d["times"] for d in denied] == [3], f"assistant-finance's 3 denials show as {denied}"


def seed_runs(admin: str, n: int, at: str | None = None) -> None:
    """n runs of assistant-finance, a second apart, or all opened at `at`."""
    with db.transaction(admin) as conn:
        for i in range(n):
            conn.execute(
                "insert into runs (id, instance_id, token_hash, trigger, acts_for, opened_at, "
                "closed_at, outcome, expires_at) values (%s, 'assistant-finance', %s, "
                "'{\"kind\": \"schedule\"}', '{}', coalesce(%s::timestamptz, "
                "'2026-10-27T00:00:00+00:00'::timestamptz + make_interval(secs => %s)), "
                "now(), 'done', now())",
                (str(uuid.uuid4()), uuid.uuid4().bytes, at, i))


def test_paging_through_every_run_gives_every_run(stack):
    """Client.each_run walks until the core says there are no more, whatever the page's size,
    though the core gives 200 at most."""
    seed_runs(stack.admin, 250)
    with Client(stack.url, SERVICE_TOKEN) as core:
        every = list(core.each_run("assistant-finance", page=500))
    assert len(every) == 250, f"{len(every)} of 250 runs"


def test_paging_doesnt_skip_runs_opened_at_the_same_moment(stack):
    """Pages go by when a run opened and its id, so runs opened at the same moment are each on
    one page."""
    seed_runs(stack.admin, 3, at="2026-10-27T09:00:00+00:00")
    with Client(stack.url, SERVICE_TOKEN) as core:
        every = list(core.each_run("assistant-finance", page=2))
    assert len({r["run"] for r in every}) == 3, f"{len(every)} of 3 runs"



def test_paging_from_where_no_page_ended_is_refused(stack, approving, provider):
    from test_studio_pages import signed_in
    api = signed_in(approving, provider)
    with stack.client() as c:
        for bad in ("yesterday", "2026-10-27T09:00:00+00:00|not-a-run"):
            path = f"/studio/instances/assistant-finance/runs?before={bad}"
            assert c.get(path).status_code == 400, bad
            assert api(f"/studio/api{path.removeprefix('/studio')}", "ana").status_code == 400
