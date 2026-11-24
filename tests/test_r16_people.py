"""Round 16, reviewer C: people's data and conversations.

- C1: searching the conversation gave an unmarked run what a marked run wrote, from before a
  fresh start too, and from a task's topic kept apart, so a change it then asked for went
  unmarked."""

from __future__ import annotations

from a5s import db
from a5s.services import context


def test_what_search_finds_of_a_marked_run_marks_the_run_that_found_it(stack):
    stack.model.reply("They ask INV-1042 be paid on 26 Nov, THB 86,000.")
    stack.say("What does the supplier's mail ask?", person="ben")
    run, token = stack.open_run("ben")  # unmarked, as what it's given carries nothing,
    with db.transaction(stack.admin) as conn:  # such as when that answer is past its budget:
        conn.execute("update runs set read_outside = true where id <> %s", (run,))  # that
        assert not conn.execute("select read_outside from runs where id = %s",  # run read a
                                (run,)).fetchone()["read_outside"]  # supplier's mail
    with stack.client(token) as c:
        found = c.post("/run/tools/search_conversation", json={"args": {"query": "INV-1042"}})
    assert found.status_code == 200 and found.json()["result"]["found"], found.text
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select read_outside from runs where id = %s",
                            (run,)).fetchone()["read_outside"]


def test_search_finds_nothing_from_before_a_fresh_start(stack):
    stack.model.reply("Noted: the Leeds office.")
    stack.say("The Leeds office is where I work.", person="ben")
    with db.transaction(stack.admin) as conn:  # as when they said "start afresh" since
        through = conn.execute("select max(id) as n from turns").fetchone()["n"]
        conn.execute("insert into fresh_starts (person, agent, through) values ('ben', "
                     "'assistant', %s)", (through,))
        assert context.fresh(conn, "ben", "assistant") == through
    _, token = stack.open_run("ben")
    with stack.client(token) as c:
        found = c.post("/run/tools/search_conversation", json={"args": {"query": "Leeds"}})
    assert [t["said"] for t in found.json()["result"]["found"]] == []


def test_a_groups_answer_kept_through_an_erasure_names_its_asker_by_the_archive_alone(database):
    """C2: its route still named Ana, and listed her among the chat's members."""
    from datetime import UTC, datetime

    from psycopg.types.json import Jsonb

    from a5s.core import erasure
    with db.transaction(database) as conn:
        conn.execute("insert into outbox (person, channel, text, route, delivered_at) values "
                     "('ana', 'teams', 'The refund is on its way.', %s, now())",
                     (Jsonb({"channel": "teams", "reply_to": {}, "person": "ana",
                             "members": ["ana", "ben"]}),))
    with db.transaction(db.as_role(database, "gateway")) as conn:
        erasure.erase(conn, "ana", datetime.now(UTC), here=True)
    with db.transaction(database) as conn:
        [kept] = conn.execute("select person, route from outbox").fetchall()
    assert "ana" not in str(kept["route"]) and kept["route"]["members"][1] == "ben"
    assert kept["route"]["person"] == kept["person"] == kept["route"]["members"][0]


def test_erasing_an_archive_by_name_takes_what_they_asked_out_of_samples(database):
    """C3: samples keep the id, never an archive's name, so erasing the archive by its name
    left what they asked; and erasing an id took every past holder's words, in no window."""
    from datetime import UTC, datetime, timedelta

    from a5s.core import departures, erasure
    now = datetime.now(UTC)
    with db.transaction(database) as conn:
        for asked, at in (("Move Q-1 for me, Nok.", now - timedelta(days=30)),
                          ("Move Q-2 for me, the new Nok.", now + timedelta(days=1))):
            conn.execute(
                "insert into samples (scenario, kind, release, definition, instance_id, run_id, "
                "part, action, said, records, acts_for, drawn_at, asked) values ('sample', "
                "'proposal', 'r1', 'assistant', 'assistant-finance', gen_random_uuid(), "
                "'billing', 'move', 'Moves it', '{}', '{nok}', %s, %s)", (at, asked))
    with db.transaction(db.as_role(database, "gateway")) as conn:
        archive = departures.rename(conn, "nok", now)  # she left, and the id came back after
        conn.execute("insert into departures (person, missing_since, archived_at, archived_as) "
                     "values ('nok', %s, %s, %s)", (now - timedelta(days=60), now, archive))
        erasure.erase(conn, archive, now + timedelta(days=2))
    with db.transaction(database) as conn:
        left = [r["asked"] for r in conn.execute("select asked from samples order by drawn_at")]
    assert left == [None, "Move Q-2 for me, the new Nok."]  # hers alone, in her time


def test_a_customers_erasure_reaches_their_reminders_repeats_and_notes(stack):
    """C5: it put a stand-in in their messages, but not in what agents keep of them besides."""
    from a5s.core import customers
    address = "pat@fabrikam.example"
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into reminders (person, agent, instance_id, about, due_at, "
                     "offered_at, offered_run, asked_at) values ('ben', 'assistant', "
                     "'assistant-finance', %s, now(), now(), gen_random_uuid(), now())",
                     (f"call {address} on Friday",))
        conn.execute("insert into profile_notes (person, agent, text, offered_at, offered_run, "
                     "asked_at) values ('ben', 'assistant', %s, now(), gen_random_uuid(), now())",
                     (f"{address} pays late",))
    with db.transaction(stack.cfg.database_url) as conn:
        done = customers.erase(conn, address)
    assert {"what people asked to be reminded of", "notes agents keep of people"} <= set(
        done["gone"]), done
    with db.transaction(stack.admin) as conn:
        about = conn.execute("select about from reminders").fetchone()["about"]
    assert address not in about and customers.STAND_IN in about
