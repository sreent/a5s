"""What nobody answers for any more, on the administrators' page (core/administration.py,
docs/administration.md): an agent nobody the directory names owns, an instance whose owner or
deputy the directory no longer knows, and a part nobody owns, each with what to do."""

from a5s import db
from a5s.core import administration


def ownerless(stack) -> dict:
    with db.transaction(stack.admin) as conn:
        return administration.ownerless(conn, stack.gateway)


def leave(stack, monkeypatch, *gone: str) -> None:
    """The directory as it is once these people have left, as tests/test_departures.py has it."""
    people = {pid: p for pid, p in stack.gateway.scenario._people.items() if pid not in gone}
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)


def test_nothing_is_ownerless_while_everyone_is_there(stack):
    assert ownerless(stack) == {"agents": [], "instances": [], "parts": []}


def test_an_owner_who_leaves_leaves_what_they_owned_ownerless(stack, monkeypatch):
    # the agents' owner, an instance's deputy, and billing's owner
    leave(stack, monkeypatch, "priya", "ben", "ana")
    found = ownerless(stack)
    assert [a["agent"] for a in found["agents"]] == ["assistant", "watcher"]
    assert [(i["instance"], i["what"]) for i in found["instances"]] == [
        ("assistant-finance", "the directory no longer knows ana, ben, who run it")]
    assert [p["part"] for p in found["parts"]] == ["billing"]
    assert all(x["do"] for x in found["agents"] + found["instances"] + found["parts"])
