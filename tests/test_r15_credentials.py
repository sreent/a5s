"""Round 15, the operator's finding (D3): a stolen service token acted as any agent: it opened
runs, made level-2 changes, wrote to people and read the trail. Now operators' commands call
the core with a token of their own, which opens no run and writes to nobody, and the service
token, the scheduler's, does none of their work; reading the trail through the core's API needs
the reader's own sign-in wherever people sign in; and each run's opening names the credential
behind it."""

from __future__ import annotations

from dataclasses import replace

from a5s import config
from a5s.core import gateway
from conftest import SERVICE_TOKEN

OPERATOR = "an operator's own token, as long as a token must be"
AUDITOR = "kofi"  # the sample's assurance


def test_an_operators_token_opens_no_run_and_the_schedulers_does_none_of_their_work(stack):
    stack.gateway.cfg = replace(stack.gateway.cfg, operator_token=OPERATOR)
    with stack.client(OPERATOR) as c:
        assert c.get("/status").status_code == 200
        assert c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", "ben")}}).status_code == 401
        assert c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                        "text": "Your password has expired."}).status_code == 401
    with stack.client() as c:  # the service token, the scheduler's
        refused = c.get("/status")
        assert refused.status_code == 401 and "operators' token" in refused.text
        assert c.post("/runs/sweep").status_code == 200
    stack.model.reply("Hello, Ben.")
    stack.say("Hello", person="ben")  # and the scheduler's work goes on
    assert stack.model.requests


def test_where_no_operators_token_is_set_the_service_token_does_both(stack):
    with stack.client() as c:
        assert c.get("/status").status_code == 200 and c.post("/runs/sweep").status_code == 200


def test_reading_the_trail_needs_the_readers_own_sign_in_where_people_sign_in(stack, approving,
                                                                               provider):
    with stack.client() as c:
        named = c.get("/audit/entries", params={"by": AUDITOR})  # a token names anyone
        signed = c.get("/audit/entries", params={"by": AUDITOR},
                       headers={"X-A5S-Identity": provider.id_token(person=AUDITOR)})
    assert named.status_code == 401 and "sign in to read the audit trail" in named.text
    assert signed.status_code == 200, signed.text


def test_each_run_opening_names_the_credential_behind_it(stack):
    stack.model.reply("Hello, Ben.")
    stack.say("Hello", person="ben")
    opened = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert opened and {e["args"]["credential"] for e in opened} == {
        gateway.credential(SERVICE_TOKEN)}
    assert SERVICE_TOKEN not in str(opened)


def paths(routes) -> set[str]:
    """Every route's path, within the routers an app includes too."""
    found: set[str] = set()
    for route in routes:
        found |= {route.path} if getattr(route, "path", None) else set()
        if (inner := getattr(route, "original_router", None)) is not None:
            found |= paths(inner.routes)
    return found


def test_every_operators_route_is_one_the_core_serves(stack):
    served = paths(gateway.create_app(stack.gateway).routes)
    assert gateway.OPERATING <= served, gateway.OPERATING - served


def test_an_operators_token_anyone_could_guess_or_the_schedulers_own_stops_the_core():
    base = {"A5S_SERVICE_TOKEN": "t" * 40, "A5S_SEAL_KEYS": "k" * 40}
    problems, _ = config.check({**base, "A5S_OPERATOR_TOKEN": "op"})
    assert problems == [("A5S_OPERATOR_TOKEN has 2 characters: it takes at least 32, made at "
                         "random")]
    problems, _ = config.check({**base, "A5S_OPERATOR_TOKEN": "t" * 40})
    assert problems == [("A5S_OPERATOR_TOKEN is the service token: make it apart, at random, or "
                         "operators hold the scheduler's")]
    assert config.check({**base, "A5S_OPERATOR_TOKEN": OPERATOR}) == ([], [])
