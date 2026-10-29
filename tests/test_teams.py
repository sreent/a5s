"""Teams: the core receives each message itself, checks it, and answers only through the core."""

import json
import threading
import time
import uuid
from dataclasses import replace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from a5s.core import teams
from a5s.core.teams import Teams, TeamsConfig
from conftest import free_port, serve

APP_ID, TENANT = "a5s-bot-app", "0a5a7e17-0000-4000-8000-000000000001"
ANA, BEN = "0a5a0000-0000-4000-8000-00000000a0a1", "0a5a0000-0000-4000-8000-00000000b0b2"
SERVICE_URL = "https://smba.test/amer/"


class FakeBotFramework:
    """The Bot Framework's signing keys, Entra ID's login for the bot, and Teams' connector."""

    def __init__(self) -> None:
        self.keys = {kid: rsa.generate_private_key(public_exponent=65537, key_size=2048)
                     for kid in ("teams-key", "webchat-key")}
        self.endorsements = {"teams-key": ["msteams"], "webchat-key": ["webchat"]}
        self.sent: list[dict] = []
        self.logins: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/v1/.well-known/openidconfiguration"):
            return httpx.Response(200, json={"issuer": teams.BOT_FRAMEWORK,
                                             "jwks_uri": "https://login.botframework.test/v1/keys"})
        if url.endswith("/v1/keys"):
            return httpx.Response(200, json={"keys": [
                {**RSAAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": kid, "use": "sig",
                 "endorsements": self.endorsements[kid]} for kid, key in self.keys.items()]})
        if url == f"https://login.test/{TENANT}/oauth2/v2.0/token":
            self.logins.append(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(200, json={"access_token": "bot-token", "expires_in": 3600})
        if request.url.host == "smba.test" and request.url.path.endswith("/activities"):
            assert request.headers["authorization"] == "Bearer bot-token"
            self.sent.append(json.loads(request.content))
            return httpx.Response(201, json={"id": f"reply-{len(self.sent)}"})
        return httpx.Response(404)

    def token(self, *, kid: str = "teams-key", **claims) -> str:
        now = int(time.time())
        body = {"iss": teams.BOT_FRAMEWORK, "aud": APP_ID, "serviceurl": SERVICE_URL,
                "nbf": now, "exp": now + 3600, **claims}  # Bot Framework tokens carry no iat
        return jwt.encode({k: v for k, v in body.items() if v is not None}, self.keys[kid],
                          algorithm="RS256", headers={"kid": kid})

    def auth(self, **claims) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(**claims)}"}


def activity(text: str = "Which questions mention an invoice?", *, sender: str = ANA,
             tenant: str = TENANT, channel: str = "msteams", service_url: str = SERVICE_URL,
             kind: str = "personal") -> dict:
    return {"type": "message", "id": f"msg-{uuid.uuid4().hex[:8]}", "channelId": channel,
            "serviceUrl": service_url, "text": text,
            "from": {"id": "29:1-person", "aadObjectId": sender},
            "recipient": {"id": "28:a5s-bot"},
            "conversation": {"id": "a:1-chat", "conversationType": kind, "tenantId": tenant},
            "channelData": {"tenant": {"id": tenant}}}


@pytest.fixture
def bot(stack):
    fake = FakeBotFramework()
    cfg = TeamsConfig(app_id=APP_ID, app_secret="bot-secret", tenant_id=TENANT,
                      service_hosts=("smba.test",), login_url="https://login.test",
                      metadata_url="https://login.botframework.test/v1/.well-known/openidconfiguration")
    stack.gateway.teams = Teams(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(teams.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/api/messages"
        yield fake


def queued(stack) -> list[dict]:
    from a5s import db

    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from inbound order by received_at").fetchall()


def test_a_teams_message_is_checked_recorded_and_answered_in_teams(stack, bot):
    stack.model.reply("Q-1001 mentions an invoice.")
    message = activity()
    assert httpx.post(bot.url, json=message, headers=bot.auth()).status_code == 200
    [row] = queued(stack)
    assert row["person"] == "ana" and row["text"] == message["text"]

    assert stack.scheduler().answer_waiting() == 1
    [sent] = bot.sent
    assert sent["text"] == "Q-1001 mentions an invoice."
    assert sent["replyToId"] == message["id"] and sent["conversation"] == {"id": "a:1-chat"}
    assert [login["scope"] for login in bot.logins] == ["https://api.botframework.com/.default"]

    entries = stack.ledger()
    opened = next(e for e in entries if e["kind"] == "run" and e["action"] == "open")
    assert opened["args"]["identity"] == "verified by teams"
    assert [e["outcome"]["status"] for e in entries if e["action"] == "deliver"] == ["ok"]
    assert message["text"] not in json.dumps(entries)  # the ledger keeps a hash, not the words
    assert stack.verify().ok

    assert httpx.post(bot.url, json=message, headers=bot.auth()).status_code == 200  # sent again
    assert stack.scheduler().answer_waiting() == 0
    assert len(bot.sent) == 1


@pytest.mark.parametrize("case", [
    "no token", "another bot", "another issuer", "expired", "another service URL",
    "a key not endorsed for Teams", "another organisation", "another channel",
    "a service URL Teams doesn't use"])
def test_teams_messages_that_dont_check_out_are_refused_and_never_queued(stack, bot, case):
    message, headers = activity(), bot.auth()
    if case == "no token":
        headers = {}
    elif case == "another bot":
        headers = bot.auth(aud="someone-elses-bot")
    elif case == "another issuer":
        headers = bot.auth(iss="https://sts.windows.net/someone/")
    elif case == "expired":
        headers = bot.auth(exp=int(time.time()) - 600)
    elif case == "another service URL":
        headers = bot.auth(serviceurl="https://smba.test/emea/")
    elif case == "a key not endorsed for Teams":
        headers = bot.auth(kid="webchat-key")
    elif case == "another organisation":
        message = activity(tenant="another-tenant")
    elif case == "another channel":
        message = activity(channel="webchat")
    elif case == "a service URL Teams doesn't use":
        message, headers = activity(service_url="https://evil.test/"), bot.auth(serviceurl="https://evil.test/")

    response = httpx.post(bot.url, json=message, headers=headers)
    assert response.status_code == (401 if case == "no token" else 403)
    assert not queued(stack) and not bot.sent
    assert not [e for e in stack.ledger() if e["kind"] == "inbound"]


def test_someone_the_directory_doesnt_know_is_told_so_and_nothing_runs(stack, bot):
    stranger = activity(sender="0a5a0000-0000-4000-8000-0000000000ff")
    assert httpx.post(bot.url, json=stranger, headers=bot.auth()).status_code == 200
    assert not queued(stack)
    assert [m["text"] for m in bot.sent] == [teams.UNKNOWN]
    assert stack.ledger()[-1]["decision"] == "deny"


def test_group_chats_get_a_pointer_to_a_one_to_one_chat(stack, bot):
    assert httpx.post(bot.url, json=activity(kind="groupChat"), headers=bot.auth()).status_code == 200
    assert not queued(stack)
    assert [m["text"] for m in bot.sent] == [teams.ONE_TO_ONE]


def test_a_scheduler_cant_forge_or_reuse_a_teams_message(stack, bot):
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    [row] = queued(stack)

    def open_run(sender: str, inbound: str) -> httpx.Response:
        with stack.client() as c:
            return c.post("/runs", json={"instance": "assistant-finance", "trigger": {
                "kind": "message", "channel": "teams", "sender": sender, "inbound": inbound}})

    for sender, inbound, reason in [
            ("ana", str(uuid.uuid4()), "isn't one the core received"),
            ("ben", str(row["id"]), "came from ana, not ben"),
            ("ana", "not-an-id", "isn't one the core received")]:
        refused = open_run(sender, inbound)
        assert refused.status_code == 409 and reason in refused.json()["detail"]["reasons"][0]
    assert open_run("ana", str(row["id"])).status_code == 200
    again = open_run("ana", str(row["id"]))
    assert again.status_code == 409 and "answered already" in again.json()["detail"]["reasons"][0]


def test_a5s_notices_reach_teams_only_in_answer_and_briefly(stack, bot):
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    [row] = queued(stack)

    def notice(person: str, inbound: str) -> httpx.Response:
        with stack.client() as c:
            return c.post("/channels/teams/notices", json={
                "person": person, "inbound": inbound, "text": "See https://evil.test now"})

    assert notice("ben", str(row["id"])).status_code == 403  # not in answer to ben
    assert [notice("ana", str(row["id"])).status_code for _ in range(4)] == [200, 200, 200, 403]
    assert [m["text"] for m in bot.sent] == ["See [link removed] now"] * 3  # no links in a5s's own words


def test_a_suspended_agent_says_so_in_teams(stack, bot):
    stack.suspend()
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()
    assert [m["text"] for m in bot.sent] == [
        "The assistant is suspended at the moment, so it can't help. Ask Ana Ortiz."]
    assert not stack.model.requests


def test_the_scheduler_answers_as_messages_arrive(stack, bot):
    stack.model.reply("Hello, Ana.")
    stop = threading.Event()
    listener = threading.Thread(target=stack.scheduler().listen, args=(stop,), daemon=True)
    listener.start()
    try:
        httpx.post(bot.url, json=activity("Hello"), headers=bot.auth()).raise_for_status()
        deadline = time.monotonic() + 30
        while not bot.sent and time.monotonic() < deadline:
            time.sleep(0.1)
    finally:
        stop.set()
        listener.join(10)
    assert [m["text"] for m in bot.sent] == ["Hello, Ana."]


def test_a_teams_run_writes_only_to_the_person_it_answers(stack, bot):
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    [row] = queued(stack)
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "channel": "teams", "sender": "ana", "inbound": str(row["id"])}})
    with stack.client(opened.json()["token"]) as c:
        denied = c.post("/run/messages", json={"to": "ben", "text": "Psst, Ben."})
    assert denied.status_code == 403
    assert denied.json()["reasons"] == ["teams-answers-the-sender"] and not bot.sent


def test_a_busy_conversation_waits_in_the_queue_without_holding_others_up(stack, bot):
    scheduler = stack.scheduler()
    assert scheduler._lease("ana/assistant/general", "a run for ana")
    httpx.post(bot.url, json=activity("From Ana"), headers=bot.auth()).raise_for_status()
    httpx.post(bot.url, json=activity("From Ben", sender=BEN), headers=bot.auth()).raise_for_status()
    assert scheduler._claim()["person"] == "ben"
    assert scheduler._claim() is None  # Ana's waits for her conversation
    scheduler._release("ana/assistant/general", "a run for ana")
    assert scheduler._claim()["person"] == "ana"


def test_the_endpoint_takes_one_message_not_a_flood(stack, bot):
    big = activity("x" * (300 * 1024))
    assert httpx.post(bot.url, json=big, headers=bot.auth()).status_code == 413
    assert not queued(stack)
