"""Handing a conversation over to people (core/handover.py, docs/agent-model.md#handing-a-conversation-over):
an instance's settings name the teams it may hand a conversation to; its agent hands one over at
the person's word, with a brief; while it's handed over, the agent answers nothing there, and one
of the team, who reads the brief and the person's own words, each record they may not see as such,
takes it and answers in the same chat, until they hand it back, and the agent answers again,
knowing what was said."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db
from a5s.contract import parse_settings
from a5s.core import approvals, erasure, export, handover, retention
from conftest import FAKE_MODELS, PROVIDER_KEY, FakeModel, Stack, accessible, build_root, running

ASKS = "Can I talk to a person about the refund on Q-1002?"
BRIEF = "Ben wants to talk to someone about the refund on Q-1002, paid twice."


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The sample, with the assistant's release handing conversations over where its settings
    name a team."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    spec = root / "agents" / "assistant" / "agent.yaml"
    spec.write_text(re.sub(r"^(  agents: true)", r"  handover: true\n\1", spec.read_text(),
                           flags=re.MULTILINE))
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def as_person(url: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    return httpx.request(method, f"{url}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})


def swept(stack: Stack) -> dict:
    with stack.client() as c:
        answer = c.post("/handovers/sweep")
    answer.raise_for_status()
    return answer.json()


def handed(stack: Stack, team: str = "operations") -> dict:
    """Ben asks for a person, and the assistant hands it to the team."""
    stack.model.reply(None, ("hand_over", {"team": team, "brief": BRIEF}))
    stack.model.reply("I've passed this to the operations team: someone there answers you here.")
    stack.say(ASKS, person="ben")
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from handovers order by id desc limit 1").fetchone()


def told(stack: Stack, person: str = "ben") -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute("select text from outbox where person = %s "
                                                "order by id", (person,))]


def test_the_agent_hands_the_conversation_to_a_team_which_answers_until_it_hands_it_back(
        stack, approving, provider):
    assert not stack.settle(hands_to=["operations"]).refused
    row = handed(stack)
    assert (row["person"], row["agent"], row["team"]) == ("ben", "assistant", "operations")
    assert row["brief"] == BRIEF and row["said"][-1]["text"] == ASKS  # his own words alone
    result = json.dumps(stack.model.requests[-1]["body"])
    assert "Tell them the operations team takes it from here" in result
    assert swept(stack)["told"] == 1
    assert any(t.startswith("The assistant has handed this conversation to the operations team")
               for t in told(stack))
    # While it's handed over, the assistant answers nothing there
    asked = len(stack.model.requests)
    assert stack.say("Hello? Is anyone there?", person="ben") == ""
    assert len(stack.model.requests) == asked
    # The team reads the brief and Ben's own words, each billing record as one they may not see
    [line] = as_person(approving, provider, "chen", "GET", "/studio/api/handovers").json()["handovers"]
    assert line["person"] == "Ben Okafor" and line["unanswered"] == 1 and line["taken_by"] is None
    assert "Q-1002" not in line["brief"] and handover.HIDDEN in line["brief"]
    home = as_person(approving, provider, "omar", "GET", "/studio/api/home").json()["waiting"]
    assert any(w["kind"] == "handover" and w["go"] == f"/studio/handovers/{row['id']}" for w in home)
    shell = as_person(approving, provider, "chen", "GET", "/shell/api").json()["pages"]
    assert any(p["page"] == "handovers" for p in shell)
    # Nobody outside the team reads it, nor Ben's own team
    assert as_person(approving, provider, "ana", "GET", "/studio/api/handovers").json() == {"handovers": []}
    assert as_person(approving, provider, "ana", "GET",
                     f"/studio/api/handovers/{row['id']}").status_code == 404
    assert not any(p["page"] == "handovers" for p in
                   as_person(approving, provider, "ana", "GET", "/shell/api").json()["pages"])
    # One of the team takes it, and answers him in his chat
    path = f"/studio/api/handovers/{row['id']}"
    early = as_person(approving, provider, "chen", "POST", f"{path}/answer", {"text": "Hi"})
    assert early.status_code == 409 and "take it first" in early.json()["detail"]
    assert as_person(approving, provider, "chen", "POST", f"{path}/take").json() == {"done": True}
    other = as_person(approving, provider, "omar", "POST", f"{path}/take")
    assert other.status_code == 409 and "Chen Wei has taken it" in other.json()["detail"]
    assert as_person(approving, provider, "chen", "POST", f"{path}/answer",
                     {"text": "We'll look at it today."}).json() == {"done": True}
    assert swept(stack)["answered"] == 1
    assert "Chen Wei, of the operations team: We'll look at it today." in told(stack)
    seen = as_person(approving, provider, "chen", "GET", path).json()
    assert [s["answered"] for s in seen["since"]] == [True]
    assert seen["answers"][0]["sent"] and seen["answers"][0]["by"] == "Chen Wei"
    # Handed back, the assistant answers again, knowing what was said
    assert as_person(approving, provider, "chen", "POST", f"{path}/back").json() == {"done": True}
    assert swept(stack)["back"] == 1
    assert any(t.startswith("The operations team has handed this conversation back to the "
                            "assistant") for t in told(stack))
    stack.model.reply("Glad Chen could help.")
    assert stack.say("Thanks, all sorted.", person="ben") == "Glad Chen could help."
    sent = json.dumps(stack.model.requests[-1]["body"])
    assert "Hello? Is anyone there?" in sent and "We'll look at it today." in sent
    ends = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "hand-back"]
    assert ends and ends[-1]["args"]["by"] == "chen"
    assert "We'll look at it today" not in json.dumps(stack.ledger())  # never the words



def test_the_team_reads_a_brief_only_if_they_may_see_every_record_its_run_handled(
        stack, approving, provider):
    """The agent writes the brief from what its run read, which it may say without naming a
    record: someone of the team who may not see a record the run handled reads what the person
    said instead, as the studio wouldn't show them the run."""
    assert not stack.settle(hands_to=["operations"]).refused
    row = handed(stack)
    with db.transaction(stack.admin) as conn:  # the run read Q-1002, which operations may not see
        conn.execute("insert into run_records (run_id, record) values (%s, 'Q-1002')",
                     (row["run_id"],))
    [line] = as_person(approving, provider, "chen", "GET", "/studio/api/handovers").json()["handovers"]
    assert line["brief"] == handover.WITHHELD and "refund" not in line["brief"]
    seen = as_person(approving, provider, "chen", "GET", f"/studio/api/handovers/{row['id']}").json()
    assert seen["brief"] == handover.WITHHELD
    assert [s["text"] for s in seen["said"]] == [ASKS.replace("Q-1002", handover.HIDDEN)]

def test_it_hands_over_only_to_a_team_its_settings_name(stack, approving):
    stack.model.reply("I can't pass you to a person here.")
    stack.say(ASKS, person="ben")
    offered = [t["function"]["name"] for t in stack.model.requests[-1]["body"].get("tools", [])]
    assert "hand_over" not in offered  # no team named: never offered
    assert not stack.settle(hands_to=["operations"]).refused
    stack.model.reply(None, ("hand_over", {"team": "quality", "brief": BRIEF}))
    stack.model.reply("I couldn't.")
    stack.say(ASKS, person="ben")
    said = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert "hands conversations to operations alone" in said
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from handovers").fetchone()["n"] == 0


def test_a_conversation_nobody_answers_is_handed_back(stack, approving):
    assert not stack.settle(hands_to=["operations"]).refused
    row = handed(stack)
    swept(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("update handovers set started_at = now() - interval '4 days'")
    assert swept(stack)["back"] == 1
    with db.transaction(stack.admin) as conn:
        ended = conn.execute("select * from handovers where id = %s", (row["id"],)).fetchone()
    assert ended["ended_at"] and ended["ended_by"] is None
    [lapsed] = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "hand-back"]
    assert lapsed["args"]["lapsed"]


def test_approvers_read_whom_it_may_hand_conversations_to_and_the_core_checks_them(stack):
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    before = parse_settings((folder / "settings.yaml").read_bytes())
    settings["serial"] += 1
    settings["instances"]["assistant-finance"]["hands_to"] = ["operations"]
    after = parse_settings(yaml.safe_dump(settings).encode())
    words = approvals.changes(before, after, stack.gateway.definitions,
                              stack.gateway.scenario.person)
    [line] = [w for w in words if "hand" in w["text"]]
    assert line["widens"] and line["text"].startswith("assistant-finance may hand a conversation "
                                                      "over, at its agent's word, to the people "
                                                      "of the operations team")
    settings["instances"]["assistant-finance"]["hands_to"] = ["nobody-here"]
    wrong = parse_settings(yaml.safe_dump(settings).encode())
    assert any("teams nobody in the directory is in: nobody-here" in p
               for p in stack.gateway.unusable(wrong, None))


def test_what_a5s_keeps_of_a_handover_is_theirs_and_goes_with_them(stack, approving, provider):
    assert not stack.settle(hands_to=["operations"]).refused
    row = handed(stack)
    as_person(approving, provider, "chen", "POST", f"/studio/api/handovers/{row['id']}/take")
    as_person(approving, provider, "chen", "POST", f"/studio/api/handovers/{row['id']}/answer",
              {"text": "On it."})
    swept(stack)
    with db.transaction(stack.admin) as conn:
        [kept] = export.gather(conn, "ben")["handovers"]
        assert kept["team"] == "operations" and kept["answers"][0]["text"] == "On it."
        assert export.gather(conn, "chen")["handover_answers"] == 1
    with db.transaction(stack.admin) as conn:
        gone, _ = erasure.erase(conn, "ben", datetime.now(UTC), here=True)
        assert gone["handovers"] == 1
        assert conn.execute("select count(*) as n from handover_replies").fetchone()["n"] == 0
    row = handed(stack)
    with db.transaction(stack.admin) as conn:  # handed back, and kept for what the officer chose
        conn.execute("update handovers set ended_at = now() - interval '13 months'")
        assert retention.sweep(conn, datetime.now(UTC), stack.gateway.scenario.name)["handovers"] == 1


def test_one_of_the_team_answers_from_the_studio(stack, approving, provider, browser):
    assert not stack.settle(hands_to=["operations"]).refused
    row = handed(stack)
    swept(stack)
    stack.send("Still there?", person="ben")
    provider.person = "chen"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/handovers")
    page.wait_for_selector("#handovers a", timeout=30000)
    assert "Ben Okafor" in page.inner_text("#handovers")
    accessible(page)
    page.click("#handovers a")
    page.wait_for_selector("#answer button.primary", timeout=30000)
    assert "Still there?" in page.inner_text("#said") and handover.HIDDEN in page.inner_text("#brief")
    page.click("#answer button.primary")  # take it
    page.wait_for_selector("#answer-text", timeout=30000)
    page.fill("#answer-text", "Yes: I'm looking at it now.")
    page.click("#answer button.primary")
    page.wait_for_selector("#said >> text=Yes: I'm looking at it now.", timeout=30000)
    accessible(page)
    assert swept(stack)["answered"] == 1
    assert "Chen Wei, of the operations team: Yes: I'm looking at it now." in told(stack)
    page.click("#answer button:has-text('Hand it back')")  # it asks first
    page.click("dialog[open] button.primary")
    page.wait_for_selector("text=It's been handed back to the assistant.", timeout=30000)
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select ended_by from handovers where id = %s",
                            (row["id"],)).fetchone()["ended_by"] == "chen"


def test_a_brief_is_withheld_where_its_conversation_held_what_the_team_may_not_see(
        stack, approving, provider):
    """Round 14 (B-H1): the run that hands Ben over is given his conversation's latest turns,
    whatever their topic, so a brief can carry what an earlier run read: here, yesterday's
    answer about his billing question. The run takes the records the runs behind those turns
    handled, so Chen, who may not see billing, reads that the brief is withheld."""
    assert not stack.settle(hands_to=["operations"]).refused
    stack.model.reply(None, ("get_record", {"key": "Q-1002"}))
    stack.model.reply("Q-1002 is Contoso's refund of £860.00, paid twice on 2026-10-20: finance "
                      "is checking it.")
    stack.say("What's happening with Q-1002?", person="ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("update turns set at = at - interval '20 hours'")
    before = len(stack.model.requests)
    stack.model.reply(None, ("hand_over", {"team": "operations", "brief": (
        "Ben wants to talk to someone about his laptop. He is also waiting on Contoso's refund "
        "of £860.00, paid twice on 2026-10-20.")}))
    stack.model.reply("I've passed you to operations.")
    stack.say("Can I talk to a person about my laptop?", person="ben")
    given = json.dumps(stack.model.requests[before]["body"]["messages"], ensure_ascii=False)
    assert "£860.00" in given  # it was given yesterday's answer
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select * from handovers").fetchone()
        handled = {r["record"] for r in conn.execute(
            "select record from run_records where run_id = %s", (row["run_id"],))}
    assert "Q-1002" in handled and not stack.gateway.scenario.sees("chen", "Q-1002")
    seen = as_person(approving, provider, "chen", "GET", f"/studio/api/handovers/{row['id']}").json()
    assert seen["brief"] == handover.WITHHELD
