"""Exports: all a5s keeps about someone, for their request to see it (docs/data-protection.md),
for the data protection officer alone, with nobody else's words, and recorded in the ledger in
counts."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from a5s import db
from a5s.core import groups
from test_departures import MONDAY, TUESDAY, sweep
from test_proposals import asked, decide, held
from test_proposals import sweep as sweep_changes

SAID = "I'm working on Q-1002 today."


def export(stack, person: str, by: str = "noor", identity: str | None = None):
    with stack.client() as c:
        return c.post(f"/people/{person}/export", json={"by": by, "identity": identity})


def test_the_data_protection_officer_exports_all_a5s_keeps_about_someone(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")  # Ana's, not Ben's
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into preferences (person, name, value, set_at) values "
                     "('ben', 'digest-time', '08:30', now())")
        conn.execute("insert into obligations (scenario, source, record, person, title, "
                     "opened_at, due_at, waiting_on) values ('sample', 'records', 'Q-1002', "
                     "'ben', 'Refund for a duplicate payment', now() - interval '2 days', "
                     "now() + interval '1 day', 'the bank''s reply')")
    r = export(stack, "ben")
    assert r.status_code == 200, r.text
    found = r.json()
    assert found["person"] == "ben" and found["archives"] == []
    assert [t["content"] for t in found["conversations"] if t["role"] == "person"] == [SAID]
    assert any(t["content"] == "Noted, Ben." for t in found["conversations"])
    assert [m["text"] for m in found["messages_received"]] == [SAID]
    assert [(p["name"], p["value"]) for p in found["preferences"]] == [("digest-time", "08:30")]
    [owed] = found["owed"]
    assert (owed["record"], owed["waiting_on"]) == ("Q-1002", "the bank's reply")
    assert [d["tokens"] for d in found["days"]["budget"]] == [15]
    assert found["evidence"]["runs"] == 1 and found["evidence"]["ledger"]["calls to a model"] == 1
    assert "Hello, Ana." not in json.dumps(found)


def test_only_the_data_protection_officer_may_export_it(stack):
    for who in ("ana", "kofi", "ben"):  # an approver, assurance, and Ben himself
        r = export(stack, "ben", by=who)
        assert r.status_code == 403 and "only the data protection officer" in r.text
    assert not [e for e in stack.ledger() if e["action"] == "export"]


def test_in_a_group_chat_it_gives_what_they_said_and_only_counts_what_others_did(stack):
    chat = groups.key("matrix", "!team:a5s.test")
    with db.transaction(stack.admin) as conn:
        for speaker, role, content in (("ben", "person", "Ben's own words"),
                                       ("ana", "person", "Ana's words"),
                                       (None, "agent", "The assistant's answer")):
            conn.execute("insert into turns (person, agent, topic, role, content, speaker, "
                         "heard_by) values (%s, 'assistant', 'general', %s, %s, %s, "
                         "array['ana', 'ben'])", (chat, role, content, speaker))
        conn.execute(  # and the facts its summary keeps, each with who said it
            "insert into summaries (person, agent, topic, body, through, heard_by) values "
            "(%s, 'assistant', 'Q-1002', %s, 3, array['ana', 'ben'])",
            (chat, json.dumps({"facts": [
                {"value": "Q-1002", "who": "Ben Okafor", "speaker": "ben", "when": "Monday"},
                {"value": "£1,240.50", "who": "Ana Ortiz", "speaker": "ana",
                 "when": "Monday"}]})))
    found = export(stack, "ben").json()
    assert [t["content"] for t in found["said_in_group_chats"]] == ["Ben's own words"]
    assert [f["value"] for f in found["facts_in_group_summaries"]] == ["Q-1002"]
    assert found["heard_in_group_chats"] == {"turns": 2, "summaries": 1, "answers": 0}
    assert "Ana's words" not in json.dumps(found) and "1,240.50" not in json.dumps(found)
    assert export(stack, chat).status_code == 400  # a group's conversation is nobody's own


def test_someone_who_left_is_exported_from_their_archive_by_its_name(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    with db.transaction(stack.admin) as conn:  # a question asked for him alone, while he was here
        conn.execute("insert into questions (id, asked_by_run, asker, asked, acts_for, text, "
                     "read_outside, asked_at) values (gen_random_uuid(), gen_random_uuid(), "
                     "'assistant-finance', 'watcher-finance', '{ben}', 'What changed for Ben?', "
                     "false, %s)", (MONDAY,))
    everyone = dict(stack.gateway.scenario._people)
    people = dict(everyone)
    del people["ben"]  # Ben leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    found = export(stack, "ben").json()  # what's his id's now: nothing, and where he went
    [archive] = found["archives"]
    assert archive["name"].startswith("former:") and found["conversations"] == []
    old = export(stack, archive["name"]).json()
    assert [t["content"] for t in old["conversations"] if t["role"] == "person"] == [SAID]
    assert [q["text"] for q in old["questions"]] == ["What changed for Ben?"]

    monkeypatch.setattr(stack.gateway.scenario, "_people", everyone)  # the id goes to someone
    stack.at("2026-11-04T10:00:00+00:00")  # new, who has nothing of the Ben before them
    stack.model.reply("Hello.")
    stack.say("Hello, I'm new here.", person="ben")
    found = export(stack, "ben").json()
    assert [t["content"] for t in found["conversations"] if t["role"] == "person"] == [
        "Hello, I'm new here."]
    assert found["questions"] == [] and SAID not in json.dumps(found)


def test_what_a_group_was_told_and_questions_for_others_too_are_only_counted(stack):
    chat = groups.key("matrix", "!team:a5s.test")
    with db.transaction(stack.admin) as conn:
        asked = conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                             "reply_to, conversation, members) values (gen_random_uuid(), "
                             "'matrix', 'm1', 'ana', 'assistant', 'What did Ben just say?', '{}', "
                             "%s, array['ana', 'ben']) returning id", (chat,)).fetchone()["id"]
        conn.execute("insert into outbox (inbound_id, person, channel, text, agent) values "
                     "(%s, 'ana', 'matrix', 'Ben said he is off next week.', 'assistant')",
                     (asked,))
        conn.execute("insert into questions (id, asked_by_run, asker, asked, acts_for, text, "
                     "read_outside) values (gen_random_uuid(), gen_random_uuid(), "
                     "'assistant-finance', 'watcher-finance', '{ana,ben}', "
                     "'What is open for Ana and Ben?', false)")
    found = export(stack, "ana").json()
    assert found["messages_sent"] == [] and found["heard_in_group_chats"]["answers"] == 1
    assert found["questions"] == [] and found["questions_with_others"] == 1
    assert [m["text"] for m in found["messages_received"]] == ["What did Ben just say?"]
    text = json.dumps(found)
    assert "Ben said he is off" not in text and "open for Ana and Ben" not in text


def test_a_change_is_said_without_what_its_records_held_or_whom_else_it_was_for(
        stack, approving, provider):
    asked(stack)  # Ben asks for a change to Q-1002, which Ana decides
    decide(approving, provider, [held(stack)[0]["digest"]])
    sweep_changes(stack)  # it's made, and drawn as a sample of the agent's work
    with db.transaction(stack.admin) as conn:  # which Dana grades
        conn.execute("update samples set grade = 'right', graded_by = 'dana', graded_at = now()")
    from test_officer import asked as officer_asked  # where people sign in, the officer asks
    for person in ("ben", "ana", "dana"):  # for each, on the core's page
        officer_asked(approving, provider, "export", person)
    [change] = export(stack, "ben").json()["changes_for_them"]
    assert change["said"] == "Change a customer question's due date: Q-1002, with due 2026-11-13."
    decider = export(stack, "ana").json()
    assert decider["changes_they_could_decide"] == 1 and len(decider["decisions"]) == 1
    graded = export(stack, "dana").json()
    [sample] = graded["samples"]
    assert (sample["as"], sample["said"], sample["grade"]) == (["grader"], None, "right")
    assert "as it stood" not in json.dumps(graded) and "Ben Okafor" not in json.dumps(graded)


def test_an_id_the_directory_doesnt_know_and_a5s_holds_nothing_under_is_not_found(stack):
    r = export(stack, "bne")  # Ben, mistyped
    assert r.status_code == 404 and "check the id" in r.text
    assert not [e for e in stack.ledger() if e["action"] == "export"]


def test_the_ledger_records_each_export_in_counts_and_none_of_what_was_said(stack):
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    assert export(stack, "ben").status_code == 200
    [entry] = [e for e in stack.ledger() if e["action"] == "export"]
    assert (entry["kind"], entry["acts_for"]) == ("admin", ["ben"])
    assert (entry["args"]["person"], entry["args"]["by"]) == ("ben", "noor")
    assert entry["args"]["counts"]["conversations"] == 2
    assert SAID not in json.dumps(entry)


def test_the_officer_writes_it_to_a_file_only_they_may_read(stack, tmp_path, monkeypatch, capsys):
    from a5s import cli
    from conftest import SERVICE_TOKEN
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    out = tmp_path / "ben.json"
    cli.main(["export", "--person", "ben", "--by", "noor", "--out", str(out)])
    assert "Wrote all a5s keeps about ben" in capsys.readouterr().out
    if os.name == "nt":
        system = Path(os.environ["SystemRoot"]) / "System32"
        who = subprocess.check_output([str(system / "whoami.exe")], text=True).strip()
        acl = subprocess.check_output([str(system / "icacls.exe"), str(out)], text=True)
        entries = [line.strip() for line in acl.splitlines() if ":(" in line]
        assert len(entries) == 1
        assert entries[0].casefold().endswith(f"{who}:(F)".casefold())
    else:
        assert out.stat().st_mode & 0o777 == 0o600
    assert json.loads(out.read_text())["messages_received"][0]["text"] == SAID


def test_the_officer_never_writes_over_a_file_already_there(stack, tmp_path, monkeypatch):
    from a5s import cli
    from conftest import SERVICE_TOKEN
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    there = tmp_path / "ben.json"
    there.write_text("someone else's")
    there.chmod(0o644)
    with pytest.raises(SystemExit, match="is there already"):
        cli.main(["export", "--person", "ben", "--by", "noor", "--out", str(there)])
    assert there.read_text() == "someone else's"
