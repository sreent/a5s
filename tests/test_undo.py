"""Undoing a change an agent made (core/undoing.py, docs/agent-model.md#undoing-a-change): a
tool that changes a record says how the change is reversed; a5s keeps how, for as long as the
tool says, once it makes the change, at level 2 or once its deciders approve it; whoever it was
for, or whoever decides changes like it in its record's part, undoes it on its page, signed in
afresh for that alone; the core checks the sign-in again and makes the call that reverses it,
while the record is as the change left it; and the undo counts against the agent's accuracy,
as a wrong grade of its work, which the core seals."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from a5s import db
from a5s.contract import Tool, Undo
from a5s.core import samples, undoing
from conftest import CLIENT, SEAL_KEY, accessible
from test_levels import asked, due_of, levelled
from test_proposals import decide, held
from test_proposals import sweep as decided


def signed_for(url: str, provider, nonce: str, person: str) -> str:
    """A sign-in made afresh as the studio makes one, its nonce bound to an act: its token."""
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": f"{url}/studio/", "state": "s", "nonce": nonce,
        "code_challenge": challenge.decode(), "code_challenge_method": "S256", "max_age": "0"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    return httpx.post(f"{url}/studio/sign-in/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/studio/"}).json()["id_token"]


def undo(url: str, provider, change: int, person: str, nonce: str | None = None) -> httpx.Response:
    salt = secrets.token_urlsafe(32)
    token = signed_for(url, provider, nonce or undoing.nonce(change, salt), person)
    return httpx.post(f"{url}/studio/api/changes/{change}/undo", json={"salt": salt},
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)


def page(url: str, provider, change: int, person: str) -> httpx.Response:
    return httpx.get(f"{url}/studio/api/changes/{change}", timeout=30,
                     headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})


def swept(stack) -> dict:
    with stack.client() as c:
        answer = c.post("/undo/sweep")
    answer.raise_for_status()
    return answer.json()


def kept(stack) -> dict:
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select *, until - made_at as lasts from changes_made").fetchall()
    return row


def test_a_change_made_at_level_2_is_kept_to_undo_and_whoever_it_was_for_hears_how(
        stack, approving, provider):
    levelled(stack)
    asked(stack)  # Ben asks to move Q-1002 to 2026-11-13, and it's made
    assert due_of(stack) == "2026-11-13"
    made = kept(stack)
    assert made["record"] == "Q-1002" and made["acts_for"] == ["ben"] and made["parts"] == ["billing"]
    assert made["undo"] == {"tool": "change_due_date", "args": {"key": "Q-1002", "due": "2026-11-06"}}
    assert made["as_left"] == {"due date": "2026-11-13"} and made["lasts"] == timedelta(hours=24)
    # The agent is told how, to tell Ben, and so is the instance's owner, in her digest
    sent = json.dumps([r["body"] for r in stack.model.requests])
    link = f"{approving}/studio/undo?change={made['id']}"
    assert "a5s_undo" in sent and "It can be undone until" in sent and link in sent
    with db.transaction(stack.admin) as conn:
        [item] = conn.execute("select text from digest_items where person = 'ana'").fetchall()
    assert item["text"].endswith(f"on its page: {link}")
    # It's on Ben's home, while he can undo it
    home = httpx.get(f"{approving}/studio/api/home", timeout=30,
                     headers={"Authorization": f"Bearer {provider.id_token(person='ben')}"}).json()
    [mine] = [w for w in home["waiting"] if w["kind"] == "undo"]
    assert mine["go"] == f"/studio/undo?change={made['id']}" and "which you can undo until" in mine["what"]


def test_whoever_it_was_for_undoes_it_and_it_counts_against_the_agent(stack, approving, provider):
    levelled(stack)
    asked(stack)
    change = kept(stack)["id"]
    seen = page(approving, provider, change, "ben").json()
    assert seen["may"] and seen["state"] == "kept" and seen["whom"] == ["Ben Okafor"]
    assert seen["said"].startswith("Change a customer question's due date: Q-1002")
    assert page(approving, provider, change, "chen").status_code == 404  # neither for nor deciding
    asking = undo(approving, provider, change, "ben")
    assert asking.status_code == 200, asking.text
    again = undo(approving, provider, change, "ben")
    assert again.status_code == 409 and "undoing it already" in again.json()["detail"]
    assert due_of(stack) == "2026-11-13"  # the channels app undoes nothing
    assert swept(stack) == {"undone": 1, "refused": 0, "failed": 0}
    assert due_of(stack) == "2026-11-06"
    made = kept(stack)
    assert made["state"] == "undone" and made["undone_by"] == "ben" and made["proof"] is None
    [call] = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "change_due_date"
              and e.get("args", {}).get("undo") == change]
    assert call["acts_for"] == ["ben"] and call["outcome"] == {"status": "ok"}
    # As a wrong grade of the agent's work, which the core sealed, though never drawn
    with db.transaction(stack.admin) as conn:
        [graded] = conn.execute("select * from samples where run_id = %s",
                                (made["run_id"],)).fetchall()
        told = [r["text"] for r in conn.execute("select text from digest_items where person = 'ana'")]
        noted = [r["content"] for r in conn.execute(
            "select content from turns where person = 'ben' and role = 'notice'")]
    assert graded["grade"] == "wrong" and graded["graded_by"] == "ben" and graded["undone_at"]
    assert samples.counted((SEAL_KEY,), graded)
    assert any(t.startswith("Ben Okafor undid a change the assistant made") for t in told)
    assert any(n.startswith("Ben Okafor undid the change a5s made") for n in noted)
    after = page(approving, provider, change, "ben").json()
    assert after["state"] == "undone" and after["by"] == "Ben Okafor" and not after["may"]


def test_a_record_changed_since_is_left_for_whoever_changed_it(stack, approving, provider):
    levelled(stack)
    asked(stack)
    change = kept(stack)["id"]
    with db.transaction(stack.admin) as conn:  # someone moves it again in the records system
        conn.execute("insert into sample.changes (key, field, value, made_for) "
                     "values ('Q-1002', 'due', '2026-12-01', 'chen')")
    assert undo(approving, provider, change, "ben").status_code == 200
    assert swept(stack) == {"undone": 0, "refused": 1, "failed": 0}
    assert due_of(stack) == "2026-12-01"
    made = kept(stack)
    assert made["state"] == "refused" and "changed since" in made["outcome"]
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute("select text from digest_items where person = 'ben'")]
        assert conn.execute("select count(*) as n from samples where undone_at is not null"
                            ).fetchone()["n"] == 0
    assert any(t.startswith("a5s didn't undo the change the assistant made") for t in told)


def test_only_whoever_it_was_for_or_decides_there_may_and_only_in_time(stack, approving, provider):
    levelled(stack)
    asked(stack)
    change = kept(stack)["id"]
    assert page(approving, provider, change, "ana").json()["may"]  # who decides it in billing
    other = undo(approving, provider, change, "ben", nonce=undoing.nonce(change + 1, "x" * 20))
    assert other.status_code == 403 and "wasn't to undo change" in other.json()["detail"]
    with db.transaction(stack.admin) as conn:
        conn.execute("update changes_made set until = now() - interval '1 minute'")
    late = page(approving, provider, change, "ben").json()
    assert not late["may"] and "time to undo it has passed" in late["why_not"]
    refused = undo(approving, provider, change, "ben")
    assert refused.status_code == 409 and "time to undo it has passed" in refused.json()["detail"]


def test_a_held_change_once_approved_and_made_can_be_undone_too(stack, approving, provider):
    asked(stack)  # below level 2: it waits for Ana
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    decided(stack)  # sealed and made
    assert due_of(stack) == "2026-11-13"
    made = kept(stack)
    assert made["proposal_id"] == p["id"] and made["acts_for"] == ["ben"]
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute(
            "select text from outbox where person = 'ben' order by id")]
    assert any("a5s has made it" in t and f"/studio/undo?change={made['id']}" in t for t in told)
    assert undo(approving, provider, made["id"], "ben").status_code == 200
    assert swept(stack)["undone"] == 1 and due_of(stack) == "2026-11-06"
    with db.transaction(stack.admin) as conn:
        [graded] = conn.execute("select * from samples where proposal_id = %s", (p["id"],)).fetchall()
    assert graded["kind"] == "proposal" and graded["grade"] == "wrong"


def test_how_a_tool_says_its_undone_is_checked_as_the_core_starts():
    takes = {"type": "object", "properties": {"key": {"type": "string"}, "due": {"type": "string"}},
             "required": ["key", "due"]}

    def tool(name: str, undo_: Undo | None = None, **kwargs) -> Tool:
        return Tool(name=name, description=name, schema=takes, run=lambda call: {},
                    record_arg="key", action="change-due-date", undo=undo_, **kwargs)

    good = Undo(tool="move", args=(("key", "args.key"), ("due", "before.due date")))
    assert undoing.problems({"move": tool("move", good)}) == []
    assert "isn't a tool here" in undoing.problems({"move": tool("move", Undo(
        tool="gone", args=(("key", "args.key"),)))})[0]
    assert "must name the record" in undoing.problems({"move": tool("move", Undo(
        tool="move", args=(("key", "before.key"), ("due", "before.due date"))))})[0]
    assert "needs due" in undoing.problems({"move": tool("move", Undo(
        tool="move", args=(("key", "args.key"),)))})[0]
    for wrong in ((("key", "after.key"),), ()):
        with pytest.raises(ValueError):
            Undo(tool="move", args=wrong)
    with pytest.raises(ValueError, match="a minute to 7 days"):
        Undo(tool="move", args=(("key", "args.key"),), within=timedelta(days=8))
    with pytest.raises(ValueError, match="only a tool that changes a record"):
        Tool(name="read", description="read", schema=takes, run=lambda call: {}, undo=good)
    assert tool("move", good).schema_hash != tool("move").schema_hash  # how it's undone is pinned
    assert undoing.planned(tool("move", good), {"key": "Q-1", "due": "2026-12-01"},
                           {"fields": {"due date": "2026-11-01"}}) == {
        "tool": "move", "args": {"key": "Q-1", "due": "2026-11-01"}}
    assert undoing.planned(tool("move", good), {"key": "Q-1"}, None) is None  # never read


def test_someone_undoes_a_change_on_its_page(stack, approving, provider, browser):
    levelled(stack)
    asked(stack)
    change = kept(stack)["id"]
    provider.person = "ben"
    tab = browser.new_page(viewport={"width": 1280, "height": 900})
    tab.goto(f"{approving}/studio/undo?change={change}")
    tab.wait_for_selector("#change button.danger", timeout=30000)
    assert "Q-1002" in tab.inner_text("#change") and "Ben Okafor" in tab.inner_text("#change")
    accessible(tab)
    tab.click("#change button.danger")  # it asks first
    tab.click("dialog[open] button.primary")  # then signs in afresh for this alone, and back
    tab.wait_for_selector("#change >> text=a5s is undoing it", timeout=30000)
    assert swept(stack)["undone"] == 1
    tab.wait_for_selector("#change .badge.good", timeout=30000)  # undone, by whom
    assert re.search(r"by Ben Okafor", tab.inner_text("#change"))
    assert due_of(stack) == "2026-11-06"
    accessible(tab)
