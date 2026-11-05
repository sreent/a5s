"""Exports: all a5s keeps about someone, for their request to see it (docs/data-protection.md),
for the data protection officer alone, with nobody else's words, and recorded in the ledger in
counts."""

import json

from a5s import db
from a5s.core import groups
from test_departures import MONDAY, TUESDAY, sweep

SAID = "I'm working on Q-1002 today."


def export(stack, person: str, by: str = "noor"):
    with stack.client() as c:
        return c.post(f"/people/{person}/export", json={"by": by})


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
    assert found["evidence"]["runs"] == 1 and found["evidence"]["ledger"]["model"] == 1
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
    found = export(stack, "ben").json()
    assert [t["content"] for t in found["said_in_group_chats"]] == ["Ben's own words"]
    assert found["heard_in_group_chats"]["turns"] == 2
    assert "Ana's words" not in json.dumps(found)
    assert export(stack, chat).status_code == 400  # a group's conversation is nobody's own


def test_someone_who_left_is_exported_from_their_archive(stack, monkeypatch):
    stack.at(MONDAY)
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    people = dict(stack.gateway.scenario._people)
    del people["ben"]  # Ben leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    sweep(stack)
    stack.at(TUESDAY)
    assert sweep(stack)["archived"] == 1
    found = export(stack, "ben").json()
    [archive] = found["archives"]
    assert archive["name"].startswith("former:")
    assert [t["content"] for t in found["conversations"] if t["role"] == "person"] == [SAID]


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
    assert out.stat().st_mode & 0o777 == 0o600
    assert json.loads(out.read_text())["messages_received"][0]["text"] == SAID
