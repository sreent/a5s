"""When someone leaves. A day after the directory stops naming them, a5s archives what it
keeps for them where it is, under a name no person has: no run loads it again, nothing more
goes to them, and someone given the same id later starts afresh. Someone back within the day
is forgotten as missing. Nothing is copied anywhere else, and the archive goes on retention's
usual clock."""

from a5s import db

MONDAY = "2026-11-02T10:00:00+00:00"
TUESDAY = "2026-11-03T10:30:00+00:00"  # more than a day on


def sweep(stack) -> dict:
    with stack.client() as c:
        r = c.post("/retention/sweep")
    r.raise_for_status()
    return r.json()


def kept_for(stack, person: str) -> dict[str, int]:
    with db.transaction(stack.admin) as conn:
        return {table: conn.execute(f"select count(*) as n from {table} where person = %s",
                                    (person,)).fetchone()["n"]
                for table in ("turns", "outbox", "reminders", "profile_notes")}


def test_a_day_after_someone_leaves_what_a5s_kept_for_them_is_archived(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say("I'm working on Q-1002 today.", person="ben")
    assert kept_for(stack, "ben")["turns"] == 2
    people = dict(stack.gateway.scenario._people)
    del people["ben"]  # Ben leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    assert sweep(stack)["archived"] == 0  # not yet: the directory may only have missed him
    assert kept_for(stack, "ben")["turns"] == 2
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    assert kept_for(stack, "ben") == {"turns": 0, "outbox": 0, "reminders": 0, "profile_notes": 0}
    with db.transaction(stack.admin) as conn:
        [left] = conn.execute("select * from departures").fetchall()
        archived = conn.execute("select count(*) as n from turns where person = %s",
                                (left["archived_as"],)).fetchone()["n"]
    assert left["person"] == "ben" and left["archived_as"].startswith("former:")
    assert archived == 2  # where it was, not copied anywhere
    [entry] = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "archive"]
    assert entry["args"]["as"] == left["archived_as"]


def test_someone_given_the_same_id_later_starts_afresh(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say("Remember that I look after Contoso.", person="ben")
    ben = stack.gateway.scenario._people["ben"]
    people = dict(stack.gateway.scenario._people)
    del people["ben"]
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    sweep(stack)
    stack.at(TUESDAY)
    sweep(stack)
    monkeypatch.setattr(stack.gateway.scenario, "_people", {**people, "ben": ben})  # a new Ben
    stack.model.reply("Hello.")
    stack.say("Hello, I'm new here.", person="ben")
    seen = str(stack.model.requests[-1]["body"]["messages"])
    assert "Contoso" not in seen  # nothing of the Ben who left


def test_someone_back_within_the_day_keeps_their_conversation(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say("I'm working on Q-1002 today.", person="ben")
    everyone = stack.gateway.scenario._people
    monkeypatch.setattr(stack.gateway.scenario, "_people",
                        {k: v for k, v in everyone.items() if k != "ben"})
    sweep(stack)  # missed, for a moment
    monkeypatch.setattr(stack.gateway.scenario, "_people", everyone)
    sweep(stack)  # and back
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 0
    assert kept_for(stack, "ben")["turns"] == 2
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from departures").fetchone()["n"] == 0
