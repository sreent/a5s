"""Who sent a message: tokens from the organisation's identity provider, checked in the core."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import replace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from a5s import db
from a5s.core import inbox
from a5s.core.identity import IdentityConfig, IdentityError, Verifier
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


@pytest.fixture
def signing_in(stack, issuer):
    """The core's channels with sign-in through the fake identity provider, as deployed."""
    endpoint = replace(stack.gateway, identity=issuer.verifier(), cfg=stack.as_role("channels"))
    with serve(inbox.create_app(endpoint), free_port()) as url:
        yield f"{url}/channels/local/messages"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_core_asks_people_to_sign_in_and_records_who_did(stack, issuer, signing_in):
    stack.model.reply("Hello, Ana.")
    message = {"agent": "assistant", "text": "Hi"}
    assert httpx.post(signing_in, json=message).status_code == 401
    assert httpx.post(signing_in, json={**message, "person": "ana"},
                      headers=bearer(issuer.token("ben"))).status_code == 403
    expired = issuer.token("ana", exp=int(time.time()) - 120)
    assert httpx.post(signing_in, json=message, headers=bearer(expired)).status_code == 401

    sent = httpx.post(signing_in, json=message, headers=bearer(issuer.token("ana")))
    assert sent.status_code == 202
    stack.scheduler().answer_waiting()
    mine = httpx.get(f"{signing_in}/{sent.json()['message']}", headers=bearer(issuer.token("ana")))
    bens = httpx.get(f"{signing_in}/{sent.json()['message']}", headers=bearer(issuer.token("ben")))
    assert mine.json()["replies"] == ["Hello, Ana."] and bens.status_code == 404

    [received] = [e for e in stack.ledger() if e["kind"] == "inbound"]
    assert received["args"]["identity"] == "verified" and received["acts_for"] == ["ana"]
    recorded = json.dumps(stack.ledger())
    assert issuer.token("ana").split(".")[2] not in recorded  # the token is checked, never kept


def test_sign_in_finds_people_through_the_directory_as_teams_does(stack, issuer):
    entra = Verifier(IdentityConfig(issuer=issuer.url, audience="a5s", person_claim="oid",
                                    directory_prefix="entra"),
                     httpx.Client(transport=httpx.MockTransport(issuer.handler)))
    endpoint = replace(stack.gateway, identity=entra, cfg=stack.as_role("channels"))
    ana = issuer.token(None, oid="0a5a0000-0000-4000-8000-00000000a0a1")  # Ana's Entra ID
    stranger = issuer.token(None, oid="0a5a0000-0000-4000-8000-0000000000ff")
    with serve(inbox.create_app(endpoint), free_port()) as url:
        message = {"agent": "assistant", "text": "Hi"}
        assert httpx.post(f"{url}/channels/local/messages", json=message,
                          headers=bearer(ana)).status_code == 202
        refused = httpx.post(f"{url}/channels/local/messages", json=message,
                             headers=bearer(stranger))
    assert refused.status_code == 403 and "doesn't know who you are" in refused.json()["detail"]
    assert [e["acts_for"] for e in stack.ledger() if e["kind"] == "inbound"] == [["ana"]]


def test_without_an_identity_provider_only_development_takes_peoples_word(stack):
    message = stack.send("Hi")
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select 1 from inbound where id = %s", (message,)).fetchone()
    assert stack.ledger()[-1]["args"]["identity"] == "unverified (development)"

    production = replace(stack.gateway, cfg=replace(stack.as_role("channels"), development=False))
    with serve(inbox.create_app(production), free_port()) as url:
        refused = httpx.post(f"{url}/channels/local/messages",
                             json={"person": "ana", "agent": "assistant", "text": "Hi"})
    assert refused.status_code == 503


def test_the_scheduler_cant_say_who_a_message_is_from(stack):
    message = stack.send("Hi from Ana")
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": message, "sender": "ben", "channel": "teams"}})
        assert opened.status_code == 200
        unknown = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": str(uuid.uuid4())}})
        again = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": message}})
        bare = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "sender": "ana"}})
    [opening] = [e for e in stack.ledger(opened.json()["run"]) if e["action"] == "open"]
    assert opening["acts_for"] == ["ana"] and opening["args"]["channel"] == "local"
    assert unknown.json()["detail"]["reasons"] == ["the message it answers isn't one the core received"]
    assert again.json()["detail"]["reasons"] == ["the message it answers has been answered already"]
    assert bare.status_code == 400
