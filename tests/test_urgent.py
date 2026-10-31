"""Urgent messages: what a5s and its agents write to someone at once, when they aren't waiting
for it. Up to five a day go at once, across all the agents, in the person's own day. The rest
wait, and go together once the oldest has waited an hour. Answers aren't counted."""

from datetime import datetime

from a5s import db
from a5s.core import urgent

FRIDAY = "2026-10-30T09:30:00+00:00"  # 09:30 in London: only what a test sets up falls due
SUPPLIERS = ("Northwind", "Contoso", "Fabrikam", "Litware", "Tailspin", "Wingtip", "Adatum")


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


def test_five_go_at_once_and_the_rest_together_once_the_first_has_waited_an_hour(stack):
    due_now(stack, 7)
    stack.at(FRIDAY)
    for supplier in SUPPLIERS:
        stack.model.reply(f"Ana, it's time to call {supplier}.")
    assert stack.scheduler().work_due() == 7
    told = [f"Ana, it's time to call {s}." for s in SUPPLIERS]
    assert [m["text"] for m in stack.inbox("ana")] == told[:5]
    assert [h["text"] for h in held(stack)] == told[5:]
    sent = [e["args"]["channel"] for e in stack.ledger()
            if e["kind"] == "message" and e["action"] == "send"]
    assert sent == ["local"] * 5 + ["batch"] * 2

    stack.model.reply("You're welcome.")
    assert stack.say("Thanks") == "You're welcome."  # an answer isn't counted, or held

    stack.at("2026-10-30T10:29:00+00:00")
    stack.scheduler().work_due()
    assert stack.inbox("ana") == []
    stack.at("2026-10-30T10:30:00+00:00")
    stack.scheduler().work_due()
    [batch] = stack.inbox("ana")
    assert batch["from"] == "a5s" and batch["text"] == (
        "2 messages that waited, as you've had today's 5 at once:\n\n"
        f"From the assistant:\n{told[5]}\n\nFrom the assistant:\n{told[6]}")
    [entry] = [e for e in stack.ledger() if e["kind"] == "notice" and e["action"] == "batch"]
    assert entry["acts_for"] == ["ana"] and entry["args"]["items"] == 2
    assert all(h["sent_at"] is not None for h in held(stack))
    stack.scheduler().work_due()
    assert stack.inbox("ana") == []  # once
    assert stack.verify().ok


def test_a5s_own_notices_count_and_wait_too(stack):
    due_now(stack, 6)
    stack.suspend(by="ben")
    stack.at(FRIDAY)
    assert stack.scheduler().work_due() == 0  # the core reminds her itself, in code
    assert len(stack.inbox("ana")) == 5
    [waiting] = held(stack)
    assert waiting["agent"] is None and "so a5s is reminding you itself" in waiting["text"]
    reminded = [e["args"]["channel"] for e in stack.ledger() if e["action"] == "remind"]
    assert reminded == ["local"] * 5 + ["batch"]

    stack.at("2026-10-30T10:30:00+00:00")
    stack.scheduler().work_due()
    [one] = stack.inbox("ana")  # a batch of one goes as itself
    assert one["from"] == "a5s" and one["text"] == waiting["text"]


def test_each_day_is_counted_in_the_persons_own_time_zone(stack):
    late = datetime.fromisoformat("2026-10-30T15:30:00+00:00")  # 23:30 in Singapore
    next_day = datetime.fromisoformat("2026-10-30T16:30:00+00:00")  # 00:30 the next day there
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert all(urgent.counted(conn, scenario, "chen", late) for _ in range(urgent.CAP))
        assert not urgent.counted(conn, scenario, "chen", late)
        assert urgent.counted(conn, scenario, "chen", next_day)
        assert urgent.counted(conn, scenario, "ana", late)  # each person has their own five
