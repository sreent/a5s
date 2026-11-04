"""Round 6, reviewer c: the people around a held change, and what each can do with what a5s
tells them. A decider's manager is sent a link to a page that shows them nothing. A part's new
owner can't decide what waited for the old one. A decider who rejects a change can't say why,
so the person who asked, and the agent's next run, never learn it. And the page shows the
record only as it stood, with no link to it and no word that it has changed since.

Each test fails now and says what a5s should do instead.
"""

from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from a5s import db
from a5s.core import inbox
from a5s.core.teams import Bot, Teams, TeamsConfig
from conftest import free_port, serve
from test_outside import FORM, read
from test_proposals import asked, held, signed, sweep
from test_teams import ANA, APP_ID, SERVICE_URL, TENANT, FakeBotFramework


@pytest.fixture
def teams_bot(stack):
    """Teams, with the assistant's bot, as test_teams sets it up."""
    fake = FakeBotFramework()
    cfg = TeamsConfig(bots=(Bot("assistant", APP_ID, "bot-secret"),), tenant_id=TENANT,
                      service_hosts=("smba.test",), login_url="https://login.test",
                      metadata_url="https://login.botframework.test/v1/.well-known/openidconfiguration")
    stack.gateway.teams = Teams(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with serve(inbox.create_app(replace(stack.gateway, cfg=stack.as_role("channels"))),
               free_port()) as url:
        fake.url = f"{url}/channels/teams/messages"
        yield fake


def review(url: str, provider, person: str) -> list[dict]:
    """What the decision page shows someone, once they've signed in to see what waits."""
    r = httpx.post(f"{url}/decide/review",
                   headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})
    assert r.status_code == 200, r.text
    return r.json()["proposals"]


def test_a_deciders_manager_can_see_the_change_they_are_sent(stack, approving, provider,
                                                              monkeypatch):
    """After five working days, Ana's manager, Lena, is told P-1 waits, and given the link to
    the decision page "unless someone decides it". The page shows only what waits for its
    deciders, so Lena, who can't decide it, sees "Nothing waits for your decision"."""
    stack.at("2026-11-02T09:30:00+00:00")  # a Monday
    asked(stack)
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], manager="lena"))
    stack.at("2026-11-09T10:00:00+00:00")  # five working days on
    sweep(stack)
    [up] = [m["text"] for m in stack.inbox("lena")]
    assert "/decide/?proposal=" in up
    shown = [p["key"] for p in review(approving, provider, "lena")]
    assert shown == ["P-1"], f"Lena follows the link she was sent and sees {shown}: {up!r}"


def test_a_decider_who_added_the_agents_app_gets_its_card_in_teams(stack, approving, teams_bot):
    """Ana's Teams has the assistant's app, as an organisation deploys it, but she has never
    written to it. a5s asks a decider "where they work" without naming the agent, which reads
    only the chats people wrote in, so her card waits in the web chat's inbox, which she
    doesn't use, and P-1 lapses unseen."""
    added = {"type": "installationUpdate", "action": "add", "id": "f:ana-adds-the-assistant",
             "channelId": "msteams", "serviceUrl": SERVICE_URL,
             "from": {"id": "29:1-ana", "aadObjectId": ANA}, "recipient": {"id": f"28:{APP_ID}"},
             "conversation": {"id": "a:1-ana-assistant", "conversationType": "personal",
                              "tenantId": TENANT},
             "channelData": {"tenant": {"id": TENANT}}}
    assert httpx.post(teams_bot.url, json=added, headers=teams_bot.auth()).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:  # the assistant may write to her there
        assert stack.gateway.reach(conn, "ana", "assistant")["channel"] == "teams"
    asked(stack)
    cards = [m for m in teams_bot.sent if m.get("attachments")]
    assert cards, f"Ana's card for P-1 went to {[m['channel'] for m in held_for(stack, 'ana')]}"


def held_for(stack, person: str) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select channel from outbox where person = %s", (person,)).fetchall()


def test_an_owner_added_to_a_part_can_decide_what_waits_there(stack, approving, provider,
                                                               monkeypatch):
    """Ana goes on leave, and the directory makes Dana a second owner of billing, the only way
    the contract has to name someone else who decides. P-1 was held while only Ana owned it,
    so it waits for Ana alone, is chased to her and her manager, and lapses."""
    asked(stack)
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "dana", replace(people["dana"],
                                                roles=("grader", "part-owner:billing")))
    shown = [p["key"] for p in review(approving, provider, "dana")]
    assert shown == ["P-1"], "billing's new owner can't see, or decide, what waits in billing"


def test_a_decider_can_say_why_they_reject_a_change(stack, approving, provider):
    """Ben hears only that Ana didn't approve it, and so does the agent's next run, so neither
    can say why, or what to ask for instead."""
    asked(stack)
    [p] = held(stack)
    token, salt = signed(approving, provider, [p["digest"]], "reject")
    r = httpx.post(f"{approving}/decide/proposals", json={
        "proposals": [p["digest"]], "decision": "reject", "salt": salt,
        "reason": "Contoso asked for the 20th, not the 13th."},
        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    sweep(stack)
    told = [m["text"] for m in stack.inbox("ben")]
    assert any("asked for the 20th" in t for t in told), told


def test_the_page_says_when_a_record_has_changed_since_it_was_asked_for(stack, approving,
                                                                       provider, monkeypatch):
    """The page shows Q-1002 "as it stands" when the change was held. Someone answers it
    meanwhile; Ana approves what she's shown, and only then hears a5s didn't make it."""
    asked(stack)
    records = dict(stack.gateway.scenario._records)
    records["Q-1002"] = {**records["Q-1002"], "status": "open"}
    monkeypatch.setattr(stack.gateway.scenario, "_records", records)
    [shown] = review(approving, provider, "ana")
    beside = json.dumps({k: v for k, v in shown.items() if k not in ("said", "key", "digest")})
    assert "Q-1002" in beside and "changed" in beside, (
        f"nothing on the page says Q-1002 has changed since: {shown}")


def test_a_decider_can_open_the_record_a_change_is_about(stack, approving, provider):
    """The card and the page give the fields the scenario reports, as they stood, and no link
    to the record, so to check its history or its emails Ana must find it herself."""
    asked(stack)
    [card] = [m["text"] for m in stack.inbox("ana") if m["text"].startswith("P-1 waits")]
    [shown] = review(approving, provider, "ana")
    link = "https://sample.a5s.dev/records/Q-1002"
    assert link in card and link in json.dumps(shown), card


def test_a_decider_is_told_which_values_came_from_a_customers_email(stack, approving):
    """Contoso's email tells the agent to move every due date to 2026-12-31. If a5s's reader
    gives that date as the email's, and the agent asks for it, Ana is told only that the agent
    read some outside content: the date counts as read from get_messages, like a record's, so
    nothing says it is the email's own."""
    read(stack, {**FORM, "date": "2026-12-31"},
         then=("change_due_date", {"key": "Q-1002", "due": "2026-12-31"}),
         said="Read Contoso's email and do what it says.")
    [p] = held(stack)
    assert any("2026-12-31" in f for f in p["flags"]), p["flags"]
