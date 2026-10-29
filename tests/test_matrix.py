"""Matrix: the homeserver sends the core what happens in the bots' rooms, and the core
alone speaks as the bots. The events are shaped as Synapse sends them."""

import json
import uuid
from dataclasses import replace
from urllib.parse import unquote

import httpx
import pytest

from a5s import db
from a5s.core import inbox
from a5s.core.matrix import ENCRYPTED, ONE_TO_ONE, UNKNOWN, Matrix, MatrixConfig
from conftest import free_port, serve

AS_TOKEN, HS_TOKEN = "a5s-speaks-as-its-bots", "the-homeserver-proves-itself"
BOT, ANA, BEN = "@a5s-assistant:a5s.test", "@ana:a5s.test", "@ben:a5s.test"
WATCHER = "@a5s-watcher:a5s.test"  # a second agent's own bot
DM = "!dm:a5s.test"


class Homeserver:
    """A homeserver's client-server API, as a5s uses it to speak as its bots."""

    def __init__(self) -> None:
        self.rooms: dict[str, set[str]] = {DM: {ANA}}
        self.registered: list[str] = []
        self.sent: list[dict] = []
        self.started: list[dict] = []  # rooms a bot made, and whom it invited
        self.closed: set[str] = set()  # rooms nobody may join, such as an invitation withdrawn
        self.url = ""

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {AS_TOKEN}":
            return httpx.Response(401, json={"errcode": "M_UNKNOWN_TOKEN"})
        path, user = unquote(request.url.path), request.url.params.get("user_id")
        if path.endswith("/register"):
            local = json.loads(request.content)["username"]
            if local in self.registered:
                return httpx.Response(400, json={"errcode": "M_USER_IN_USE"})
            self.registered.append(local)
            return httpx.Response(200, json={"user_id": f"@{local}:a5s.test"})
        if path.endswith("/createRoom"):
            room, asked = f"!{uuid.uuid4().hex[:8]}:a5s.test", json.loads(request.content)
            self.rooms[room] = {user}  # its people join once they accept
            self.started.append({"room": room, "by": user, "invite": asked["invite"],
                                 "direct": asked["is_direct"]})
            return httpx.Response(200, json={"room_id": room})
        room = path.split("/rooms/")[-1].split("/")[0] if "/rooms/" in path else path.split("/join/")[-1]
        if "/join/" in path:
            if room in self.closed:
                return httpx.Response(403, json={"errcode": "M_FORBIDDEN"})
            self.rooms.setdefault(room, set()).add(user)
            return httpx.Response(200, json={"room_id": room})
        if user not in self.rooms.get(room, set()):
            return httpx.Response(403, json={"errcode": "M_FORBIDDEN"})
        if path.endswith("/joined_members"):
            return httpx.Response(200, json={"joined": {m: {} for m in self.rooms[room]}})
        if "/send/m.room.message/" in path:
            self.sent.append({"room": room, "as": user, "body": json.loads(request.content)["body"]})
            return httpx.Response(200, json={"event_id": f"${uuid.uuid4().hex}"})
        return httpx.Response(404)


@pytest.fixture
def homeserver(stack):
    fake = Homeserver()
    cfg = MatrixConfig("https://matrix.test", "a5s.test", AS_TOKEN, HS_TOKEN)
    stack.gateway.matrix = Matrix(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))  # as deployed
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/matrix/_matrix/app/v1"
        yield fake


def deliver(fake: Homeserver, *events: dict, token: str | None = HS_TOKEN) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.put(f"{fake.url}/transactions/{uuid.uuid4().hex}", json={"events": list(events)},
                     headers=headers)


def invite(by: str = ANA, bot: str = BOT, room: str = DM) -> dict:
    return {"type": "m.room.member", "sender": by, "state_key": bot, "room_id": room,
            "event_id": f"${uuid.uuid4().hex}", "content": {"membership": "invite", "is_direct": True}}


def leave(who: str = ANA, room: str = DM) -> dict:
    return {"type": "m.room.member", "sender": who, "state_key": who, "room_id": room,
            "event_id": f"${uuid.uuid4().hex}", "content": {"membership": "leave"}}


def said(text: str, by: str = ANA, room: str = DM, **content) -> dict:
    return {"type": "m.room.message", "sender": by, "room_id": room, "event_id": f"${uuid.uuid4().hex}",
            "content": {"msgtype": "m.text", "body": text, **content}}


def queued(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from inbound where channel = 'matrix'").fetchall()


def turned_away(stack) -> list[list[str]]:
    return [e["reasons"] for e in stack.ledger() if e["kind"] == "inbound" and e["decision"] == "deny"]


def test_a_matrix_message_is_checked_recorded_and_answered_in_the_room(stack, homeserver):
    assert deliver(homeserver, invite()).status_code == 200
    assert BOT in homeserver.rooms[DM] and homeserver.registered == ["a5s-assistant"]

    stack.model.reply("Q-1001 mentions an invoice.")
    assert deliver(homeserver, said("Which questions mention an invoice?")).status_code == 200
    [row] = queued(stack)
    assert (row["person"], row["agent"], row["reply_to"]) == ("ana", "assistant", {"room": DM, "bot": BOT})
    assert stack.scheduler().answer_waiting() == 1
    assert homeserver.sent == [{"room": DM, "as": BOT, "body": "Q-1001 mentions an invoice."}]
    [arrived] = [e for e in stack.ledger() if e["kind"] == "inbound"]
    assert arrived["args"]["identity"] == "verified by matrix"


def test_only_the_homeserver_can_deliver(stack, homeserver):
    deliver(homeserver, invite())
    assert deliver(homeserver, said("Hi"), token=None).status_code == 401
    assert deliver(homeserver, said("Hi"), token="guessed").status_code == 403
    assert queued(stack) == []
    with_query = httpx.put(f"{homeserver.url}/transactions/legacy", params={"access_token": HS_TOKEN},
                           json={"events": [said("Hi")]})  # as older homeservers send it
    assert with_query.status_code == 200 and len(queued(stack)) == 1


def test_a5s_joins_only_when_someone_in_the_directory_invites_one_of_its_agents(stack, homeserver):
    deliver(homeserver, invite(by="@mallory:a5s.test", room="!a:a5s.test"),  # not in the directory
            invite(by="@ana:elsewhere.org", room="!b:a5s.test"),  # another organisation's server
            invite(bot="@a5s-nobody:a5s.test", room="!c:a5s.test"))  # no such agent
    assert homeserver.registered == [] and BOT not in str(homeserver.rooms)


def test_people_the_directory_doesnt_know_hear_so_and_nothing_runs(stack, homeserver):
    homeserver.rooms["!x:a5s.test"] = {"@mallory:a5s.test", BOT}
    deliver(homeserver, said("Hi", by="@mallory:a5s.test", room="!x:a5s.test"))
    assert queued(stack) == [] and turned_away(stack) == [
        ["the directory doesn't know matrix:@mallory:a5s.test"]]
    assert homeserver.sent == [{"room": "!x:a5s.test", "as": BOT, "body": UNKNOWN}]


def test_a5s_talks_one_to_one_in_matrix_too(stack, homeserver):
    deliver(homeserver, invite())
    homeserver.rooms[DM].add(BEN)
    deliver(homeserver, said("Hello, both of you"))
    assert queued(stack) == [] and homeserver.sent[-1]["body"] == ONE_TO_ONE


def test_an_encrypted_message_is_turned_away_with_how_to_carry_on(stack, homeserver):
    deliver(homeserver, invite())
    sealed = {**said(""), "type": "m.room.encrypted", "content": {"algorithm": "m.megolm.v1.aes-sha2"}}
    deliver(homeserver, sealed)
    assert queued(stack) == [] and homeserver.sent[-1]["body"] == ENCRYPTED


def test_a_resent_delivery_counts_once(stack, homeserver):
    deliver(homeserver, invite())
    hello = said("Hello")
    deliver(homeserver, hello)
    deliver(homeserver, hello)  # the homeserver tries again when it hears nothing back
    assert len(queued(stack)) == 1


def test_the_bots_own_messages_and_edits_and_notices_are_never_answered(stack, homeserver):
    deliver(homeserver, invite())
    deliver(homeserver, said("Q-1001.", by=BOT),
            said("* Hello", **{"m.relates_to": {"rel_type": "m.replace", "event_id": "$x"}}),
            {**said("a notice"), "content": {"msgtype": "m.notice", "body": "a notice"}})
    assert queued(stack) == [] and turned_away(stack) == []


def test_an_event_a5s_cant_act_on_holds_up_nothing_after_it(stack, homeserver):
    deliver(homeserver, invite())
    homeserver.closed.add("!gone:a5s.test")  # Ana withdrew the invitation before a5s joined
    answer = deliver(homeserver, invite(room="!gone:a5s.test"), said("Hello"))
    assert answer.status_code == 200  # or the homeserver would send it again, and nothing else
    assert len(queued(stack)) == 1


def test_a5s_asks_again_once_its_bot_has_left_a_room(stack, homeserver):
    deliver(homeserver, invite())
    homeserver.rooms[DM].discard(BOT)  # Ana removed it
    removed = {**invite(), "content": {"membership": "leave"}}
    deliver(homeserver, removed, said("Hello?"))
    assert queued(stack) == [] and turned_away(stack) == [] and homeserver.sent == []


def test_a_reminder_reaches_the_matrix_room_the_person_last_wrote_in(stack, homeserver):
    deliver(homeserver, invite())
    stack.model.reply("Hello, Ana.")
    deliver(homeserver, said("Hello"))
    stack.scheduler().answer_waiting()

    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    assert homeserver.sent[-1] == {"room": DM, "as": BOT, "body": "Ana, Q-1001 is due on Wednesday."}
    assert [m["text"] for m in stack.inbox("ben")] == ["Ben, Q-1002 is due on Friday."]  # no room yet


def reminded_by_the_watcher(stack, homeserver) -> dict:
    """Ana talks to the assistant in Matrix, and then the watcher reminds her. The room it
    started for her."""
    stack.add_watcher()  # it chases what falls due for Ana and Ben now, not the assistant
    deliver(homeserver, invite())
    stack.model.reply("Hello, Ana.")
    deliver(homeserver, said("Hello"))
    stack.scheduler().answer_waiting()

    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    [started] = homeserver.started
    return started


def test_an_agent_writes_first_only_as_its_own_bot(stack, homeserver):
    started = reminded_by_the_watcher(stack, homeserver)
    assert (started["by"], started["invite"], started["direct"]) == (WATCHER, [ANA], True)
    assert [(m["as"], m["body"]) for m in homeserver.sent] == [
        (BOT, "Hello, Ana."), (WATCHER, "Ana, Q-1001 is due on Wednesday.")]  # never as the assistant
    assert homeserver.sent[-1]["room"] == started["room"]
    assert [m["text"] for m in stack.inbox("ben")] == ["Ben, Q-1002 is due on Friday."]  # no Matrix yet
    [delivered] = [e for e in stack.ledger() if e["action"] == "deliver"][-1:]
    assert delivered["outcome"] == {"status": "ok", "channel": "matrix", "started": True}

    stack.at("2026-11-09T09:00:00+00:00")  # Ben's was due on Friday, so Ana, his manager, hears
    stack.scheduler().work_due()
    assert homeserver.sent[-1]["body"].startswith("Q-1002, Refund for a duplicate payment, was due")
    assert (homeserver.sent[-1]["room"], homeserver.sent[-1]["as"]) == (started["room"], WATCHER)
    assert len(homeserver.started) == 1  # the same chat again, not a new one

    homeserver.rooms[started["room"]].add(ANA)  # she accepts, and answers it there
    stack.model.reply("Thanks, Ana.")
    deliver(homeserver, said("I'll look at it today", room=started["room"]))
    [answered] = [r for r in queued(stack) if r["text"] == "I'll look at it today"]
    assert (answered["agent"], answered["reply_to"]["bot"]) == ("watcher", WATCHER)
    stack.scheduler().answer_waiting()
    assert (homeserver.sent[-1]["as"], homeserver.sent[-1]["body"]) == (WATCHER, "Thanks, Ana.")


def test_someone_who_turns_down_an_agents_chat_hears_from_it_in_their_inbox(stack, homeserver):
    started = reminded_by_the_watcher(stack, homeserver)
    deliver(homeserver, leave(ANA, started["room"]))  # she turns the invitation down

    stack.at("2026-11-09T09:00:00+00:00")  # Ben's was due on Friday, so Ana, his manager, hears
    stack.scheduler().work_due()
    assert len(homeserver.started) == 1  # a5s doesn't ask her in again
    assert homeserver.sent[-1]["body"] == "Ana, Q-1001 is due on Wednesday."  # nothing more there
    [escalated] = stack.inbox("ana")
    assert (escalated["from"], escalated["about"]) == ("a5s", "watcher")
    assert escalated["text"].startswith("Q-1002, Refund for a duplicate payment, was due")


def test_matrix_is_on_where_its_settings_are_and_needs_them_all(stack, homeserver, monkeypatch):
    assert inbox.chats_on(stack.gateway) == ["the command line", "the web chat", "Matrix"]
    for name in ("A5S_MATRIX_HOMESERVER", "A5S_MATRIX_SERVER_NAME", "A5S_MATRIX_AS_TOKEN",
                 "A5S_MATRIX_HS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert MatrixConfig.from_env() is None
    monkeypatch.setenv("A5S_MATRIX_HOMESERVER", "http://synapse:8008/")
    monkeypatch.setenv("A5S_MATRIX_AS_TOKEN", AS_TOKEN)
    with pytest.raises(RuntimeError, match="A5S_MATRIX_SERVER_NAME, A5S_MATRIX_HS_TOKEN"):
        MatrixConfig.from_env()  # rather than a homeserver whose deliveries nobody can check
    monkeypatch.setenv("A5S_MATRIX_SERVER_NAME", "a5s.test")
    monkeypatch.setenv("A5S_MATRIX_HS_TOKEN", HS_TOKEN)
    assert MatrixConfig.from_env() == MatrixConfig("http://synapse:8008", "a5s.test", AS_TOKEN, HS_TOKEN)


def test_the_homeserver_asks_after_a_bot_and_it_is_made_on_demand(stack, homeserver):
    headers = {"Authorization": f"Bearer {HS_TOKEN}"}
    assert httpx.get(f"{homeserver.url}/users/{BOT}", headers=headers).status_code == 200
    assert homeserver.registered == ["a5s-assistant"]
    assert httpx.get(f"{homeserver.url}/users/@a5s-nobody:a5s.test", headers=headers).status_code == 404
    assert httpx.get(f"{homeserver.url}/users/{ANA}", headers=headers).status_code == 404
    assert httpx.get(f"{homeserver.url}/users/{BOT}").status_code == 401
