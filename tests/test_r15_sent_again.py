"""Round 15, the operator's finding (D13): a chat away for more than a quarter of an hour lost what
a5s sent it meanwhile to the person's local inbox for good, which someone who reads only Teams
never sees. Now what fell back there is tried again for a day, unless they read it there first:
at once when the chat takes something else for them, else hourly. What a departure or a restore
leaves there never goes again."""

from __future__ import annotations

from datetime import timedelta

import httpx
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import gateway, restoring
from conftest import QUIET

ROUTE = {"channel": "teams", "reply_to": {"conversation": "a:ana"}}


class Teams:
    """A chat that takes what a5s sends it, or, while it's away, doesn't."""

    def __init__(self) -> None:
        self.away, self.sent = True, []

    def send(self, reply_to: dict, text: str, card=None, feedback: bool = False) -> str:
        if self.away:
            raise httpx.ConnectError("teams is away")
        self.sent.append(text)
        return f"activity-{len(self.sent)}"


def waiting(stack, person: str, text: str, **row) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute(
            "insert into outbox (person, channel, text, route, attempts) values (%s, 'teams', "
            "%s, %s, %s) returning id", (person, text, Jsonb(ROUTE), row.get("attempts", 0)),
        ).fetchone()["id"]


def swept(stack) -> None:
    with stack.client() as c:
        c.post("/deliveries/sweep").raise_for_status()


def row(stack, id: int) -> dict:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from outbox where id = %s", (id,)).fetchone()


def test_what_fell_back_to_the_inbox_goes_once_the_chat_takes_something_else(stack):
    teams = stack.gateway.teams = Teams()
    first = waiting(stack, "ana", "Your refund is on its way.", attempts=gateway.TRIES - 1)
    swept(stack)  # its fifth try: away, so to her inbox
    fell = row(stack, first)
    assert (fell["channel"], fell["fell_back_at"] is not None) == ("local", True)
    teams.away = False
    later = waiting(stack, "ana", "And here's your receipt.")
    swept(stack)
    assert teams.sent == ["And here's your receipt.", "Your refund is on its way."]
    went = row(stack, first)
    assert (went["channel"], went["delivered_at"] is not None, went["fell_back_at"]) == (
        "teams", True, None)
    assert row(stack, later)["delivered_at"] is not None


def test_what_fell_back_goes_hourly_for_a_day_unless_they_read_it_first(stack):
    teams = stack.gateway.teams = Teams()
    ids = [waiting(stack, who, f"For {who}.", attempts=gateway.TRIES - 1)
           for who in ("ana", "ben", "kofi")]
    swept(stack)
    teams.away = False
    with db.transaction(stack.admin) as conn:  # ben read his in the inbox, and kofi's is old
        conn.execute("update outbox set delivered_at = now() where id = %s", (ids[1],))
        conn.execute("update outbox set fell_back_at = fell_back_at - interval '2 days' "
                     "where id = %s", (ids[2],))
    stack.at((QUIET + timedelta(hours=1, minutes=1)).isoformat())  # an hour on, by the core
    swept(stack)
    assert teams.sent == ["For ana."]
    assert row(stack, ids[2])["channel"] == "local"  # in kofi's inbox, as it was


def test_what_a_restore_holds_never_goes_again(stack, tmp_path):
    teams = stack.gateway.teams = Teams()
    teams.away = False
    held = waiting(stack, "ana", "May have gone already.")
    with db.transaction(stack.admin) as conn:
        conn.execute("update outbox set channel = 'local', problem = %s where id = %s",
                     (restoring.HELD, held))
    waiting(stack, "ana", "Something new.")
    swept(stack)
    assert teams.sent == ["Something new."] and row(stack, held)["channel"] == "local"
