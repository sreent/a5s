"""Retention: a conversation goes 12 months after the last thing a person and an agent said to
each other, and the values a run was handed, and what it read, once it has been over for an
hour. The ledger records how much each sweep deleted, and stays whole."""

from a5s import db

WORDS = (("turns", "at"), ("inbound", "received_at"), ("outbox", "at"), ("summaries", "updated_at"))


def sweep(stack) -> dict:
    with stack.client() as c:
        r = c.post("/retention/sweep")
    r.raise_for_status()
    return r.json()["deleted"]


def aged(stack, person: str, agent: str = "assistant") -> None:
    """Make all that someone and an agent said to each other 13 months older."""
    with db.transaction(stack.admin) as conn:
        for table, at in WORDS:
            conn.execute(f"update {table} set {at} = {at} - interval '13 months' "
                         "where person = %s and agent = %s", (person, agent))


def kept(stack, person: str) -> dict[str, int]:
    with db.transaction(stack.admin) as conn:
        return {table: conn.execute(f"select count(*) as n from {table} where person = %s",
                                    (person,)).fetchone()["n"] for table, _ in WORDS}


def test_a_conversation_goes_twelve_months_after_its_last_message(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    stack.model.reply("Hello, Ben.")
    stack.say("Hello", person="ben")
    with db.transaction(stack.admin) as conn:  # what no run is given any more, folded
        conn.execute("insert into summaries (person, agent, topic, body, through) "
                     "values ('ana', 'assistant', 'general', '{}', 1)")
    aged(stack, "ana")
    assert sweep(stack) == {"turns": 2, "messages": 2, "summaries": 1}
    assert kept(stack, "ana") == {"turns": 0, "inbound": 0, "outbox": 0, "summaries": 0}
    assert kept(stack, "ben") == {"turns": 2, "inbound": 1, "outbox": 1, "summaries": 0}
    [entry] = [e for e in stack.ledger() if e["kind"] == "retention"]
    assert entry["args"] == {"turns": 2, "messages": 2, "summaries": 1}
    assert sweep(stack) == {}  # nothing more to delete, so nothing more recorded
    assert [e for e in stack.ledger() if e["kind"] == "retention"] == [entry]
    assert stack.verify().ok


def test_a_conversation_someone_came_back_to_is_kept_whole(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    aged(stack, "ana")
    stack.model.reply("Welcome back.")
    stack.say("I'm back")
    assert sweep(stack) == {}
    assert kept(stack, "ana")["turns"] == 4


def test_each_conversation_is_kept_by_its_own_last_message(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:  # and lately, with another agent
        conn.execute("insert into turns (person, agent, role, content) "
                     "values ('ana', 'watcher', 'person', 'What changed?')")
    aged(stack, "ana")
    assert sweep(stack)["turns"] == 2
    with db.transaction(stack.admin) as conn:
        assert [r["agent"] for r in conn.execute("select agent from turns")] == ["watcher"]


def test_the_values_a_run_handled_go_once_it_has_been_over_an_hour(stack):
    run, _ = stack.open_run()
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into run_handles (run_id, handle, field, value, source) values "
                     "(%s, '7f3a9c2b', 'contact', 'buyer@northwind.example', 'search_records')",
                     (run,))
        conn.execute("insert into run_reads (run_id, source, kind, norm, text) values "
                     "(%s, 'search_records', 'key', 'Q-1001', 'Q-1001')", (run,))
        reads = conn.execute("select count(*) as n from run_reads where run_id = %s",
                             (run,)).fetchone()["n"]
    assert sweep(stack) == {}  # it's still open
    with stack.client() as c:
        c.post(f"/runs/{run}/close", json={"outcome": "done"}).raise_for_status()
    assert sweep(stack) == {}  # over, but not for an hour
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set closed_at = closed_at - interval '61 minutes' where id = %s",
                     (run,))
    assert sweep(stack) == {"handles": 1, "reads": reads}
    with db.transaction(stack.admin) as conn:
        assert not conn.execute("select 1 from run_handles union all select 1 from run_reads"
                                ).fetchall()


def test_notes_reminders_and_a5s_notices_go_twelve_months_after_they_ended(stack):
    with db.transaction(stack.admin) as conn:
        for text, ended in (("Short answers.", "now() - interval '13 months'"),
                            ("Bullet points.", "null")):
            conn.execute("insert into profile_notes (person, agent, text, offered_at, offered_run, "
                         "asked_at, confirmed_at, ended_at) values ('ana', 'assistant', %s, "
                         "now() - interval '14 months', gen_random_uuid(), "
                         f"now() - interval '14 months', now() - interval '14 months', {ended})",
                         (text,))
        agreed = "confirmed_at = now() - interval '14 months'"
        for about, when in (
                ("given long ago", f"{agreed}, reminded_at = now() - interval '13 months'"),
                ("cancelled lately", f"{agreed}, cancelled_at = now() - interval '1 month'"),
                ("never agreed to", "confirmed_at = null"),
                ("due next year", f"{agreed}, due_at = now() + interval '1 month'")):
            row = conn.execute(
                "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
                "offered_run, asked_at) values ('ana', 'assistant', 'assistant-finance', %s, "
                "now() - interval '13 months', now() - interval '14 months', gen_random_uuid(), "
                "now() - interval '14 months') returning id", (about,)).fetchone()
            conn.execute(f"update reminders set {when} where id = %s", (row["id"],))
        conn.execute("insert into outbox (person, channel, text, at) values "
                     "('ana', 'local', 'An escalation, long ago.', now() - interval '13 months'), "
                     "('ana', 'local', 'An escalation, lately.', now() - interval '1 month')")
    assert sweep(stack) == {"notes": 1, "reminders": 2, "messages": 1}
    with db.transaction(stack.admin) as conn:
        assert [r["text"] for r in conn.execute("select text from profile_notes")] == [
            "Bullet points."]
        assert [r["about"] for r in conn.execute("select about from reminders order by id")] == [
            "cancelled lately", "due next year"]
        assert [r["text"] for r in conn.execute("select text from outbox")] == [
            "An escalation, lately."]
