"""Urgent messages: what a5s and its agents write to someone at once, when they aren't waiting
for it, such as an escalation. Up to five a day go at once, across all the agents, in the
person's own day. The rest wait, and go together once the oldest has waited an hour, in their
working hours. Answers aren't counted, and neither are reminders they asked for at a time."""

from datetime import datetime

from a5s import db
from a5s.core import registry, urgent

FRIDAY = "2026-10-30T09:30:00+00:00"  # 09:30 in London: only what a test sets up falls due
TUESDAY = "2026-11-03T09:30:00+00:00"  # the morning after Ben's extra records fell due
SUPPLIERS = ("Northwind", "Contoso", "Fabrikam", "Litware", "Tailspin", "Wingtip", "Adatum")


def overdue(stack, monkeypatch, count: int) -> None:
    """Records Ben owes, all due on Monday. Nobody chases him, as the assistant is suspended,
    so once due each goes up his line to Ana, his manager: an urgent message for her."""
    records = stack.gateway.scenario._records
    for n in range(1, count + 1):
        key = f"Q-20{n:02d}"
        monkeypatch.setitem(records, key, {
            "key": key, "part": "billing", "title": f"Refund for {SUPPLIERS[n - 1]}",
            "status": "open", "customer": SUPPLIERS[n - 1], "owner": "ben",
            "opened": "2026-10-26", "due": "2026-11-02", "contact": "billing@contoso.test"})
    stack.suspend(by="ben")


def due_now(stack, count: int) -> None:
    """Reminders Ana agreed to for a particular time, which go at once, all due on Friday."""
    with db.transaction(stack.admin) as conn:
        for supplier in SUPPLIERS[:count]:
            conn.execute(
                "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
                "offered_run, asked_at, confirmed_at, in_digest) values ('ana', 'assistant', "
                "'assistant-finance', %s, %s, now(), gen_random_uuid(), now(), now(), false)",
                (f"call {supplier}", FRIDAY))


def held(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from urgent_held order by id").fetchall()


def test_five_go_at_once_and_the_rest_together_once_the_first_has_waited_an_hour(stack,
                                                                                    monkeypatch):
    overdue(stack, monkeypatch, 7)
    stack.at(TUESDAY)
    stack.scheduler().work_due()
    told = [m["text"] for m in stack.inbox("ana")]
    assert len(told) == 5 and all(t.startswith("Q-20") for t in told)
    assert [h["text"][:7] for h in held(stack)] == ["Q-2006,", "Q-2007,"]
    went = [e["args"]["channel"] for e in stack.ledger() if e["action"] == "escalate"]
    assert went == ["local"] * 5 + ["batch"] * 2

    stack.at("2026-11-03T10:29:00+00:00")
    stack.scheduler().work_due()
    assert stack.inbox("ana") == []
    stack.at("2026-11-03T10:30:00+00:00")
    stack.scheduler().work_due()
    [batch] = stack.inbox("ana")
    assert batch["from"] == "a5s" and batch["text"].startswith(
        "2 messages that waited, as you've had today's 5 at once:\n\nFrom a5s:\nQ-2006,")
    [entry] = [e for e in stack.ledger() if e["kind"] == "notice" and e["action"] == "batch"]
    assert entry["acts_for"] == ["ana"] and entry["args"]["items"] == 2
    assert all(h["sent_at"] is not None for h in held(stack))
    stack.scheduler().work_due()
    assert stack.inbox("ana") == []  # once
    assert stack.verify().ok


def test_an_answer_is_never_counted_or_held(stack, monkeypatch):
    overdue(stack, monkeypatch, 6)
    stack.at(TUESDAY)
    stack.scheduler().work_due()
    assert len(held(stack)) == 1
    with db.transaction(stack.cfg.database_url) as conn:  # Ben resumes it
        assert not registry.set_status(conn, "assistant-finance", by="ben", suspend=False)
    stack.model.reply("You're welcome.")
    assert stack.say("Thanks") == "You're welcome."


def test_reminders_people_asked_for_at_a_time_all_go_then(stack):
    due_now(stack, 7)
    stack.suspend(by="ben")
    stack.at(FRIDAY)
    assert stack.scheduler().work_due() == 0  # the core reminds her itself, in code
    told = stack.inbox("ana")
    assert len(told) == 7 and held(stack) == []  # she asked for each of them then
    assert all("so a5s is reminding you itself" in m["text"] for m in told)


def test_each_day_is_counted_in_the_persons_own_time_zone(stack):
    late = datetime.fromisoformat("2026-10-30T15:30:00+00:00")  # 23:30 in Singapore
    next_day = datetime.fromisoformat("2026-10-30T16:30:00+00:00")  # 00:30 the next day there
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert all(urgent.counted(conn, scenario, "chen", late) for _ in range(urgent.CAP))
        assert not urgent.counted(conn, scenario, "chen", late)
        assert urgent.counted(conn, scenario, "chen", next_day)
        assert urgent.counted(conn, scenario, "ana", late)  # each person has their own five
