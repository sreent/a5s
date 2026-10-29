"""Who sent a message: tokens from the organisation's identity provider, checked in the core."""

import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from a5s import db
from a5s.core.identity import IdentityConfig, IdentityError, Verifier
from a5s.services import channels
from conftest import FakeIssuer, free_port, serve


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


def forge(header: dict, claims: dict, secret: bytes | None) -> str:
    """A token made by hand, the way an attacker would make one."""

    def part(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    signed = f"{part(json.dumps(header).encode())}.{part(json.dumps(claims).encode())}"
    mac = hmac.new(secret, signed.encode(), hashlib.sha256).digest() if secret else b""
    return f"{signed}.{part(mac)}"


def test_a_token_from_the_identity_provider_names_the_person(issuer):
    assert issuer.verifier().person(issuer.token("ana")) == "ana"


@pytest.mark.parametrize("claims", [
    {"aud": "another-app"},
    {"iss": "https://elsewhere.test"},
    {"exp": int(time.time()) - 120},
    {"exp": None},
    {"preferred_username": None},
], ids=["audience", "issuer", "expired", "no expiry", "nobody named"])
def test_a_token_that_doesnt_check_out_is_refused(issuer, claims):
    with pytest.raises(IdentityError):
        issuer.verifier().person(issuer.token("ana", **claims))


def test_the_issuer_must_match_exactly_even_its_last_slash(issuer):
    issuer.url = "https://sts.test/tenant/"  # the way Entra ID's v1 tokens name it
    assert issuer.verifier().person(issuer.token("ana")) == "ana"
    with pytest.raises(IdentityError):
        issuer.verifier().person(issuer.token("ana", iss="https://sts.test/tenant"))


def test_a_token_changed_after_signing_is_refused(issuer):
    header, _, signature = issuer.token("ben").split(".")
    _, claims, _ = issuer.token("ana").split(".")
    with pytest.raises(IdentityError):
        issuer.verifier().person(f"{header}.{claims}.{signature}")


def test_tokens_signed_with_no_key_or_a_shared_secret_are_refused(issuer):
    claims = jwt.decode(issuer.token("ana"), options={"verify_signature": False})
    public = issuer.keys["key-1"].public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    for token in (forge({"alg": "none", "kid": "key-1"}, claims, None),
                  forge({"alg": "HS256", "kid": "key-1"}, claims, public)):  # the public key as a secret
        with pytest.raises(IdentityError):
            issuer.verifier().person(token)


def test_a_rotated_key_is_fetched_and_a_withdrawn_one_stops_working(issuer):
    verifier = issuer.verifier(max_age=0)
    old = issuer.token("ana")
    assert verifier.person(old) == "ana"
    issuer.rotate()  # the provider signs with a new key, and withdraws the old one
    assert verifier.person(issuer.token("ana")) == "ana"
    with pytest.raises(IdentityError):
        verifier.person(old)


def test_unknown_keys_cant_make_it_fetch_keys_over_and_over(issuer):
    verifier = issuer.verifier()
    verifier.person(issuer.token("ana"))
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(issuer.token("ana"), options={"verify_signature": False})
    for n in range(5):
        with pytest.raises(IdentityError):
            verifier.person(jwt.encode(claims, stranger, algorithm="RS256",
                                       headers={"kid": f"made-up-{n}"}))
    assert issuer.fetches == 1


def test_nobody_is_let_in_when_the_identity_provider_cant_be_reached_or_misleads(issuer):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    def elsewhere(request: httpx.Request) -> httpx.Response:
        response = issuer.handler(request)
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={**response.json(), "issuer": "https://elsewhere.test"})
        return response

    for handler in (down, elsewhere):
        verifier = Verifier(IdentityConfig(issuer=issuer.url, audience="a5s"),
                            httpx.Client(transport=httpx.MockTransport(handler)))
        with pytest.raises(IdentityError):
            verifier.person(issuer.token("ana"))


def open_run(stack, sender: str, identity: str | None) -> httpx.Response:
    with stack.client() as c:
        return c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "channel": "local", "sender": sender, "identity": identity}})


def test_the_core_opens_a_run_only_for_the_person_the_token_names(stack, issuer):
    stack.gateway.identity = issuer.verifier()
    tokens = {"ana": issuer.token("ana"), "ben": issuer.token("ben"),
              "expired": issuer.token("ana", exp=int(time.time()) - 120)}

    opened = open_run(stack, "ana", tokens["ana"])
    assert opened.status_code == 200
    run = opened.json()["run"]
    assert stack.ledger(run)[0]["args"]["identity"] == "verified"
    with db.transaction(stack.cfg.database_url) as conn:
        trigger = conn.execute("select trigger from runs where id = %s", (run,)).fetchone()["trigger"]
    assert "identity" not in trigger  # the token is checked, never kept

    for token, reason in [(tokens["ben"], "the identity is ben's, not ana's"),
                          (None, "the sender's identity wasn't given"),
                          (tokens["expired"], "the sender's identity doesn't check out")]:
        refused = open_run(stack, "ana", token)
        assert refused.status_code == 409
        assert any(r.startswith(reason) for r in refused.json()["detail"]["reasons"])
        assert stack.ledger()[-1]["decision"] == "deny"

    recorded = json.dumps(stack.ledger())
    assert all(token not in recorded for token in tokens.values())
    assert stack.verify().ok


def test_without_an_identity_provider_the_ledger_says_senders_went_unchecked(stack):
    run, _ = stack.open_run()
    assert stack.ledger(run)[0]["args"]["identity"] == "unverified (development)"


def test_the_channel_asks_people_to_sign_in_and_the_core_checks_them_again(stack, issuer):
    stack.model.reply("Hello, Ana.")
    stack.gateway.identity = issuer.verifier()
    channel = channels.create_app(stack.scheduler(), stack.cfg.database_url, issuer.verifier())
    as_ana = {"Authorization": f"Bearer {issuer.token('ana')}"}
    as_ben = {"Authorization": f"Bearer {issuer.token('ben')}"}
    message = {"agent": "assistant", "text": "Hi"}

    with serve(channel, free_port()) as url, httpx.Client(base_url=url, timeout=60) as person:
        assert person.post("/channels/local/messages", json=message).status_code == 401
        assert person.post("/channels/local/messages", json={**message, "person": "ana"},
                           headers=as_ben).status_code == 403
        reply = person.post("/channels/local/messages", json=message, headers=as_ana)
        assert reply.json()["reply"] == "Hello, Ana."
        assert person.get("/channels/local/outbox/ana", headers=as_ben).status_code == 403
        outbox = person.get("/channels/local/outbox/ana", headers=as_ana).json()
    assert [m["text"] for m in outbox] == ["Hello, Ana."]

    opened = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert [e["args"]["identity"] for e in opened] == ["verified"]


def test_a_scheduler_that_doesnt_pass_the_token_on_opens_no_run(stack, issuer):
    stack.gateway.identity = issuer.verifier()
    reply = stack.scheduler().handle_message(person="ana", agent="assistant", text="Hi")
    assert reply.startswith("a5s couldn't confirm it's you")
    assert not stack.model.requests
