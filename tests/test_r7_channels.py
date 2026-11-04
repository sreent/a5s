"""Round 7: the chats an agent works in with more than one person.

Matrix rooms set up as people set them up, rooms with several of a5s's bots, rooms that are
someone's own until someone else joins them, Teams chats with other apps in them, and what a5s
says, and records, when it can't work somewhere. Each test failed before round 7's fixes.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from a5s import db
from a5s.core.matrix import Matrix, MatrixConfig
from test_groups import (
    ANA,
    BEN,
    CHEN,
    ROOM,
    group_chat,
    group_room,
    mention,
    queued,
    team,  # noqa: F401  (a fixture)
)
from test_matrix import BOT, DM, WATCHER, deliver, homeserver, invite, said  # noqa: F401
from test_teams import APP_ID


@pytest.fixture
def room(stack):
    with group_room(stack) as fake:
        yield fake


def sent(fake, n: int = 1) -> list[str]:
    """What a5s said in the chat, once its background replies have gone."""
    for _ in range(50):
        if len(fake.sent) >= n:
            break
        time.sleep(0.1)
    return [m.get("body") or m.get("text") for m in fake.sent]


def denials(stack) -> list[str]:
    return [r for e in stack.ledger() if e["kind"] == "inbound" and e["decision"] == "deny"
            for r in e["reasons"]]


# Teams


def test_teams_keeps_the_names_people_mention_and_drops_only_the_bots(stack, team):  # noqa: F811
    """A Teams message loses only its mention of the bot it went to (C7)."""
    said_there = group_chat("what did <at>Ben Okafor</at> ask you about yesterday?")
    said_there["entities"].append({"type": "mention", "text": "<at>Ben Okafor</at>",
                                   "mentioned": {"id": "29:ben", "name": "Ben Okafor"}})
    assert httpx.post(team.url, json=said_there, headers=team.auth()).status_code == 200
    [row] = queued(stack)
    assert row["text"] == "what did Ben Okafor ask you about yesterday?"


def test_a_teams_chat_with_another_app_in_it_is_turned_away(stack, team):  # noqa: F811
    """Any app but a5s's own bots may read what's said, so it's a stranger (A9)."""
    team.members = [*team.members, {"id": "28:meeting-notes", "name": "Meeting Notes"}]
    assert httpx.post(team.url, json=group_chat(), headers=team.auth()).status_code == 200
    assert queued(stack) == []
    assert sent(team) == [("I can help in a chat only if everyone in it is in the organisation's "
                           "directory, and Meeting Notes isn't, so I can't help here. Ask me one "
                           "to one.")]
    assert f"28:{APP_ID}" in {m["id"] for m in team.members}  # its own bot is no stranger


def test_a_teams_chat_whose_members_cant_be_read_hears_so_and_its_recorded(stack, team):  # noqa: F811
    """Not a 503 that nobody records, which Teams may never send again (B13)."""
    original = team.handler

    def failing(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/members"):
            return httpx.Response(502)
        return original(request)

    stack.gateway.teams.http = httpx.Client(transport=httpx.MockTransport(failing))
    assert httpx.post(team.url, json=group_chat(), headers=team.auth()).status_code == 200
    assert queued(stack) == [] and "a5s couldn't read who's in the chat" in denials(stack)
    assert sent(team) == [("I couldn't tell who's in this chat just now, so I can't answer "
                           "here. Ask me again in a minute.")]


# Matrix


def test_an_encrypted_group_room_hears_once_why_the_agent_cant_work_there(stack, room):
    """Not silence, ever (C5)."""
    sealed = {**said("", by=ANA, room=ROOM), "type": "m.room.encrypted",
              "content": {"algorithm": "m.megolm.v1.aes-sha2"}}
    deliver(room, sealed)
    deliver(room, {**sealed, "event_id": "$again"})
    assert queued(stack) == []
    assert sent(room) == [("I can't read encrypted rooms yet, so I can't help in this one. Ask "
                           "me in a room made with encryption off, or one to one.")]


def test_the_history_refusal_says_who_can_change_it(stack, room):
    room.history[ROOM] = "shared"  # as Synapse makes a private room
    deliver(room, mention("Which questions mention an invoice?"))
    assert "Ask whoever administers this room" in sent(room)[-1]


def test_each_of_a5s_bots_in_a_room_hears_its_own_mentions(stack, room):
    """With the assistant and the watcher in one room, before a restart and after (C6, B11)."""
    stack.with_watcher()
    deliver(room, invite(room=ROOM, bot=WATCHER))
    deliver(room, mention("what's Q-1001 about?"))
    stack.gateway.matrix._rooms.clear()  # the channels app restarts
    deliver(room, said("a5s-watcher: what changed on Q-1001?", room=ROOM,
                       **{"m.mentions": {"user_ids": [WATCHER]}}))
    assert [r["agent"] for r in queued(stack)] == ["assistant", "watcher"]


def test_a_big_rooms_chatter_costs_one_member_list_and_a_room_too_big_is_left(stack, room):
    """Not a list of 2,002 people for every message nobody sent the agent (B8)."""
    big = "!everyone:a5s.test"
    room.rooms[big] = {ANA, BEN, *(f"@p{i}:a5s.test" for i in range(2000))}
    room.history[big] = "joined"
    calls = []
    original = room.handler

    def counting(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/joined_members"):
            calls.append(request.url.path)
        return original(request)

    stack.gateway.matrix.http = httpx.Client(transport=httpx.MockTransport(counting))
    deliver(room, invite(room=big))
    for i in range(30):
        deliver(room, said(f"lunch {i}?", by=BEN, room=big))
    assert len(calls) <= 2  # the bot checks it's there, then reads who's in it once
    deliver(room, mention("help", by=ANA) | {"room_id": big})
    assert sent(room)[-1].startswith("I work in group chats of up to 20 people")
    for _ in range(50):
        if BOT not in room.rooms[big]:
            break
        time.sleep(0.1)
    assert BOT not in room.rooms[big]  # it left


def test_a_room_whose_members_cant_be_read_isnt_taken_as_ones_own_chat(stack, room):
    """It fails closed: a message there isn't answered as the sender's own (A15)."""
    deliver(room, mention("Hello"))  # the bot is known to be in the room
    queued_before = len(queued(stack))
    room.rooms[ROOM].discard(BOT)  # it's removed, and the channels app hasn't heard yet
    deliver(room, said("Lunch at one? Q-1001 can wait.", by=ANA, room=ROOM))
    with db.transaction(stack.admin) as conn:
        own = conn.execute("select count(*) as n from inbound where conversation is null "
                           "and text like 'Lunch%%'").fetchone()["n"]
    assert own == 0 and len(queued(stack)) == queued_before


@pytest.mark.parametrize("how", ["readable unjoined", "anyone may join", "someone invited"])
def test_a_room_others_can_read_isnt_taken_as_ones_own_chat(stack, homeserver, how):  # noqa: F811
    """Only Ana and the bot have joined, but others can read what's said there, so it's a
    group's room: a plain message to the agent isn't answered as hers alone (A8)."""
    deliver(homeserver, invite())
    if how == "readable unjoined":
        homeserver.handler = _history(homeserver, "world_readable")
        stack.gateway.matrix.http = httpx.Client(transport=httpx.MockTransport(homeserver.handler))
    elif how == "anyone may join":
        homeserver.rules[DM] = "public"
    else:
        homeserver.invited[DM] = {CHEN}
    deliver(homeserver, said("What's Q-1001 about?"))
    assert queued(stack) == []  # it didn't mention the agent, as a group's room needs


def _history(fake, visibility: str):
    original = fake.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/state/m.room.history_visibility"):
            return httpx.Response(200, json={"history_visibility": visibility})
        return original(request)

    return handler


def test_once_someone_joins_a_persons_own_chat_a5s_writes_to_them_first_elsewhere(
        stack, homeserver):  # noqa: F811
    """Ana's own room with the assistant isn't hers alone once Ben joins it, so her reminders,
    digests and cards go to a new direct chat, never that room (B2, A7)."""
    deliver(homeserver, invite())
    stack.model.reply("Hello, Ana.")
    deliver(homeserver, said("Hello"))
    stack.scheduler().answer_waiting()
    with db.transaction(stack.admin) as conn:
        assert stack.gateway.reach(conn, "ana", "assistant")["reply_to"] == {"room": DM, "bot": BOT}
    homeserver.rooms[DM].add(BEN)
    deliver(homeserver, {"type": "m.room.member", "sender": BEN, "state_key": BEN,
                         "room_id": DM, "event_id": "$ben-joins",
                         "content": {"membership": "join"}})
    with db.transaction(stack.admin) as conn:
        route = stack.gateway.reach(conn, "ana", "assistant")
    assert route.get("reply_to") != {"room": DM, "bot": BOT}
    assert route["start"]["user"] == ANA  # a new direct chat, just hers


def test_a_direct_chat_a5s_starts_hides_what_was_said_from_anyone_added_later():
    """So someone added to it later can't read what a5s wrote there to its person (B2)."""
    made = []

    def homeserver_(request: httpx.Request) -> httpx.Response:
        made.append(request)
        return httpx.Response(200, json={"room_id": "!new:a5s.test", "user_id": BOT})

    matrix = Matrix(MatrixConfig("https://matrix.test", "a5s.test", "as", "hs"),
                    httpx.Client(transport=httpx.MockTransport(homeserver_)))
    matrix.start(ANA, "assistant")
    [created] = [json.loads(r.content) for r in made if r.url.path.endswith("/createRoom")]
    assert {"type": "m.room.history_visibility", "state_key": "",
            "content": {"history_visibility": "joined"}} in created["initial_state"]


def test_a_room_with_someone_a5s_may_not_write_to_hears_so_before_any_run(stack, room):
    """Not a run on the asker's budget, then a reply it can't send (C8)."""
    from dataclasses import replace
    people = stack.gateway.scenario._people
    people["ben"] = replace(people["ben"], in_audience=False)
    deliver(room, mention("Which questions mention an invoice?"))
    stack.scheduler().answer_waiting()
    assert stack.model.requests == []
    assert sent(room)[-1] == ("I may not write to Ben Okafor, so I can't help in this chat. Ask "
                              "me in a chat without them, or one to one.")


def test_a_rooms_stranger_is_named(stack, room):
    room.rooms[ROOM].add("@guest:a5s.test")
    deliver(room, mention("Which questions mention an invoice?"))
    assert "@guest:a5s.test isn't" in sent(room)[-1]
