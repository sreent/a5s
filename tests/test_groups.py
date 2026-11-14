"""Group conversations. People bring an agent into a group chat, a Matrix room or a Teams group
chat of up to 20 people the directory knows, and it answers whoever mentions it there. A run
acts for everyone in the chat, so it sees only what all of them may see, and is given only
what everyone now in the chat heard. What's one person's own stays one to one: a reminder
asked for in a group is the asker's alone, and an agent never writes first into a group."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import unquote

import httpx
import pytest

from a5s import db, definitions
from a5s.config import load_models
from a5s.core import departures, groups, inbox, topics
from a5s.core.matrix import Matrix, MatrixConfig
from a5s.core.teams import Bot, Teams, TeamsConfig
from a5s.services import context
from conftest import ROOT, FakeModel, build_root, eventually, free_port, live_image, running, serve
from test_matrix import AS_TOKEN, BOT, HS_TOKEN, Homeserver, deliver, invite, said
from test_teams import ANA as ANA_ENTRA
from test_teams import APP_ID, TENANT, WATCHER_APP, FakeBotFramework, activity
from test_teams import BEN as BEN_ENTRA

ANA, BEN, CHEN = "@ana:a5s.test", "@ben:a5s.test", "@chen:a5s.test"
ROOM = "!team:a5s.test"
GROUP = groups.key("matrix", ROOM)
ASKED = "Which questions mention an invoice?"


class GroupHomeserver(Homeserver):
    """A homeserver whose rooms also say who may read what was said before they joined."""

    def __init__(self) -> None:
        super().__init__()
        self.rooms[ROOM] = {ANA, BEN}
        self.history: dict[str, str] = {ROOM: "joined"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        if path.endswith("/state/m.room.history_visibility"):
            room = path.split("/rooms/")[-1].split("/")[0]
            if room not in self.history:
                return httpx.Response(404, json={"errcode": "M_NOT_FOUND"})
            return httpx.Response(200, json={"history_visibility": self.history[room]})
        return super().handler(request)


@contextmanager
def group_room(stack) -> Iterator[GroupHomeserver]:
    """The homeserver, with the room Ana brings the assistant into, with Ben."""
    fake = GroupHomeserver()
    cfg = MatrixConfig("https://matrix.test", "a5s.test", AS_TOKEN, HS_TOKEN)
    stack.gateway.matrix = Matrix(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/matrix/_matrix/app/v1"
        deliver(fake, invite(room=ROOM))
        yield fake


@pytest.fixture
def homeserver(stack):
    with group_room(stack) as fake:
        yield fake


def mention(text: str, by: str = ANA) -> dict:
    """A message in the room that mentions the assistant, as Element sends one."""
    return said(f"a5s-assistant: {text}", by=by, room=ROOM, **{"m.mentions": {"user_ids": [BOT]}})


def queued(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from inbound where conversation is not null "
                            "order by received_at").fetchall()


def messages(stack, request: int = -1) -> list[dict]:
    return stack.model.requests[request]["body"]["messages"]


def test_a_mention_in_a_group_room_is_answered_there_for_everyone_in_it(stack, homeserver):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    assert deliver(homeserver, mention(ASKED)).status_code == 200
    [row] = queued(stack)
    assert (row["person"], row["conversation"], row["members"], row["text"]) == (
        "ana", GROUP, ["ana", "ben"], ASKED)
    assert stack.scheduler().answer_waiting() == 1
    assert homeserver.sent[-1] == {"room": ROOM, "as": BOT, "body": "Q-1001 mentions an invoice."}
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select acts_for, trigger from runs").fetchall()
        turns = conn.execute("select person, speaker, heard_by, role from turns order by id").fetchall()
    assert run["acts_for"] == ["ana", "ben"] and run["trigger"]["conversation"] == GROUP
    assert [(t["person"], t["speaker"], t["heard_by"], t["role"]) for t in turns] == [
        (GROUP, "ana", ["ana", "ben"], "person"), (GROUP, None, ["ana", "ben"], "agent")]
    told = messages(stack, 0)
    assert "Who you're working for: everyone in this group chat" in told[0]["content"]
    assert "Ana Ortiz (who asked), Ben Okafor" in told[0]["content"]
    assert told[-1]["role"] == "user" and told[-1]["content"].endswith(f"] Ana Ortiz: {ASKED}")
    with db.transaction(stack.admin) as conn:  # the day's budget it used is the asker's
        assert [r["person"] for r in conn.execute("select person from spend")] == ["ana"]


def test_what_doesnt_mention_the_agent_isnt_heard(stack, homeserver):
    deliver(homeserver, said("Lunch at one?", room=ROOM))
    assert queued(stack) == [] and homeserver.sent == []


def test_a_run_in_a_group_sees_only_what_everyone_in_it_may_see(stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    homeserver.rooms[ROOM] = {ANA, CHEN, BOT}  # Chen, in operations, may not see billing
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("I can't find one we may all see.")
    deliver(homeserver, mention(ASKED))
    assert stack.scheduler().answer_waiting() == 1
    found = json.loads(messages(stack)[-1]["content"])
    assert "Q-1001" not in json.dumps(found)  # Ana's billing question, which Chen may not see


def test_nobody_added_later_is_given_what_was_said_before(stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    stack.model.reply("Q-1001 is about an invoice.")
    deliver(homeserver, mention("What's Q-1001 about?"))
    stack.scheduler().answer_waiting()
    homeserver.rooms[ROOM].add(CHEN)  # Chen joins
    stack.model.reply("Hello, Chen.")
    deliver(homeserver, mention("Say hello to Chen", by=BEN))
    stack.scheduler().answer_waiting()
    given = json.dumps(messages(stack))
    assert "Q-1001" not in given and "Ben Okafor: Say hello to Chen" in given
    homeserver.rooms[ROOM].discard(CHEN)  # once Chen has gone, what Ana and Ben heard is theirs
    stack.model.reply("Yes.")
    deliver(homeserver, mention("Do you remember Q-1001?"))
    stack.scheduler().answer_waiting()
    assert "Q-1001 is about an invoice." in json.dumps(messages(stack))


def test_an_answer_someone_joined_during_goes_to_whoever_asked_instead(stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    stack.model.on_request = lambda n: homeserver.rooms[ROOM].add(CHEN)  # Chen joins meanwhile
    stack.model.reply("Q-1001 is Northwind's question about an invoice.")
    deliver(homeserver, mention("What's Q-1001?"))
    stack.scheduler().answer_waiting()
    [started] = homeserver.started  # a chat of her own with the assistant, on Matrix, where
    in_room = [m["body"] for m in homeserver.sent if m["room"] == ROOM]  # she talks to it
    assert in_room == [groups.JOINED.format(where="it's in a chat of their own with me")]
    assert [m["body"] for m in homeserver.sent if m["room"] == started["room"]] == [
        "Q-1001 is Northwind's question about an invoice."]  # not the room Chen joined
    assert started["invite"] == [ANA]
    assert [e for e in stack.ledger() if e["action"] == "kept back"]
    with db.transaction(stack.admin) as conn:  # the group's conversation keeps it as hers alone
        turns = conn.execute("select role, heard_by from turns where person = %s order by id",
                             (GROUP,)).fetchall()
    assert [(t["role"], t["heard_by"]) for t in turns] == [
        ("person", ["ana", "ben"]), ("notice", ["ana", "ben", "chen"]), ("agent", ["ana"])]


def test_a_reminder_asked_for_in_a_group_is_the_askers_alone(stack, homeserver):
    stack.model.reply(None, ("offer_reminder", {"about": "call Northwind", "on": "2026-11-02"}))
    stack.model.reply("Shall I remind you on Monday, Ana?")
    deliver(homeserver, mention("Remind me to call Northwind on Monday"))
    stack.scheduler().answer_waiting()
    stack.model.reply(None, ("confirm_reminder", {}))  # Ben can't say yes for her
    stack.model.reply("Only Ana can.")
    deliver(homeserver, mention("Yes", by=BEN))
    stack.scheduler().answer_waiting()
    with db.transaction(stack.admin) as conn:
        [offer] = conn.execute("select * from reminders").fetchall()
    assert (offer["person"], offer["conversation"], offer["confirmed_at"]) == ("ana", GROUP, None)
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Set.")
    deliver(homeserver, mention("Yes, please"))
    stack.scheduler().answer_waiting()
    assert "What you offered Ana Ortiz here, waiting for their yes" in messages(stack)[0]["content"]
    with db.transaction(stack.admin) as conn:
        [kept] = conn.execute("select * from reminders").fetchall()
        route = stack.gateway.reach(conn, "ana", "assistant")
    assert kept["confirmed_at"] is not None
    assert route["reply_to"].get("room") != ROOM  # it reaches her alone, never the group


def test_whats_one_persons_own_is_asked_for_one_to_one(stack, homeserver):
    stack.model.reply("Ask me one to one.")
    deliver(homeserver, mention("Note that I like short answers, and list my reminders"))
    stack.scheduler().answer_waiting()
    offered = set(stack.model.tool_names(-1))  # not offered in a group, so never refused there
    assert not offered & {"offer_note", "list_reminders"}
    with stack.client() as c:  # and refused, were it asked for all the same
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select id::text from inbound").fetchall()
            conn.execute("update inbound set answered_at = null where id = %s", (row["id"],))
        token = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": row["id"]}}).json()["token"]
    with stack.client(token) as c:
        refused = c.post("/run/tools/offer_note", json={"args": {"note": "Short answers."}})
    assert refused.status_code == 403
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from profile_notes").fetchone()["n"] == 0


def test_a_group_the_agent_doesnt_serve_everyone_in_hears_so(stack, homeserver):
    homeserver.rooms[ROOM] = {ANA, CHEN, BOT}  # the assistant serves Ana and Ben, not Chen
    deliver(homeserver, mention(ASKED))
    stack.scheduler().answer_waiting()
    assert homeserver.sent[-1]["body"] == groups.UNSERVED.format(  # whom, and who adds them
        who="Chen Wei", add="As the owner of the parts it works in, you can add them.")
    assert stack.model.requests == []


@pytest.mark.parametrize("case", ["history shown", "shown from invitation", "a stranger",
                                  "too many"])
def test_a_room_the_agent_cant_work_in_hears_why(stack, homeserver, monkeypatch, case):
    if case == "history shown":
        homeserver.history[ROOM] = "shared"
    elif case == "shown from invitation":  # to people the run wasn't for, once they join
        homeserver.history[ROOM] = "invited"
    elif case == "a stranger":
        homeserver.rooms[ROOM].add("@stranger:a5s.test")
    else:
        monkeypatch.setattr(groups, "LIMIT", 1)
    deliver(homeserver, mention(ASKED))
    assert queued(stack) == []
    assert eventually(lambda: homeserver.sent)  # told after the 200, in the background
    assert homeserver.sent[-1]["body"] == {"history shown": groups.HISTORY,
                                           "shown from invitation": groups.HISTORY,
                                           "a stranger": groups.STRANGERS.format(
                                               who="@stranger:a5s.test"),
                                           "too many": groups.TOO_MANY}[case]


def test_someone_who_leaves_keeps_their_words_in_the_group_under_the_archives_name(
        stack, homeserver):
    stack.model.reply("Noted.")
    deliver(homeserver, mention("Q-1002 is mine", by=BEN))
    stack.scheduler().answer_waiting()
    with db.transaction(stack.admin) as conn:
        name = departures.archive(conn, "ben", datetime.now(UTC))
        turns = conn.execute("select person, speaker, heard_by from turns order by id").fetchall()
        [row] = conn.execute("select person, members from inbound where conversation = %s",
                             (GROUP,)).fetchall()
    assert [(t["person"], t["speaker"], t["heard_by"]) for t in turns] == [
        (GROUP, name, ["ana", name]), (GROUP, None, ["ana", name])]
    assert (row["person"], row["members"]) == (name, ["ana", name])


def test_whoever_said_a_turn_is_named_even_once_theyve_left_the_room(stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    homeserver.rooms[ROOM].add(CHEN)
    stack.model.reply("Hello, Chen.")
    deliver(homeserver, mention("Hello from operations", by=CHEN))
    stack.scheduler().answer_waiting()
    homeserver.rooms[ROOM].discard(CHEN)  # Chen leaves the room, not the organisation
    stack.model.reply("Chen did.")
    deliver(homeserver, mention("Who said hello?"))
    stack.scheduler().answer_waiting()
    assert "Chen Wei: Hello from operations" in json.dumps(messages(stack))


def test_a_run_after_one_that_read_outside_content_in_the_group_is_marked_too(
        stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused

    def marked(n: int) -> None:  # as if the run had read a customer's email
        if n == 1:
            with db.transaction(stack.admin) as conn:
                conn.execute("update runs set read_outside = true")

    stack.model.on_request = marked
    stack.model.reply("Q-1001 is about an invoice.")
    deliver(homeserver, mention("What's Q-1001 about?"))
    stack.scheduler().answer_waiting()
    stack.model.on_request = None
    stack.model.reply("You're welcome.")
    deliver(homeserver, mention("Thanks", by=BEN))  # it's given what the marked run said
    stack.scheduler().answer_waiting()
    homeserver.rooms[ROOM].add(CHEN)  # who didn't hear it, so a run for all three isn't given it
    stack.model.reply("Hello, Chen.")
    deliver(homeserver, mention("Say hello to Chen", by=BEN))
    stack.scheduler().answer_waiting()
    with db.transaction(stack.admin) as conn:
        runs = conn.execute("select acts_for, read_outside from runs order by opened_at").fetchall()
    assert [(r["acts_for"], r["read_outside"]) for r in runs] == [
        (["ana", "ben"], True), (["ana", "ben"], True), (["ana", "ben", "chen"], False)]


# A group's summary: of what everyone in it heard

OLD = "Contoso's refund for Q-1002 is £1,240.50, due by 2026-11-06."


def a_long_group_conversation(stack) -> None:
    """Ana and Ben's earlier turns in the room, more than a run with a small budget is given."""
    with db.transaction(stack.admin) as conn:
        context.add_turn(conn, person=GROUP, agent="assistant", role="person", content=OLD,
                         speaker="ben", heard_by=["ana", "ben"])
        context.add_turn(conn, person=GROUP, agent="assistant", role="agent", content="Noted.",
                         heard_by=["ana", "ben"])
        for n in range(5):
            context.add_turn(conn, person=GROUP, agent="assistant", role="person",
                             content=f"Note {n}: " + "the weekly sync went through invoices. " * 25,
                             speaker="ana", heard_by=["ana", "ben"])
    stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters


def folded(decisions: list[str]) -> str:
    return json.dumps({"decisions": decisions, "commitments": [], "open_questions": []})


def group_summaries(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from summaries where person = %s", (GROUP,)).fetchall()


def answering(stack) -> list[list[dict]]:
    """What the agent's own runs were sent, not a5s's summary runs."""
    return [r["body"]["messages"] for r in stack.model.requests
            if r["body"]["messages"][0]["content"] != topics.SUMMARY]


def test_a_long_group_conversation_is_summarised_for_everyone_who_heard_it(stack, homeserver):
    a_long_group_conversation(stack)
    stack.model.reply("Hello, both.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    deliver(homeserver, mention("Hello"))
    stack.scheduler().answer_waiting()
    asked = messages(stack)
    assert asked[0]["content"] == topics.SUMMARY
    assert "in a group chat's conversation with you" in asked[1]["content"]
    assert f"Ben Okafor: {OLD}" in asked[1]["content"]
    [summary] = group_summaries(stack)
    assert summary["heard_by"] == ["ana", "ben"]
    assert [(f["value"], f["who"], f["speaker"]) for f in summary["body"]["facts"]] == [
        ("Q-1002", "Ben Okafor", "ben"), ("£1,240.50", "Ben Okafor", "ben"),
        ("2026-11-06", "Ben Okafor", "ben")]
    with db.transaction(stack.admin) as conn:
        [opened] = [r for r in conn.execute("select acts_for, trigger from runs")
                    if r["trigger"]["kind"] == "summary"]
    assert (opened["acts_for"], opened["trigger"]["sender"]) == (["ana", "ben"], "ana")

    stack.model.reply("It's due on 2026-11-06.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    deliver(homeserver, mention("When is the refund due?", by=BEN))
    stack.scheduler().answer_waiting()
    given = answering(stack)[-1][1]["content"]
    assert given.startswith("[from a5s, not anyone in the chat] A summary of this topic")
    assert "Decided: Contoso's refund for Q-1002 is £1,240.50." in given
    assert "Q-1002 (Ben Okafor, " in given


def test_nobody_added_later_is_given_a_summary_of_what_was_said_before(stack, homeserver):
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    a_long_group_conversation(stack)
    stack.model.reply("Hello, both.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    deliver(homeserver, mention("Hello"))
    stack.scheduler().answer_waiting()
    homeserver.rooms[ROOM].add(CHEN)  # Chen joins
    stack.model.reply("Hello, Chen.")
    deliver(homeserver, mention("Say hello to Chen", by=BEN))
    stack.scheduler().answer_waiting()
    given = json.dumps(answering(stack)[-1])
    assert "Q-1002" not in given and "A summary of this topic" not in given
    with db.transaction(stack.admin) as conn:  # what all three heard, more than fits
        for n in range(5):
            context.add_turn(conn, person=GROUP, agent="assistant", role="person",
                             content=f"Plan {n}: " + "the rota for next week is settled. " * 28,
                             speaker="chen", heard_by=["ana", "ben", "chen"])
    stack.model.reply("Noted.")
    stack.model.reply(folded(["The rota for next week is settled."]))
    deliver(homeserver, mention("Thanks", by=CHEN))
    stack.scheduler().answer_waiting()
    asked = messages(stack)[1]["content"]
    assert ("The summary so far of the general topic, in a group chat's conversation with "
            "you:\nNone yet.") in asked  # afresh, from what Chen heard
    assert "Q-1002" not in asked and "Chen" in asked
    [summary] = group_summaries(stack)
    assert summary["heard_by"] == ["ana", "ben", "chen"]
    assert "Q-1002" not in json.dumps(summary["body"])


def test_someone_who_leaves_takes_the_groups_summary_of_what_they_said(stack, homeserver):
    a_long_group_conversation(stack)
    stack.model.reply("Hello, both.")
    stack.model.reply(folded([]))
    deliver(homeserver, mention("Hello"))
    stack.scheduler().answer_waiting()
    assert any(f["speaker"] == "ben" for s in group_summaries(stack) for f in s["body"]["facts"])
    with db.transaction(stack.admin) as conn:
        name = departures.archive(conn, "ben", datetime.now(UTC))
        speakers = {r["speaker"] for r in conn.execute("select speaker from turns where "
                                                        "speaker is not null")}
    assert group_summaries(stack) == []  # it named him: the group's next run makes it again,
    assert speakers == {"ana", name}  # from the turns, where the archive's name stands for him


# Teams: group chats, as the Bot Framework sends them


class GroupBotFramework(FakeBotFramework):
    """The Bot Framework, which also says who's in each group chat."""

    def __init__(self) -> None:
        super().__init__()
        self.members = [{"id": "29:ana", "aadObjectId": ANA_ENTRA},
                        {"id": "29:ben", "aadObjectId": BEN_ENTRA},
                        {"id": f"28:{APP_ID}", "name": "Assistant"}]  # bots aren't people

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/members"):
            return httpx.Response(200, json=self.members)
        return super().handler(request)


def group_chat(text: str = ASKED, *, mentioned: bool = True, kind: str = "groupChat") -> dict:
    said = activity(f"<at>Assistant</at> {text}", kind=kind)
    if mentioned:
        said["entities"] = [{"type": "mention", "mentioned": {"id": "28:a5s-bot"}}]
    return said


@pytest.fixture
def team(stack):
    fake = GroupBotFramework()
    cfg = TeamsConfig(bots=(Bot("assistant", APP_ID, "bot-secret"),
                            Bot("watcher", WATCHER_APP, "watcher-secret")),
                      tenant_id=TENANT, service_hosts=("smba.test",), login_url="https://login.test",
                      metadata_url="https://login.botframework.test/v1/.well-known/openidconfiguration")
    stack.gateway.teams = Teams(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/teams/messages"
        yield fake


def test_a_mention_in_a_teams_group_chat_is_answered_there(stack, team):
    assert httpx.post(team.url, json=group_chat(), headers=team.auth()).status_code == 200
    [row] = queued(stack)
    assert (row["person"], row["members"], row["text"]) == ("ana", ["ana", "ben"], ASKED)
    assert row["conversation"] == groups.key("teams", "a:1-chat")
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    assert stack.scheduler().answer_waiting() == 1
    assert team.sent[-1]["text"] == "Q-1001 mentions an invoice."


@pytest.mark.parametrize("case", ["not mentioned", "a team's channel", "a stranger"])
def test_a_teams_chat_the_agent_doesnt_work_in(stack, team, case):
    if case == "a stranger":
        team.members = [*team.members, {"id": "29:x", "aadObjectId": "0a5a0000-0000-4000-8000-0000000000ff"}]
    sent = group_chat(mentioned=case != "not mentioned",
                      kind="channel" if case == "a team's channel" else "groupChat")
    assert httpx.post(team.url, json=sent, headers=team.auth()).status_code == 200
    assert queued(stack) == []
    told = {"not mentioned": [], "a team's channel": [groups.CHANNELS],
            "a stranger": [groups.STRANGERS.format(who="someone")]}[case]
    eventually(lambda: len(team.sent) >= len(told))  # told after the 200, in the background
    assert [m["text"] for m in team.sent] == told


@pytest.mark.live
def test_a_real_model_answers_a_group_and_knows_who_said_what(database, tmp_path):
    release = definitions.load(ROOT / "agents" / "assistant")
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text())
    with (running(database, root, httpx.Client(), FakeModel(), worker_image=live_image()) as stack,
          group_room(stack) as room):
        deliver(room, mention("Which of our customer questions mention an invoice?"))
        stack.scheduler().answer_waiting()
        first = room.sent[-1]
        print(f"--> {first['body']}")
        assert first["room"] == ROOM and "Q-1001" in first["body"]
        deliver(room, mention("Who asked you about invoices just now?", by=BEN))
        stack.scheduler().answer_waiting()
        print(f"--> {room.sent[-1]['body']}")
        assert "Ana" in room.sent[-1]["body"]
