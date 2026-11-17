"""Answers people said were wrong (core/feedback.py): a "that's wrong" on an agent's answer, in
the web chat, Slack, Matrix or Teams, which the agent's owners see and grade, as far as they may
see the run behind it."""

import json
import uuid
from dataclasses import replace

import httpx
import pytest

from a5s import db
from a5s.core import feedback, inbox
from a5s.core.matrix import Matrix, MatrixConfig
from a5s.core.slack import Bot as SlackBot
from a5s.core.slack import Slack, SlackConfig
from a5s.core.teams import Bot as TeamsBot
from a5s.core.teams import Teams, TeamsConfig
from conftest import accessible, free_port, listed_runs, serve
from test_matrix import AS_TOKEN, BOT, DM, HS_TOKEN, Homeserver, deliver, invite, said
from test_slack import APP, BOT_USER, SECRET, TEAM, USERS, FakeSlack, event, post
from test_teams import APP_ID, SERVICE_URL, TENANT, FakeBotFramework, activity

ANSWER = "Your invoice went to the old address, Ana; it's due on Wednesday."
MASKED = "Your invoice went to the old address, [someone]; it's due on Wednesday."


def answered(stack, person: str = "ana", text: str = "What's wrong with Q-1001?") -> dict:
    """A message from the web chat, the agent's answer, and the answer as the chat shows it."""
    stack.model.reply(ANSWER)
    message = stack.send(text, person)
    assert stack.scheduler().answer_waiting() == 1
    found = httpx.get(f"{stack.channels_url}/channels/local/messages/{message}",
                      params={"person": person}, timeout=30).json()
    [shown] = found["messages"]
    return shown


def say_wrong(stack, message: int, person: str = "ana", why: str | None = None) -> httpx.Response:
    return httpx.post(f"{stack.channels_url}/channels/local/feedback", timeout=30,
                      json={"message": message, "said": why, "person": person})


def kept(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from answer_feedback order by id").fetchall()


def as_person(approving: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})


def test_someone_says_an_answer_in_the_web_chat_was_wrong_once(stack):
    shown = answered(stack)
    assert shown["by"] == "agent" and isinstance(shown["id"], int)
    first = say_wrong(stack, shown["id"], why="It's due Friday, not Wednesday.")
    assert first.status_code == 200 and first.json() == {"noted": True, "said": feedback.NOTED}
    assert say_wrong(stack, shown["id"]).json()["noted"] is False  # once each
    [row] = kept(stack)
    assert (row["person"], row["agent"], row["channel"], row["said"]) == (
        "ana", "assistant", "local", "It's due Friday, not Wednesday.")
    [noted] = [e for e in stack.ledger() if e["kind"] == "feedback"]
    assert noted["action"] == "wrong" and noted["args"]["chars"] == 31
    assert "Friday" not in json.dumps(noted)  # the ledger keeps their words by hash alone


def test_only_whom_it_answered_says_it_and_only_of_an_agents_answer(stack):
    shown = answered(stack)
    assert say_wrong(stack, shown["id"], person="ben").status_code == 404
    with db.transaction(stack.admin) as conn:  # a5s's own words, written by no run
        notice = conn.execute("insert into outbox (person, channel, text) values ('ana', 'local', "
                              "'a5s: the model is back.') returning id").fetchone()["id"]
    assert say_wrong(stack, notice).status_code == 404
    assert kept(stack) == []


def test_its_owners_see_what_was_said_and_grade_it(stack, approving, provider):
    listed_runs(stack)  # an instance whose runs the studio shows one by one
    shown = answered(stack)
    say_wrong(stack, shown["id"], why="Ana here: it's due Friday, ask ben@example.com.")
    found = as_person(approving, provider, "priya", "GET", "/studio/api/agents/assistant/feedback")
    assert found.status_code == 200, found.text
    body = found.json()
    [answer] = body["answers"]
    assert (answer["answer"], answer["said"], answer["grade"], answer["channel"]) == (
        MASKED, "[someone] here: it's due Friday, ask [an email].", None, "local")
    assert answer["by"] is None  # who said it, only once the officer agrees to names
    assert (body["waiting"], body["hidden"]) == (1, 0)
    home = as_person(approving, provider, "priya", "GET", "/studio/api/home").json()
    assert any(w["kind"] == "feedback" and w["go"] == "/studio/agents/assistant#feedback"
               for w in home["waiting"])
    graded = as_person(approving, provider, "priya", "POST",
                       f"/studio/api/feedback/{answer['id']}/grade", {"grade": "wrong"})
    assert graded.status_code == 200 and graded.json() == {"id": answer["id"], "grade": "wrong"}
    after = as_person(approving, provider, "priya", "GET",
                      "/studio/api/agents/assistant/feedback").json()
    assert (after["waiting"], after["graded"]) == (0, {"wrong": 1})
    assert after["answers"][0]["graded_by"] == "Priya Nair"
    [grade] = [e for e in stack.ledger() if e["kind"] == "feedback" and e["action"] == "grade"]
    assert grade["args"]["grade"] == "wrong"


def test_nobody_but_its_owners_sees_or_grades_it(stack, approving, provider):
    shown = answered(stack)
    say_wrong(stack, shown["id"])
    [row] = kept(stack)
    assert as_person(approving, provider, "ana", "GET",
                     "/studio/api/agents/assistant/feedback").status_code == 404
    assert as_person(approving, provider, "ana", "POST", f"/studio/api/feedback/{row['id']}/grade",
                     {"grade": "right"}).status_code == 404
    assert as_person(approving, provider, "priya", "POST", f"/studio/api/feedback/{row['id']}/grade",
                     {"grade": "fine"}).status_code == 400


def test_an_answer_from_records_its_owner_may_not_see_stays_out_of_their_sight(stack, approving,
                                                                               provider):
    listed_runs(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))  # billing's: finance's alone
    shown = answered(stack)
    say_wrong(stack, shown["id"])
    body = as_person(approving, provider, "priya", "GET",
                     "/studio/api/agents/assistant/feedback").json()
    assert (body["answers"], body["hidden"], body["waiting"]) == ([], 1, 0)
    [row] = kept(stack)
    assert as_person(approving, provider, "priya", "POST", f"/studio/api/feedback/{row['id']}/grade",
                     {"grade": "right"}).status_code == 404


def checks(approving, provider, person: str = "priya") -> dict:
    return as_person(approving, provider, person, "GET",
                     "/studio/api/agents/assistant/feedback").json()


def test_a_record_the_answer_or_their_words_name_keeps_it_from_whoever_may_not_see_it(
        stack, approving, provider):
    listed_runs(stack)
    stack.model.reply("Q-1002's refund went out on Monday.")  # billing's, from what it was told
    first = stack.send("Where's my refund?", "ana")
    assert stack.scheduler().answer_waiting() == 1
    [said] = [m for m in httpx.get(f"{stack.channels_url}/channels/local/messages/{first}",
                                   params={"person": "ana"}, timeout=30).json()["messages"]]
    say_wrong(stack, said["id"])
    shown = answered(stack, text="And my invoice?")
    say_wrong(stack, shown["id"], why="It's Q-1004's, not mine.")  # their words name one
    body = checks(approving, provider)
    assert (body["answers"], body["hidden"], body["waiting"]) == ([], 2, 0)
    for row in kept(stack):
        assert as_person(approving, provider, "priya", "POST",
                         f"/studio/api/feedback/{row['id']}/grade",
                         {"grade": "right"}).status_code == 404
    home = as_person(approving, provider, "priya", "GET", "/studio/api/home").json()
    assert not [w for w in home["waiting"] if w["kind"] == "feedback"]


def test_an_instance_serving_few_shows_none_until_the_officer_agrees_to_names(stack, approving,
                                                                            provider):
    shown = answered(stack)  # Ana's and Ben's assistant: two people, fewer than five
    say_wrong(stack, shown["id"], why="Wrong date.")
    body = checks(approving, provider)
    assert (body["answers"], body["hidden"], body["waiting"]) == ([], 1, 0)
    [row] = kept(stack)
    assert as_person(approving, provider, "priya", "POST", f"/studio/api/feedback/{row['id']}/grade",
                     {"grade": "right"}).status_code == 404
    home = as_person(approving, provider, "priya", "GET", "/studio/api/home").json()
    assert not [w for w in home["waiting"] if w["kind"] == "feedback"]
    assert not stack.settle(data_protection={"studio_names": True},
                            signers=("ana", "noor")).refused
    [answer] = checks(approving, provider)["answers"]  # named, and so shown as it was said
    assert (answer["answer"], answer["said"], answer["by"]) == (ANSWER, "Wrong date.", "Ana Ortiz")


def test_what_someone_said_is_theirs_kept_exported_and_erased(stack):
    shown = answered(stack)
    say_wrong(stack, shown["id"], why="Wrong date.")
    with stack.client() as c:
        found = c.post("/people/ana/export", json={"by": "noor", "identity": None}).json()
    [said] = found["said_wrong"]
    assert (said["agent"], said["said"], said["answer"]) == ("assistant", "Wrong date.", ANSWER)
    with db.transaction(stack.admin) as conn:
        conn.execute("update answer_feedback set at = at - interval '13 months'")
    with stack.client() as c:
        assert c.post("/retention/sweep").json()["deleted"]["feedback"] == 1
    assert kept(stack) == []


# Slack, Matrix and Teams: a 👎 on what the agent's bot said


@pytest.fixture
def slack_app(stack):
    fake = FakeSlack()
    for person, user in USERS.items():
        found = stack.gateway.scenario._people[person]
        stack.gateway.scenario._people[person] = replace(
            found, identities=(*found.identities, f"slack:{TEAM}/{user}"))
    cfg = SlackConfig(bots=(SlackBot("assistant", APP, SECRET, "xoxb-assistant"),),
                      team_id=TEAM, api="https://slack.test/api")
    stack.gateway.slack = Slack(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with serve(inbox.create_app(replace(stack.gateway, cfg=stack.as_role("channels"))),
               free_port()) as url:
        fake.url = f"{url}/channels/slack/events"
        yield fake


def reaction(item_ts: str, user: str = USERS["ana"], name: str = "-1") -> dict:
    return {"type": "event_callback", "team_id": TEAM, "api_app_id": APP,
            "event_id": f"Ev{uuid.uuid4().hex[:8]}",
            "authorizations": [{"team_id": TEAM, "user_id": BOT_USER, "is_bot": True}],
            "event": {"type": "reaction_added", "user": user, "reaction": name,
                      "item": {"type": "message", "channel": "D0ANA", "ts": item_ts},
                      "item_user": BOT_USER}}


def test_a_thumbs_down_in_slack_says_the_answer_was_wrong(stack, slack_app):
    stack.model.reply(ANSWER)
    assert post(slack_app.url, event()).status_code == 200
    assert stack.scheduler().answer_waiting() == 1
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select sent_as from outbox where channel = 'slack'").fetchall()
    channel, ts = row["sent_as"].split("/")
    assert channel == "D0ANA"
    assert post(slack_app.url, reaction(ts, user=USERS["ben"])).status_code == 200  # not his
    assert post(slack_app.url, reaction(ts, name="tada")).status_code == 200  # not a 👎
    assert kept(stack) == []
    assert post(slack_app.url, reaction(ts)).status_code == 200
    [said] = kept(stack)
    assert (said["person"], said["channel"], said["said"]) == ("ana", "slack", None)
    told = [m for m in slack_app.sent if m["method"] == "chat.postEphemeral"]
    assert [m["text"] for m in told] == [feedback.NOTED] and told[0]["user"] == USERS["ana"]


class Answering(Homeserver):
    """A homeserver that gives each event a5s sends its own id, as Synapse does."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        answer = super().handler(request)
        if "/send/m.room.message/" in request.url.path and answer.status_code == 200:
            self.sent[-1]["event_id"] = f"$sent{len(self.sent)}"
            return httpx.Response(200, json={"event_id": f"$sent{len(self.sent)}"})
        return answer


def test_a_thumbs_down_in_matrix_says_the_answer_was_wrong(stack):
    fake = Answering()
    cfg = MatrixConfig("https://matrix.test", "a5s.test", AS_TOKEN, HS_TOKEN)
    stack.gateway.matrix = Matrix(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with serve(inbox.create_app(replace(stack.gateway, cfg=stack.as_role("channels"))),
               free_port()) as url:
        fake.url = f"{url}/channels/matrix/_matrix/app/v1"
        assert deliver(fake, invite()).status_code == 200
        stack.model.reply(ANSWER)
        assert deliver(fake, said("What's wrong with Q-1001?")).status_code == 200
        assert stack.scheduler().answer_waiting() == 1
        [answer] = fake.sent
        assert deliver(fake, {
            "type": "m.reaction", "sender": "@ana:a5s.test", "room_id": DM,
            "event_id": f"${uuid.uuid4().hex}", "content": {"m.relates_to": {
                "rel_type": "m.annotation", "event_id": answer["event_id"],
                "key": "👎"}}}).status_code == 200
    [row] = kept(stack)
    assert (row["person"], row["channel"]) == ("ana", "matrix")
    assert fake.sent[-1] == {"room": DM, "as": BOT, "body": feedback.NOTED,
                             "event_id": "$sent2"}


@pytest.fixture
def teams_bot(stack):
    fake = FakeBotFramework()
    cfg = TeamsConfig(bots=(TeamsBot("assistant", APP_ID, "bot-secret"),), tenant_id=TENANT,
                      service_hosts=("smba.test",), login_url="https://login.test",
                      metadata_url="https://login.botframework.test/v1/.well-known/openidconfiguration")
    stack.gateway.teams = Teams(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with serve(inbox.create_app(replace(stack.gateway, cfg=stack.as_role("channels"))),
               free_port()) as url:
        fake.url = f"{url}/channels/teams/messages"
        yield fake


def test_teams_buttons_on_an_answer_say_it_was_wrong_with_why(stack, teams_bot):
    stack.model.reply(ANSWER)
    message = activity("What's wrong with Q-1001?")
    assert httpx.post(teams_bot.url, json=message, headers=teams_bot.auth()).status_code == 200
    assert stack.scheduler().answer_waiting() == 1
    [sent] = teams_bot.sent
    assert sent["channelData"] == {"feedbackLoop": {"type": "default"}}  # its buttons
    invoke = {**activity(""), "type": "invoke", "name": "message/submitAction",
              "replyToId": "reply-1", "value": {"actionName": "feedback", "actionValue": {
                  "reaction": "dislike", "feedback": json.dumps({"feedbackText": "Due Friday."})}}}
    answer = httpx.post(teams_bot.url, json=invoke, headers=teams_bot.auth())
    assert answer.status_code == 200 and answer.json()["value"] == feedback.NOTED
    [row] = kept(stack)
    assert (row["person"], row["channel"], row["said"]) == ("ana", "teams", "Due Friday.")
    liked = {**invoke, "value": {"actionName": "feedback", "actionValue": {"reaction": "like"}}}
    assert httpx.post(teams_bot.url, json=liked, headers=teams_bot.auth()).json()["value"] == "Thanks."
    assert len(kept(stack)) == 1 and SERVICE_URL in invoke["serviceUrl"]


# In the browser


def test_the_web_chat_asks_why_and_its_owners_grade_it_on_the_agents_page(stack, approving, provider,
                                                                          browser):
    listed_runs(stack)
    stack.model.reply(ANSWER)
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/chat/")
    page.wait_for_selector("#compose", timeout=30000)
    page.fill("#text", "What's wrong with Q-1001?")
    page.keyboard.press("Enter")
    assert stack.scheduler().answer_waiting() == 1
    page.wait_for_selector("li.agent >> text=old address", timeout=30000)
    page.click("li.agent button.said-wrong")
    assert "Its owners will see this answer" in page.inner_text("li.agent form.said-wrong")
    page.fill("li.agent form.said-wrong textarea", "It's due Friday.")
    page.click("li.agent form.said-wrong button.primary")
    page.wait_for_selector(f"li.agent p.said-wrong >> text={feedback.NOTED[:20]}", timeout=30000)
    [row] = kept(stack)
    assert row["said"] == "It's due Friday."

    provider.person = "priya"
    owner = browser.new_page(viewport={"width": 1280, "height": 900})
    owner.goto(f"{approving}/studio/agents/assistant#feedback")
    owner.wait_for_selector("#feedback [data-said-wrong]", timeout=30000)
    assert "It's due Friday." in owner.inner_text("#feedback")
    accessible(owner)
    owner.click("#feedback .grades button.critical")
    owner.wait_for_selector("#feedback .grades button.critical[aria-pressed=true]", timeout=30000)
    assert kept(stack)[0]["grade"] == "critical"
