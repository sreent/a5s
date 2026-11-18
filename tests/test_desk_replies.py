"""The desk's ticket writes (phase 5, step 3): a reply on a ticket, through the ITSM's MCP server,
as its mcp.yaml declares it, a change of type `reply`. Below level 2, a5s holds each for the
decider of the ticket's service area, never anyone it's for; once they approve it, a5s posts it,
once for its key, which the ITSM honours; whoever asked is told; and an auditor follows it from
who asked to the ticket it changed."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from a5s import db
from conftest import FAKE_MODELS, SYSTEMS, FakeModel, Stack, build_root, deciding
from test_proposals import decide, held, sweep
from test_service_desk import running_desk

REPLY = ("reply_on_ticket", {"key": "INC0000001", "body": "Please reinstall the approved VPN "
                                                          "client, then sign in again."})


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The desk, its agent given the ITSM's replies beside what it has."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_desk(database, root, model, httpx.Client(transport=httpx.MockTransport(model.handler)),
                      more="  changes: [reply_on_ticket]") as found:
        yield found


@pytest.fixture
def approving(desk: Stack, provider) -> Iterator[str]:
    with deciding(desk, provider) as url:
        yield url


def asked(desk: Stack, call=REPLY, person: str = "rae", said: str = "Reply to Sam on INC0000001: "
          "reinstall the VPN client.") -> dict:
    """Someone asks the desk assistant for a reply, and it asks the ITSM: what it heard."""
    desk.model.reply(None, call)
    desk.model.reply("It waits for its service area's decider.")
    desk.say(said, person=person, agent="desk-assistant")
    return json.loads(desk.model.requests[-1]["body"]["messages"][-1]["content"])


def replies(key: str = "INC0000001") -> list[dict]:
    """What the ITSM has posted on a ticket."""
    return SYSTEMS["service-desk"]["itsm"].replies.get(key, [])


def test_a_reply_waits_for_the_decider_of_its_tickets_service_area(desk, approving):
    answer = asked(desk)
    assert answer["held"] == "P-1" and answer["decides"] == "Ola Nowak", answer
    assert replies() == []  # nothing posted yet
    [p] = held(desk)
    assert (p["tool"], p["action"], p["deciders"], p["acts_for"], p["parts"], p["status"]) == (
        "reply_on_ticket", "reply", ["ola"], ["rae"], ["access"], "waiting")
    assert p["said"].startswith("Post a reply on an ITSM ticket, which its requester reads: "
                                "INC0000001, with body Please reinstall the approved VPN client")
    assert "Can't reach the VPN, as it stood when it was asked for: status open." in p["said"]
    assert any(m["text"].startswith("P-1 waits") for m in desk.inbox("ola"))


def test_a_reply_in_another_area_waits_for_that_areas_decider(desk, approving):
    answer = asked(desk, ("reply_on_ticket", {"key": "INC0000002", "body": "A courier will "
                                                                          "collect the laptop."}),
                   person="hal", said="Tell Sam a courier collects the laptop on INC0000002.")
    assert answer["decides"] == "Hugo Lind", answer
    assert held(desk)[0]["deciders"] == ["hugo"]


def test_what_the_decider_approves_is_posted_once_and_whoever_asked_is_told(desk, approving,
                                                                            provider):
    asked(desk)
    [p] = held(desk)
    decided = decide(approving, provider, [p["digest"]], person="ola")
    assert decided.status_code == 200, decided.text
    assert replies() == []  # a5s posts it, not the page
    assert sweep(desk)["made"] == 1
    [posted] = replies()
    assert posted["replied"].startswith("Please reinstall the approved VPN client")
    assert posted["a5s_key"]  # made for a5s's key, so asking again makes nothing more
    assert sweep(desk)["made"] == 0 and len(replies()) == 1
    [p] = held(desk)
    assert (p["status"], p["decided_by"]) == ("made", "ola")
    told = [m["text"] for m in desk.inbox("rae")]
    assert any(t.startswith("Ola Nowak approved P-1, and a5s has made it: Post a reply on an "
                            "ITSM ticket") for t in told), told


def test_a_rejected_reply_isnt_posted(desk, approving, provider):
    asked(desk)
    [p] = held(desk)
    assert decide(approving, provider, [p["digest"]], "reject", person="ola").status_code == 200
    sweep(desk)
    assert replies() == [] and held(desk)[0]["status"] == "rejected"


def test_nobody_decides_a_reply_they_asked_for(desk, approving, provider):
    asked(desk)
    [p] = held(desk)
    assert decide(approving, provider, [p["digest"]], person="rae").status_code == 403
    assert decide(approving, provider, [p["digest"]], person="hugo").status_code == 403
    assert held(desk)[0]["status"] == "waiting"


def test_an_auditor_follows_a_reply_from_who_asked_to_the_ticket(desk, approving, provider):
    asked(desk)
    [p] = held(desk)
    decide(approving, provider, [p["digest"]], person="ola")
    sweep(desk)
    with desk.client() as c:  # signed in, as the auditor reads it where people sign in
        r = c.get("/audit/entries", params={"by": "zia", "person": "rae", "limit": 200},
                  headers={"X-A5S-Identity": provider.id_token(person="zia")})
    assert r.status_code == 200, r.text
    trail = [(e["kind"], e["action"], e.get("decision")) for e in r.json()["entries"]]
    assert ("tool", "reply_on_ticket", "hold") in trail  # who asked, and what for
    assert ("tool", "reply_on_ticket", "record") in trail  # what changed, once approved
    with db.transaction(desk.admin) as conn:
        [decision] = conn.execute("select person, decision from proposal_decisions").fetchall()
    assert (decision["person"], decision["decision"]) == ("ola", "approve")  # who decided
