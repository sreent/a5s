"""Round 12 of the critique: decisions, and what a call reads (docs/critique.md, round 12, B6,
B10). A brief outage at the identity provider refuses no decision, and a decision it does refuse
is told to its decider, who decides again; and a5s reads no record for a call it would refuse
anyway: for a token nobody was given, arguments that don't fit, or more records than one change
may name. The desk's own are in tests/test_r12_desk_levels.py."""

from __future__ import annotations

import time
from dataclasses import replace

import httpx

from a5s import db
from test_levels import asked
from test_proposals import decide, held, sweep


def down(stack) -> httpx.Client:
    """The identity provider, unreachable as it restarts, as the gateway's keys are an hour old:
    by the verifier's own clock, which counts from when the machine started, however long ago."""
    verifier = stack.gateway.identity
    verifier._fetched_at = time.monotonic() - verifier.max_age - 1

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("the provider is restarting")
    was, verifier.http = verifier.http, httpx.Client(transport=httpx.MockTransport(refused))
    return was


def test_a_decision_waits_while_the_identity_provider_cant_be_reached(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    was = down(stack)
    sweep(stack)
    with db.transaction(stack.admin) as conn:
        [d] = conn.execute("select refused, seal from proposal_decisions").fetchall()
    assert d["refused"] is None and d["seal"] is None  # neither: it waits
    stack.gateway.identity.http = was  # the provider is back a moment later
    sweep(stack)
    assert held(stack)[0]["status"] == "made"


def test_a_refused_decision_is_told_and_its_decider_decides_again(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    with db.transaction(stack.admin) as conn:  # a sign-in that doesn't check out
        conn.execute("update proposal_decisions set proof = 'not.a.sign-in'")
    sweep(stack)
    with db.transaction(stack.admin) as conn:
        [d] = conn.execute("select refused from proposal_decisions").fetchall()
        told = [r["text"] for r in conn.execute(
            "select text from digest_items where person = 'ana' and agent is null")]
    assert d["refused"] and held(stack)[0]["status"] == "waiting"
    assert any(t.startswith("Your decision on P-1 didn't count") for t in told), told
    assert decide(approving, provider, [p["digest"]]).status_code == 200  # afresh
    sweep(stack)
    assert held(stack)[0]["status"] == "made"


def counting(stack, monkeypatch) -> list[str]:
    scenario, reads = stack.gateway.scenario, []
    was = scenario.record
    monkeypatch.setattr(scenario, "record", lambda key: reads.append(key) or was(key))
    return reads


def test_no_record_is_read_for_a_token_nobody_was_given(stack, monkeypatch):
    reads = counting(stack, monkeypatch)
    with stack.client("not-a-run-token") as c:
        r = c.post("/run/tools/change_due_date",
                   json={"args": {"key": [f"Q-{n}" for n in range(5000)], "due": "2026-12-01"}})
    assert r.status_code == 401 and reads == []


def test_nor_for_a_call_its_arguments_dont_fit_or_naming_too_many(stack, monkeypatch):
    scenario = stack.gateway.scenario
    tools = scenario.tools()
    keyed = tools["change_due_date"]  # as a tool that takes a list of the records it changes
    monkeypatch.setattr(scenario, "tools", lambda: {**tools, "change_due_date": replace(keyed, schema={
        **keyed.schema, "properties": {**keyed.schema["properties"], "key": {
            "type": ["string", "array"], "items": {"type": "string"}}}})})
    reads = counting(stack, monkeypatch)
    _, token = stack.open_run()
    with stack.client(token) as c:
        many = c.post("/run/tools/change_due_date",
                      json={"args": {"key": [f"Q-{n}" for n in range(21)], "due": "2026-12-01"}})
        wrong = c.post("/run/tools/change_due_date", json={"args": {"key": "Q-1002", "due": 7}})
    assert many.status_code == 403 and many.json()["reasons"] == ["a-change-names-few-records"]
    assert wrong.status_code == 403 and wrong.json()["reasons"] == ["arguments-fit-the-schema"]
    assert reads == []
