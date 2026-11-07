"""Round 8 of the critique: export and erasure keep to one holder of an id at a time, an erasure
waits for no run at work for its person nor works under an archive being made, and what a
group's summary held of someone goes with them (docs/critique.md, round 8)."""

import json

import httpx

from a5s import db
from a5s.core import groups
from a5s.worker import run_agent
from test_departures import MONDAY, TUESDAY, sweep
from test_erase import erase
from test_export import export
from test_groups import BEN, deliver, homeserver, mention  # noqa: F401 - a fixture
from test_r7_groups import (
    test_anyone_in_a_group_corrects_its_summary_with_their_name_on_it as ben_corrects_it,
)
from test_teams import activity, bot  # noqa: F401 - a fixture

NEW_BEN = "2026-11-04T10:00:00+00:00"  # the day the directory gives Ben's id to someone new
WAITING = "the bank's reply about my mortgage"  # the first Ben's own words


def first_ben_leaves(stack, monkeypatch, waiting: bool = False) -> str:
    """The first Ben says something, maybe what he waits on, and leaves; a day on, a5s archives
    what it kept for him, and the directory gives his id to a new Ben, who says something too.
    The first Ben's archive."""
    stack.at(MONDAY)
    with stack.client() as c:
        assert c.post("/obligations/sweep").status_code == 200
    stack.model.reply("Noted, Ben.")
    stack.say("I look after Contoso's refunds.", person="ben")
    if waiting:
        with db.transaction(stack.admin) as conn:  # as note_waiting keeps it, in his words
            assert conn.execute("update obligations set waiting_on = %s, waiting_until = "
                                "'2026-11-20', waiting_noted_at = %s where record = 'Q-1002' "
                                "and person = 'ben'", (WAITING, MONDAY)).rowcount == 1
    everyone = dict(stack.gateway.scenario._people)
    monkeypatch.setattr(stack.gateway.scenario, "_people",
                        {k: v for k, v in everyone.items() if k != "ben"})
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    monkeypatch.setattr(stack.gateway.scenario, "_people", everyone)  # a new Ben
    stack.at(NEW_BEN)
    stack.model.reply("Hello, and welcome.")
    stack.say("Hello, I'm new here.", person="ben")
    [archive] = export(stack, "ben").json()["archives"]
    return archive["name"]


def said_by_people(found: dict) -> list[str]:
    return [t["content"] for t in found["conversations"] if t["role"] == "person"]


def test_erasing_an_id_erases_its_holder_now_and_leaves_whoever_held_it_before(stack,
                                                                               monkeypatch):
    first = first_ben_leaves(stack, monkeypatch)
    r = erase(stack, "ben")  # the new Ben's request
    assert r.status_code == 200 and r.json()["archives"] == [first]  # for the officer to judge
    assert said_by_people(export(stack, "ben").json()) == []
    assert said_by_people(export(stack, first).json()) == ["I look after Contoso's refunds."]


def test_erasing_a_leavers_archive_leaves_whoever_holds_the_id_now(stack, monkeypatch):
    first = first_ben_leaves(stack, monkeypatch)
    assert erase(stack, first).json()["gone"]["turns"] == 2  # the first Ben's request
    assert said_by_people(export(stack, "ben").json()) == ["Hello, I'm new here."]
    assert export(stack, first).status_code == 404


def test_what_a_leaver_waited_on_reaches_nobody_once_they_leave(stack, monkeypatch):
    first_ben_leaves(stack, monkeypatch, waiting=True)
    with stack.client() as c:  # the records owe Q-1002 to the id still: the new Ben's
        assert c.post("/obligations/sweep").status_code == 200
    stack.model.reply("Q-1002 is waiting on finance.")
    stack.say("What's happening with Q-1002?", person="ben")
    assert WAITING not in json.dumps(stack.model.requests[-1]["body"]["messages"])
    with db.transaction(stack.admin) as conn:
        assert not conn.execute("select 1 from obligations where waiting_on is not null "
                                "or waiting_until is not null").fetchall()


def test_an_ids_holder_is_given_what_the_records_handed_them_and_nobody_before_them(
        stack, monkeypatch):
    first = first_ben_leaves(stack, monkeypatch)
    with db.transaction(stack.admin) as conn:  # Q-1001, opened before the first Ben left, goes
        conn.execute("insert into sample.changes (key, field, value, made_for) "  # to the new
                     "values ('Q-1001', 'owner', 'ben', 'the records system')")  # Ben now
    with stack.client() as c:
        assert c.post("/obligations/sweep").status_code == 200
    with db.transaction(stack.admin) as conn:
        assert conn.execute("update obligations set waiting_on = 'the courier''s note', "
                            "waiting_noted_at = %s where record = 'Q-1001' and person = 'ben'",
                            (NEW_BEN,)).rowcount == 1
    theirs, leavers = export(stack, "ben").json(), export(stack, first).json()
    assert "Q-1001" in [o["record"] for o in theirs["owed"]]
    assert "Q-1001" not in [o["record"] for o in leavers["owed"]]
    assert "courier" not in json.dumps(leavers)


def test_a_later_holders_archive_gives_none_of_an_earlier_holders(stack, approving, provider,
                                                                monkeypatch):
    from test_proposals import asked
    asked(stack)  # the first Ben asks for a change, held for Ana, as the database's clock runs
    everyone = dict(stack.gateway.scenario._people)
    people = {k: v for k, v in everyone.items() if k != "ben"}
    for leaves, archived, back in (("2026-11-08T10:00:00+00:00", "2026-11-09T10:30:00+00:00",
                                    "2026-11-10T09:00:00+00:00"),
                                   ("2026-11-11T10:00:00+00:00", "2026-11-12T10:30:00+00:00",
                                    None)):
        monkeypatch.setattr(stack.gateway.scenario, "_people", people)
        stack.at(leaves)
        sweep(stack)
        stack.at(archived)
        assert sweep(stack)["archived"] == 1
        if back:
            monkeypatch.setattr(stack.gateway.scenario, "_people", everyone)  # a new Ben
            stack.at(back)
            stack.model.reply("Hello.")
            stack.say("Hello, I'm new here.", person="ben")
    from test_officer import asked as officer_asked  # where people sign in, the officer asks
    officer_asked(approving, provider, "export", "ben")
    first, second = [a["name"] for a in export(stack, "ben").json()["archives"]]
    officer_asked(approving, provider, "export", first)
    assert len(export(stack, first).json()["changes_for_them"]) == 1
    officer_asked(approving, provider, "export", second)
    later = export(stack, second).json()
    assert later["changes_for_them"] == [] and said_by_people(later) == ["Hello, I'm new here."]


def test_an_erasure_waits_for_no_run_at_work_for_them(stack):
    tried: list[int] = []

    def worker(url: str, token: str, history: list[dict]) -> str:
        tried.append(erase(stack, "ben").status_code)  # while the run answering him works
        return run_agent(url, token, history)

    stack.model.reply("Noted, Ben.")
    stack.send("I'm working on Q-1002 today.", person="ben")
    stack.scheduler(worker=worker).answer_waiting()
    assert tried == [409]  # it might write what it read of him after he's gone: ask again
    gone = erase(stack, "ben").json()["gone"]  # once it's done
    assert gone["turns"] == 2 and export(stack, "ben").json()["conversations"] == []


def test_an_erasure_as_they_are_archived_waits_and_finds_the_archive(stack, monkeypatch):
    import threading
    import time

    import psycopg
    from psycopg.rows import dict_row

    from a5s.core import departures
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say("I look after Contoso's refunds.", person="ben")
    monkeypatch.setattr(stack.gateway.scenario, "_people", {
        k: v for k, v in stack.gateway.scenario._people.items() if k != "ben"})
    sweep(stack)
    stack.at(TUESDAY)
    archiving = psycopg.connect(stack.cfg.database_url, row_factory=dict_row)
    assert departures.sweep(archiving, stack.gateway.scenario, stack.gateway.clock()) == ["ben"]
    erased: dict = {}
    officer = threading.Thread(target=lambda: erased.update(r=erase(stack, "ben")))
    officer.start()
    time.sleep(1)  # the erasure waits for the archive being made
    archiving.commit()
    archiving.close()
    officer.join(60)
    [name] = erased["r"].json()["archives"]  # which the officer then erases by its name
    assert erase(stack, name).json()["gone"]["turns"] == 2


def test_an_answer_to_a_message_gone_meanwhile_is_refused_cleanly(stack):
    statuses: list[int] = []

    def seen(response: httpx.Response) -> None:
        if response.request.url.path == "/run/messages":
            statuses.append(response.status_code)

    def worker(url: str, token: str, history: list[dict]) -> str:
        with db.transaction(stack.admin) as conn:  # gone as the run works
            conn.execute("delete from outbox where inbound_id in (select id from inbound "
                         "where person = 'ben')")
            conn.execute("delete from inbound where person = 'ben'")
        return run_agent(url, token, history)

    stack.model.reply("Noted, Ben.")
    stack.send("I'm working on Q-1002 today.", person="ben")
    client = httpx.Client(base_url=stack.url, timeout=600, event_hooks={"response": [seen]})
    stack.scheduler(worker=worker, http=client).answer_waiting()
    assert statuses == [409]


def test_someone_erased_who_is_still_here_is_still_reached_where_they_work(stack, bot):  # noqa: F811
    stack.model.reply("Hello, Ana.")
    httpx.post(bot.url, json=activity("Hello"), headers=bot.auth()).raise_for_status()
    stack.scheduler().answer_waiting()
    assert erase(stack, "ana").status_code == 200  # at her request: she still works here
    stack.suspend(by="ben")
    stack.at("2026-11-09T09:00:00+00:00")  # Ben's Q-1002 was due on Friday: Ana is next up
    sent = len(bot.sent)
    stack.scheduler().work_due()
    assert [m for m in bot.sent[sent:] if m["text"].startswith("Q-1002")]  # in Teams, as ever
    assert export(stack, "ana").json()["messages_received"] == []  # with nothing she said


def test_what_someone_said_to_correct_a_groups_summary_is_theirs(stack, homeserver):  # noqa: F811
    ben_corrects_it(stack, homeserver)
    [correction] = export(stack, "ben").json()["corrections_in_group_summaries"]
    assert correction["said"] == "Q-1001 goes to Ana, not Ben"
    gone = erase(stack, "ben").json()["gone"]
    assert gone["group_summaries"] == 1  # made again from what's left, by the group's next run
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select * from summaries").fetchall() == []


def test_someone_who_leaves_is_named_in_nobody_elses_reminders(stack, monkeypatch):
    chat = groups.key("matrix", "!team:a5s.test")
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say("Hello", person="ben")
    with db.transaction(stack.admin) as conn:  # offered to Ana in a group Ben was in
        conn.execute("insert into reminders (person, agent, instance_id, about, due_at, "
                     "offered_at, offered_run, asked_at, conversation, heard_by) values ('ana', "
                     "'assistant', 'assistant-finance', 'Chase the bank about Q-1002', "
                     "now() + interval '1 day', now(), gen_random_uuid(), now(), %s, "
                     "array['ana', 'ben'])", (chat,))
    monkeypatch.setattr(stack.gateway.scenario, "_people", {
        k: v for k, v in stack.gateway.scenario._people.items() if k != "ben"})
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    with db.transaction(stack.admin) as conn:
        heard = conn.execute("select heard_by from reminders where person = 'ana'").fetchone()
    assert "ben" not in heard["heard_by"] and len(heard["heard_by"]) == 2


def test_a_directory_that_names_nobody_for_a_day_archives_nobody_for_a_week(stack, monkeypatch):
    stack.at(MONDAY)
    for person in ("ana", "ben", "chen", "dana"):
        stack.model.reply("Noted.")
        stack.say("Hello", person=person)
    monkeypatch.setattr(stack.gateway.scenario, "_people", {})  # emptied, by mistake
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 0  # many at once: the directory, more likely
    from a5s.core import status
    with db.transaction(stack.admin) as conn:
        assert "not yet archived: 4" in status.told(status.report(conn, []))
    stack.at("2026-11-09T10:30:00+00:00")  # still missing a week on: they've left
    assert sweep(stack)["archived"] == 4
