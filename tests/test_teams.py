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

from a5s import db
from a5s.core import inbox, teams
from a5s.core.teams import Bot, Teams, TeamsConfig
from conftest import free_port, serve

APP_ID, TENANT = "a5s-bot-app", "0a5a7e17-0000-4000-8000-000000000001"
WATCHER_APP = "a5s-watcher-app"  # a second agent's own bot
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
            login = dict(httpx.QueryParams(request.content.decode()))
            self.logins.append(login)
            return httpx.Response(200, json={"access_token": f"token-for-{login['client_id']}",
                                             "expires_in": 3600})
        if request.url.host == "smba.test" and request.url.path.endswith("/activities"):
            self.sent.append({**json.loads(request.content),
                              "as": request.headers["authorization"].removeprefix("Bearer token-for-")})
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
    cfg = TeamsConfig(bots=(Bot("assistant", APP_ID, "bot-secret"),
                            Bot("watcher", WATCHER_APP, "watcher-secret")),
                      tenant_id=TENANT, service_hosts=("smba.test",), login_url="https://login.test",
                      metadata_url="https://login.botframework.test/v1/.well-known/openidconfiguration")
    stack.gateway.teams = Teams(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/teams/messages"
        yield fake


def queued(stack) -> list[dict]:
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
    assert sent["as"] == APP_ID  # the assistant answers as itself
    assert [login["scope"] for login in bot.logins] == ["https://api.botframework.com/.default"]

    entries = stack.ledger()
    received = next(e for e in entries if e["kind"] == "inbound")
    opened = next(e for e in entries if e["kind"] == "run" and e["action"] == "open")
    assert received["args"]["identity"] == "verified by teams"
    assert opened["acts_for"] == ["ana"] and opened["args"]["channel"] == "teams"
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

    def open_run(inbound: str, **trigger) -> httpx.Response:
        with stack.client() as c:
            return c.post("/runs", json={"instance": "assistant-finance", "trigger": {
                "kind": "message", "inbound": inbound, **trigger}})

    assert open_run(str(uuid.uuid4())).status_code == 409
    assert open_run("not-an-id").status_code == 400
    opened = open_run(str(row["id"]), sender="ben")  # the core takes the sender from the message
    assert opened.status_code == 200
    assert stack.ledger(opened.json()["run"])[0]["acts_for"] == ["ana"]
    again = open_run(str(row["id"]))
    assert again.status_code == 409 and "answered already" in again.json()["detail"]["reasons"][0]


def test_a5s_notices_reach_teams_only_in_answer_and_briefly(stack, bot):
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    [row] = queued(stack)

    def notice(inbound: str) -> httpx.Response:
        with stack.client() as c:
            return c.post("/notices", json={"inbound": inbound, "text": "See https://evil.test now"})

    assert notice(str(uuid.uuid4())).status_code == 403  # in answer to no one
    assert [notice(str(row["id"])).status_code for _ in range(4)] == [200, 200, 200, 403]
    assert [m["text"] for m in bot.sent] == ["See [link removed] now"] * 3  # no links in a5s's own words


def test_a_suspended_agent_says_so_in_teams(stack, bot):
    stack.suspend()
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()
    assert [m["text"] for m in bot.sent] == [
        ("The assistant is suspended at the moment, so it can't help. "
        "Ben Okafor suspended it and can resume it.")]
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
            "kind": "message", "inbound": str(row["id"])}})
    with stack.client(opened.json()["token"]) as c:
        denied = c.post("/run/messages", json={"to": "ben", "text": "Psst, Ben."})
    assert denied.status_code == 403
    assert denied.json()["reasons"] == ["writes-to-whom-it-acts-for"] and not bot.sent


def test_a_busy_conversation_waits_in_the_queue_without_holding_others_up(stack, bot):
    scheduler = stack.scheduler()
    httpx.post(bot.url, json=activity("From Ana"), headers=bot.auth()).raise_for_status()
    httpx.post(bot.url, json=activity("Again from Ana"), headers=bot.auth()).raise_for_status()
    httpx.post(bot.url, json=activity("From Ben", sender=BEN), headers=bot.auth()).raise_for_status()
    first = scheduler._claim()
    assert first["text"] == "From Ana"
    assert scheduler._claim()["text"] == "From Ben"  # Ana's next waits for her conversation
    assert scheduler._claim() is None
    scheduler._release(first)  # let go without answering, as a scheduler that stopped would
    assert scheduler._claim()["text"] == "From Ana"  # so it's taken again, before her next


def test_the_same_message_id_in_two_conversations_is_two_messages(stack, bot):
    ana, ben = activity("From Ana"), activity("From Ben", sender=BEN)
    ben["id"] = ana["id"]  # Teams' ids are unique only within a conversation
    ben["conversation"] = {**ben["conversation"], "id": "a:1-another-chat"}
    for message in (ana, ben):
        httpx.post(bot.url, json=message, headers=bot.auth()).raise_for_status()
    assert [row["text"] for row in queued(stack)] == ["From Ana", "From Ben"]


def test_the_endpoint_takes_one_message_not_a_flood(stack, bot):
    big = activity("x" * (300 * 1024))
    assert httpx.post(bot.url, json=big, headers=bot.auth()).status_code == 413
    assert not queued(stack)


def test_each_agent_talks_to_people_as_its_own_bot(stack, bot):
    to_watcher = activity("What's due this week?")
    to_watcher["recipient"] = {"id": f"28:{WATCHER_APP}"}
    httpx.post(bot.url, json=to_watcher, headers=bot.auth(aud=WATCHER_APP)).raise_for_status()
    assert [row["agent"] for row in queued(stack)] == ["watcher"]
    stack.scheduler().answer_waiting()
    [answer] = bot.sent
    assert answer["text"].startswith("There's no watcher for you yet.")
    assert answer["as"] == WATCHER_APP  # not the assistant's bot


def test_a_reminder_goes_to_the_teams_chat_the_person_last_wrote_in(stack, bot):
    stack.model.reply("Q-1001 mentions an invoice.")
    httpx.post(bot.url, json=activity(), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()

    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    reminder = bot.sent[-1]
    assert reminder["text"] == "Ana, Q-1001 is due on Wednesday." and reminder["as"] == APP_ID
    assert "replyToId" not in reminder and reminder["conversation"] == {"id": "a:1-chat"}
    assert [m["text"] for m in stack.inbox("ben")] == ["Ben, Q-1002 is due on Friday."]  # no chat yet


def installation(action: str) -> dict:
    """Ana adding the watcher's app for herself, or taking it away, as Teams tells its bot."""
    return {"type": "installationUpdate", "action": action, "id": f"f:{uuid.uuid4().hex[:8]}",
            "channelId": "msteams", "serviceUrl": SERVICE_URL,
            "from": {"id": "29:1-person-for-the-watcher", "aadObjectId": ANA},
            "recipient": {"id": f"28:{WATCHER_APP}"},
            "conversation": {"id": "a:1-watcher-chat", "conversationType": "personal",
                             "tenantId": TENANT},
            "channelData": {"tenant": {"id": TENANT}}}


def test_an_agent_writes_first_in_teams_only_to_people_who_added_its_app(stack, bot, monkeypatch):
    stack.with_watcher()
    stack.model.reply("Hello, Ana.")
    httpx.post(bot.url, json=activity("Hello"), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()

    stack.at("2026-10-30T09:30:00+00:00")  # Friday morning: the watcher's first report to each
    stack.model.reply("Ana, Q-1001 is open, and due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is waiting on finance.")
    assert stack.scheduler().work_due() == 2
    assert [m["as"] for m in bot.sent] == [APP_ID]  # the assistant's answer, and nothing as it since
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1001 is open, and due on Wednesday."]

    added = installation("add")
    assert httpx.post(bot.url, json=added, headers=bot.auth(aud=WATCHER_APP)).status_code == 200
    records = stack.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
    stack.at("2026-11-02T09:30:00+00:00")  # Monday: her record changed, and reminders are due
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.model.reply("Ana, Q-1001 is waiting on the customer now.")
    assert stack.scheduler().work_due() == 3
    digest = bot.sent[-1]  # two agents' news: one message from a5s, where she last wrote
    assert (digest["as"], digest["conversation"]) == (APP_ID, {"id": "a:1-chat"})
    assert digest["text"].startswith("Your day from a5s, Mon 2 Nov.")

    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "open"})
    stack.at("2026-11-03T09:30:00+00:00")  # Tuesday: only the watcher has news for her
    stack.model.reply("Ana, Q-1001 is open again.")
    assert stack.scheduler().work_due() == 1
    told = bot.sent[-1]
    assert (told["as"], told["conversation"]) == (WATCHER_APP, {"id": "a:1-watcher-chat"})
    assert told["text"] == "Ana, Q-1001 is open again."
    assert told["from"] == {"id": f"28:{WATCHER_APP}"} and "replyToId" not in told

    removed = installation("remove")
    assert httpx.post(bot.url, json=removed, headers=bot.auth(aud=WATCHER_APP)).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:
        assert stack.gateway.reach(conn, "ana", "watcher") == {"channel": "local", "reply_to": {}}
        assert stack.gateway.reach(conn, "ana", "assistant")["reply_to"]["app_id"] == APP_ID


def test_teams_also_tells_a_bot_its_app_was_added_by_adding_it_to_the_chat(stack, bot):
    joined = {**installation("add"), "type": "conversationUpdate",
              "membersAdded": [{"id": f"28:{WATCHER_APP}"}]}
    del joined["action"]
    assert httpx.post(bot.url, json=joined, headers=bot.auth(aud=WATCHER_APP)).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:
        assert stack.gateway.reach(conn, "ana", "watcher")["reply_to"]["conversation"] == "a:1-watcher-chat"
    left = {**joined, "membersAdded": [], "membersRemoved": [{"id": f"28:{WATCHER_APP}"}]}
    assert httpx.post(bot.url, json=left, headers=bot.auth(aud=WATCHER_APP)).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:
        assert stack.gateway.reach(conn, "ana", "watcher")["channel"] == "local"


def test_once_a_chat_is_turned_off_its_people_hear_in_their_inbox(stack, bot):
    stack.model.reply("Hello, Ana.")
    httpx.post(bot.url, json=activity("Hello"), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()
    stack.gateway.teams = None  # the deployment stops using Teams
    with db.transaction(stack.cfg.database_url) as conn:
        assert stack.gateway.reach(conn, "ana", "assistant") == {"channel": "local", "reply_to": {}}


def test_an_app_added_by_someone_the_directory_doesnt_know_or_to_a_team_changes_nothing(stack, bot):
    stranger, team = installation("add"), installation("add")
    stranger["from"] = {"id": "29:1-stranger", "aadObjectId": "0a5a0000-0000-4000-8000-0000000000ff"}
    team["conversation"] = {**team["conversation"], "id": "19:team-channel", "conversationType": "channel"}
    for added in (stranger, team):
        assert httpx.post(bot.url, json=added, headers=bot.auth(aud=WATCHER_APP)).status_code == 200
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from chats").fetchone()["n"] == 0
    forged = installation("add")
    assert httpx.post(bot.url, json=forged).status_code == 401  # only Teams can say so


def test_an_escalation_reaches_teams_too(stack, bot):
    stack.model.reply("Hello, Ana.")
    httpx.post(bot.url, json=activity("Hello"), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()
    stack.suspend(by="ben")
    stack.at("2026-11-09T09:00:00+00:00")  # Ben's Q-1002 was due on Friday, and Ana is next up
    stack.scheduler().work_due()
    escalated = bot.sent[-1]
    assert escalated["text"].startswith("Q-1002, Refund for a duplicate payment, was due on Fri 6 Nov")
    assert "replyToId" not in escalated
    [delivered] = [e for e in stack.ledger() if e["action"] == "deliver"][-1:]
    assert delivered["outcome"] == {"status": "ok", "channel": "teams"}
