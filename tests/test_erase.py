"""Erasure: all a5s keeps about someone, erased at their request (docs/data-protection.md), by
the data protection officer alone, who confirms the id. What's evidence of what agents did
stays, and the ledger records each erasure in counts."""

import json

from a5s import db
from a5s.core import groups
from test_departures import MONDAY, TUESDAY, sweep
from test_export import SAID, export
from test_proposals import asked, held


def erase(stack, person: str, by: str = "noor", confirm: str | None = "same",
          identity: str | None = None):
    with stack.client() as c:
        return c.post(f"/people/{person}/erase", json={
            "by": by, "identity": identity, "confirm": person if confirm == "same" else confirm})


def test_the_officer_erases_what_a5s_keeps_about_someone_and_keeps_the_evidence(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")  # Ana's, which stays
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into preferences (person, name, value, set_at) values "
                     "('ben', 'digest-time', '08:30', now())")
        conn.execute("insert into obligations (scenario, source, record, person, title, "
                     "opened_at, due_at, waiting_on, waiting_until, waiting_noted_at) values "
                     "('sample', 'records', 'Q-1002', 'ben', 'Refund for a duplicate payment', "
                     "now() - interval '2 days', now() + interval '1 day', 'the bank''s reply', "
                     "now() + interval '3 days', now())")
    r = erase(stack, "ben")
    assert r.status_code == 200, r.text
    assert r.json()["gone"]["turns"] == 2 and r.json()["gone"]["preferences"] == 1
    found = export(stack, "ben").json()
    assert found["conversations"] == [] and found["messages_received"] == []
    assert found["preferences"] == [] and found["days"]["budget"] == []
    [owed] = found["owed"]  # still owed, as the records say, but not in Ben's words
    assert (owed["record"], owed["waiting_on"]) == ("Q-1002", None)
    assert owed["waiting_until"] is not None  # so chasing him waits, as he asked
    assert found["evidence"]["runs"] == 1  # what the agent did for him stays
    assert SAID not in json.dumps(found)
    assert [t["content"] for t in export(stack, "ana").json()["conversations"]
            if t["role"] == "person"] == ["Hello"]


def test_only_the_officer_erases_and_only_the_id_confirmed(stack):
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    for who in ("ana", "kofi", "ben"):
        assert erase(stack, "ben", by=who).status_code == 403
    assert erase(stack, "ben", confirm=None).status_code == 400
    assert erase(stack, "ben", confirm="bne").status_code == 400  # mistyped: nobody's erased
    assert erase(stack, "bne", confirm="bne").status_code == 404
    assert [t["content"] for t in export(stack, "ben").json()["conversations"]
            if t["role"] == "person"] == [SAID]
    assert not [e for e in stack.ledger() if e["action"] == "erase"]


def test_in_a_group_chat_their_words_go_and_nothing_links_them_to_where_they_were(stack):
    chat = groups.key("matrix", "!team:a5s.test")
    with db.transaction(stack.admin) as conn:
        for speaker, role, content in (("ben", "person", "Ben's own words"),
                                       ("ana", "person", "Ana's words"),
                                       (None, "agent", "The assistant's answer")):
            conn.execute("insert into turns (person, agent, topic, role, content, speaker, "
                         "heard_by) values (%s, 'assistant', 'general', %s, %s, %s, "
                         "array['ana', 'ben'])", (chat, role, content, speaker))
        conn.execute(
            "insert into summaries (person, agent, topic, body, through, heard_by) values "
            "(%s, 'assistant', 'Q-1002', %s, 3, array['ana', 'ben'])",
            (chat, json.dumps({"facts": [
                {"value": "Q-1002", "who": "Ben Okafor", "speaker": "ben", "when": "Monday"},
                {"value": "£1,240.50", "who": "Ana Ortiz", "speaker": "ana",
                 "when": "Monday"}]})))
    gone = erase(stack, "ben").json()["gone"]
    assert (gone["said_in_groups"], gone["facts_in_groups"]) == (1, 1)
    with db.transaction(stack.admin) as conn:
        turns = conn.execute("select content, heard_by from turns where person = %s "
                             "order by id", (chat,)).fetchall()
        [summary] = conn.execute("select body, heard_by from summaries").fetchall()
    assert [t["content"] for t in turns] == ["Ana's words", "The assistant's answer"]
    assert all("ben" not in t["heard_by"] and "ana" in t["heard_by"] for t in turns)
    assert [f["value"] for f in summary["body"]["facts"]] == ["£1,240.50"]
    assert "ben" not in summary["heard_by"]


def test_someone_who_left_is_erased_with_their_archive_and_its_record(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    people = dict(stack.gateway.scenario._people)
    del people["ben"]  # Ben leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    [archive] = export(stack, "ben").json()["archives"]
    gone = erase(stack, "ben").json()["gone"]
    assert gone["archives"] == 1 and gone["turns"] == 2
    found = export(stack, "ben").json()  # no archive, nothing of his: only the evidence
    assert found["archives"] == [] and found["conversations"] == []
    assert found["evidence"]["runs"] == 1
    assert export(stack, archive["name"]).status_code == 404  # gone, and its record with it


def test_the_changes_asked_for_them_stay_as_evidence(stack, approving, provider):
    asked(stack)  # Ben asks for a change, held for Ana
    officer = provider.id_token(person="noor")
    r = erase(stack, "ben", identity=officer)
    assert r.status_code == 200, r.text
    assert [p["acts_for"] for p in held(stack)] == [["ben"]]


def test_the_ledger_records_each_erasure_in_counts_and_none_of_what_went(stack):
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    assert erase(stack, "ben").status_code == 200
    [entry] = [e for e in stack.ledger() if e["action"] == "erase"]
    assert (entry["kind"], entry["acts_for"]) == ("admin", ["ben"])
    assert (entry["args"]["person"], entry["args"]["by"]) == ("ben", "noor")
    assert entry["args"]["erased"]["turns"] == 2
    assert SAID not in json.dumps(entry) and "former:" not in json.dumps(entry)


def test_the_command_line_says_what_went_and_what_stays(stack, monkeypatch, capsys):
    from a5s import cli
    from conftest import SERVICE_TOKEN
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    cli.main(["erase", "--person", "ben", "--confirm", "ben", "--by", "noor"])
    said = capsys.readouterr().out
    assert said.startswith("Erased what a5s kept about ben: ") and "2 from turns" in said
    assert "stay, as evidence of what agents did" in said
