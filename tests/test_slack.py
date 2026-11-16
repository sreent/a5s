"""Slack: the core receives each event itself, checks its signature, and answers only through the
core, as each agent's own app."""

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import replace

import httpx
import pytest

from a5s import db
from a5s.core import groups, inbox, slack
from a5s.core.slack import Bot, Slack, SlackConfig
from conftest import eventually, free_port, serve

TEAM, APP, WATCHER_APP = "T0A5S", "A0ASSIST", "A0WATCH"
SECRET, WATCHER_SECRET = "assistant-signing-secret", "watcher-signing-secret"
BOT_USER = "U0BOT"  # the assistant's bot, as Slack knows it
USERS = {"ana": "U0ANA", "ben": "U0BEN", "chen": "U0CHEN"}
DM, GROUP_DM, CHANNEL = "D0ANA", "C0GROUP", "C0GENERAL"


class FakeSlack:
    """Slack's Web API, as each app's bot calls it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.members: dict[str, list[str]] = {GROUP_DM: [USERS["ana"], USERS["ben"], BOT_USER]}
        self.kinds = {DM: {"is_im": True}, GROUP_DM: {"is_mpim": True}, CHANNEL: {}}
        self.opened: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        form = dict(httpx.QueryParams(request.content.decode()))
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if method in ("chat.postMessage", "chat.postEphemeral"):
            self.sent.append({**form, "method": method, "as": token})
            return httpx.Response(200, json={"ok": True, "ts": f"{time.time():.6f}"})
        if method == "conversations.members":
            return httpx.Response(200, json={"ok": True, "members": self.members.get(form["channel"], [])})
        if method == "conversations.info":
            return httpx.Response(200, json={"ok": True, "channel": self.kinds.get(form["channel"], {})})
        if method == "conversations.open":
            self.opened.append(form)
            return httpx.Response(200, json={"ok": True, "channel": {"id": f"D0NEW{len(self.opened)}"}})
        if method == "users.info":
            return httpx.Response(200, json={"ok": True, "user": {"real_name": "Mallory Moss"}})
        if method == "auth.test":
            return httpx.Response(200, json={"ok": True, "user_id": BOT_USER})
        return httpx.Response(200, json={"ok": False, "error": "unknown_method"})


def event(text: str = "Which questions mention an invoice?", *, user: str = USERS["ana"],
          channel: str = DM, kind: str = "im", team: str = TEAM, app: str = APP,
          etype: str = "message", **more) -> dict:
    return {"type": "event_callback", "team_id": team, "api_app_id": app,
            "event_id": f"Ev{uuid.uuid4().hex[:8]}",
            "authorizations": [{"team_id": team, "user_id": BOT_USER, "is_bot": True}],
            "event": {"type": etype, "user": user, "text": text, "channel": channel,
                      "channel_type": kind, "ts": f"{time.time():.6f}", **more}}


def signed(body: bytes, secret: str = SECRET, at: int | None = None) -> dict[str, str]:
    stamp = str(int(time.time()) if at is None else at)
    mac = hmac.new(secret.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": stamp, "X-Slack-Signature": f"v0={mac}",
            "Content-Type": "application/json"}


def post(url: str, payload: dict, **signing) -> httpx.Response:
    body = json.dumps(payload).encode()
    return httpx.post(url, content=body, headers=signed(body, **signing))


@pytest.fixture
def chat(stack):
    fake = FakeSlack()
    for person, user in USERS.items():  # each person's Slack account, as the directory lists it
        found = stack.gateway.scenario._people[person]
        stack.gateway.scenario._people[person] = replace(
            found, identities=(*found.identities, f"slack:{TEAM}/{user}"))
    cfg = SlackConfig(bots=(Bot("assistant", APP, SECRET, "xoxb-assistant"),
                            Bot("watcher", WATCHER_APP, WATCHER_SECRET, "xoxb-watcher")),
                      team_id=TEAM, api="https://slack.test/api")
    stack.gateway.slack = Slack(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/slack/events"
        yield fake


def queued(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from inbound order by received_at").fetchall()


def test_a_direct_message_is_checked_recorded_and_answered_as_the_agents_app(stack, chat):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    said = event()
    assert post(chat.url, said).status_code == 200
    [row] = queued(stack)
    assert row["person"] == "ana" and row["channel"] == "slack" and row["text"] == said["event"]["text"]
    assert stack.scheduler().answer_waiting() == 1
    [sent] = chat.sent
    assert (sent["channel"], sent["text"], sent["as"]) == (DM, "Q-1001 mentions an invoice.", "xoxb-assistant")
    assert "thread_ts" not in sent
    received = next(e for e in stack.ledger() if e["kind"] == "inbound")
    assert received["args"]["identity"] == "verified by slack"
    assert post(chat.url, said).status_code == 200  # Slack sends it again: answered once
    assert stack.scheduler().answer_waiting() == 0 and len(chat.sent) == 1


@pytest.mark.parametrize("case", ["no signature", "another app's secret", "five minutes ago",
                                  "another workspace", "another app than signed it"])
def test_what_doesnt_check_out_is_refused_and_never_queued(stack, chat, case):
    said = event(team="T0OTHER" if case == "another workspace" else TEAM,
                 app=WATCHER_APP if case == "another app than signed it" else APP)
    body = json.dumps(said).encode()
    headers = {"no signature": {"Content-Type": "application/json"},
               "another app's secret": signed(body, secret="not-a5s's"),
               "five minutes ago": signed(body, at=int(time.time()) - 301)}.get(case, signed(body))
    answer = httpx.post(chat.url, content=body, headers=headers)
    assert answer.status_code in (401, 403), (case, answer.text)
    assert not queued(stack) and not chat.sent


def test_slack_sets_up_its_events_with_a_signed_challenge(stack, chat):
    answer = post(chat.url, {"type": "url_verification", "challenge": "c-123", "token": "x"})
    assert answer.status_code == 200 and answer.json() == {"challenge": "c-123"}
    body = json.dumps({"type": "url_verification", "challenge": "c-123"}).encode()
    assert httpx.post(chat.url, content=body, headers=signed(body, secret="nobody's")).status_code == 403


def test_someone_the_directory_doesnt_know_is_told_so_and_nothing_runs(stack, chat):
    assert post(chat.url, event(user="U0STRANGER")).status_code == 200
    assert not queued(stack)
    assert eventually(lambda: chat.sent)
    assert [m["text"] for m in chat.sent] == [slack.mrkdwn(slack.UNKNOWN)]


def test_a_mention_in_a_channel_is_answered_to_its_sender_alone_and_nothing_runs(stack, chat):
    said = event(f"<@{BOT_USER}> what's due today?", channel=CHANNEL, etype="app_mention")
    assert post(chat.url, said).status_code == 200
    assert not queued(stack)
    assert eventually(lambda: chat.sent)
    [told] = chat.sent
    assert told["method"] == "chat.postEphemeral" and told["user"] == USERS["ana"]
    assert told["text"] == slack.mrkdwn(slack.CHANNELS)


def test_in_a_group_dm_it_answers_only_what_mentions_it_and_knows_whos_there(stack, chat):
    assert post(chat.url, event("Lunch at one?", channel=GROUP_DM, kind="mpim")).status_code == 200
    assert not queued(stack)  # not for the agent
    said = event(f"<@{BOT_USER}> which questions mention an invoice?", channel=GROUP_DM, kind="mpim")
    assert post(chat.url, said).status_code == 200
    [row] = queued(stack)
    assert row["text"] == "which questions mention an invoice?"
    assert row["members"] == ["ana", "ben"] and row["conversation"].startswith("group:")  # as a5s keeps a group


def test_a_stranger_in_a_group_dm_stops_it_by_name(stack, chat):
    chat.members[GROUP_DM].append("U0MALLORY")
    said = event(f"<@{BOT_USER}> what's due?", channel=GROUP_DM, kind="mpim")
    assert post(chat.url, said).status_code == 200
    assert not queued(stack)
    assert eventually(lambda: chat.sent)
    assert chat.sent[0]["text"] == slack.mrkdwn(groups.STRANGERS.format(who="Mallory Moss"))


def test_words_sent_with_a_file_are_read_as_typed_and_the_file_never(stack, chat):
    said = event("Which questions mention an invoice?", subtype="file_share",
                 files=[{"id": "F0SHOT", "name": "screenshot.png"}])
    assert post(chat.url, said).status_code == 200
    [row] = queued(stack)
    assert row["text"] == "Which questions mention an invoice?"
    assert "F0SHOT" not in json.dumps(row["reply_to"])


def test_apps_own_messages_edits_and_joins_are_left_alone(stack, chat):
    for said in (event(bot_id="B0OTHER"), event(subtype="message_changed"),
                 event(subtype="channel_join"), event(user=BOT_USER)):
        assert post(chat.url, said).status_code == 200
    assert not queued(stack) and not chat.sent


def test_what_a5s_says_in_slack_mentions_nobody_and_links_only_as_written():
    said = slack.mrkdwn("Tell <!channel> & <@U0BEN>: see [Q-1001](https://a5s.test/records/Q-1001), **now**")
    assert "<!channel>" not in said and "<@U0BEN>" not in said
    assert "&lt;!channel&gt; &amp; &lt;@U0BEN&gt;" in said
    assert "<https://a5s.test/records/Q-1001|Q-1001>" in said and "*now*" in said


def test_an_approval_card_is_its_words_and_a_button_that_only_opens_its_page():
    card = {"type": "AdaptiveCard", "body": [
        {"type": "TextBlock", "text": "Settings to approve", "weight": "Bolder"},
        {"type": "TextBlock", "text": "Version 4 waits for you.", "isSubtle": True}],
        "actions": [{"type": "Action.OpenUrl", "title": "Review and approve", "url": "https://a5s.test/studio/approve"}]}
    drawn = slack.blocks(card)
    assert drawn[0] == {"type": "section", "text": {"type": "mrkdwn", "text": "*Settings to approve*"}}
    assert drawn[1]["type"] == "context"
    [button] = drawn[2]["elements"]
    assert button["url"] == "https://a5s.test/studio/approve" and "value" not in button
    long = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "- a change\n" * 600}]}
    [section] = slack.blocks(long)  # what Slack would refuse whole, cut and said so
    assert len(section["text"]["text"]) <= slack.BLOCK and section["text"]["text"].endswith("…")


def test_a_reminder_opens_a_direct_message_with_the_person_who_last_wrote_in_slack(stack, chat):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    post(chat.url, event()).raise_for_status()
    stack.scheduler().answer_waiting()
    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    reminder = chat.sent[-1]
    assert reminder["text"] == "Ana, Q-1001 is due on Wednesday." and reminder["channel"] == DM
    assert "thread_ts" not in reminder  # a message of its own, not a reply
    assert [m["text"] for m in stack.inbox("ben")] == ["Ben, Q-1002 is due on Friday."]  # no chat yet
