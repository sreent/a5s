"""Round 5, reviewer c: what someone agreed to be reminded of, and what they owe, when the run
that should tell them doesn't get through.

The core marks a reminder given (reminders.reminded_at) and an obligation chased
(obligations.chased_at) as it opens the run, before the agent has written a word. When the
run then fails, such as when the model is down, nothing puts them back, so the person never
hears, and a5s's own words later say they were reminded."""

from a5s import db

FRIDAY = "2026-10-30T09:30:00+00:00"  # 09:30 in London: Ana's reminder is due, and nothing else
ABOUT = "check whether Northwind has answered about Q-1001"


def kept(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from reminders order by id").fetchall()


def runs(stack, kind: str) -> list[str]:
    """How each run of a kind ended, oldest first."""
    with db.transaction(stack.admin) as conn:
        return [r["outcome"] for r in conn.execute(
            "select outcome from runs where trigger->>'kind' = %s order by opened_at", (kind,))]


def heard(stack, person: str) -> list[str]:
    """Everything a5s or an agent wrote to someone, unasked, whether collected or not."""
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute(
            "select text from outbox where person = %s and inbound_id is null order by id", (person,))]


def asked_and_confirmed(stack, on: str = "2026-10-30") -> None:
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": on, "record": "Q-1001"}))
    stack.model.reply("Shall I remind you then? Say yes, and I'll set it.")
    stack.say("Remind me on Friday to check whether Northwind has answered.")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done.")
    stack.say("Yes please")
    assert kept(stack)[0]["confirmed_at"] is not None


def test_a_reminder_due_while_the_model_is_down_is_given_once_it_is_back(stack):
    asked_and_confirmed(stack)
    stack.at(FRIDAY)
    stack.model.failing = 5  # the provider is down when the reminder falls due
    stack.scheduler().work_due()
    assert runs(stack, "reminder") == ["model unavailable"]
    stack.model.failing = 0  # and back an hour later
    stack.at("2026-10-30T10:30:00+00:00")
    stack.model.reply("Ana, you asked me to remind you: has Northwind answered about Q-1001?")
    stack.scheduler().work_due()
    assert "done" in runs(stack, "reminder") or any(
        "a5s is reminding you itself" in t for t in heard(stack, "ana")), (
        "the reminder Ana said yes to was marked given as its run opened, so once the model "
        f"failed it was never tried again, nor given by the core: runs {runs(stack, 'reminder')}, "
        f"reminded_at {kept(stack)[0]['reminded_at']}, what she heard {heard(stack, 'ana')}")


def test_a_reminder_for_a_time_due_while_the_model_is_down_is_given_once_it_is_back(stack):
    asked_and_confirmed(stack, on="2026-10-30T14:00")
    stack.at("2026-10-30T14:00:00+00:00")
    stack.model.failing = 5
    stack.scheduler().work_due()
    assert runs(stack, "reminder") == ["model unavailable"]
    stack.model.failing = 0
    stack.at("2026-10-30T14:10:00+00:00")
    stack.model.reply("Ana, it's two: has Northwind answered about Q-1001?")
    stack.scheduler().work_due()
    assert "done" in runs(stack, "reminder") or any(
        "a5s is reminding you itself" in t for t in heard(stack, "ana")), (
        f"the reminder for 14:00 is lost: runs {runs(stack, 'reminder')}, "
        f"what she heard {heard(stack, 'ana')}")


def test_an_escalation_never_says_someone_was_reminded_when_they_werent(stack):
    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ben's Q-1002 has passed
    stack.model.failing = 5  # but the model's down as the morning's chases run
    stack.scheduler().work_due()
    stack.model.failing = 0
    assert runs(stack, "obligation") == ["model unavailable", "model unavailable"]
    [chased] = [t for t in heard(stack, "ben") if "Q-1002" in t]  # a5s chased him itself
    assert "a5s is telling you itself" in chased
    stack.at("2026-11-09T09:30:00+00:00")  # Q-1002 is overdue, so his manager hears
    stack.model.reply("Ana, Q-1001 was due on Wednesday.")
    stack.scheduler().work_due()
    [escalated] = [t for t in heard(stack, "ana") if t.startswith("Q-1002")]
    assert "They were reminded on Mon 2 Nov." in escalated  # true: a5s reminded him
