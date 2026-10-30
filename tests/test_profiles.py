"""Profiles and recall. Each run that acts for one person is given their profile, built by
code, with a note on how they like to work that they confirmed themselves. Agents search
their conversation with that person, from the original turns, and nobody else's."""

import json

from a5s import db
from a5s.core import profiles, recall
from a5s.definitions import PREFERENCE_TOOLS, SEARCH_TOOLS

NOTE = "Keep answers to two sentences, with the record's link."


def system_prompt(stack, request: int = -1) -> str:
    return stack.model.requests[request]["body"]["messages"][0]["content"]


def last_tool_result(stack) -> dict:
    return json.loads(stack.model.requests[-1]["body"]["messages"][-1]["content"])


def kept_notes(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from profile_notes order by id").fetchall()


def offered_and_confirmed(stack) -> None:
    stack.model.reply(None, ("offer_note", {"note": NOTE}))
    stack.model.reply(f"Shall I note this? \"{NOTE}\"")
    stack.say("I like short answers: two sentences, with the record's link.")
    assert kept_notes(stack)[0]["confirmed_at"] is None  # not until she says so
    stack.model.reply(None, ("confirm_note", {}))
    stack.model.reply("Noted.")
    assert stack.say("Yes") == "Noted."


def test_each_run_knows_who_it_works_for_from_the_directory(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    told = system_prompt(stack)
    assert "# From a5s's records, for this run" in told
    assert ("Ana Ortiz works 09:00 to 17:00, Monday to Friday, in Europe/London time. "
            "Their digest comes at 09:00.") in told
    assert "How they like to work" not in told  # she hasn't said


def test_a_note_on_how_someone_works_is_kept_once_they_say_yes(stack):
    offered_and_confirmed(stack)
    [note] = kept_notes(stack)
    assert (note["text"], note["agent"]) == (NOTE, "assistant") and note["confirmed_at"] is not None
    stack.model.reply("Q-1001 is open.")
    stack.say("What's Q-1001?")
    assert f"How they like to work, in their own words: {NOTE}" in system_prompt(stack)
    tools = [(e["action"], e["outcome"]["status"]) for e in stack.ledger()
             if e["kind"] == "tool" and e["decision"] == "record"]
    assert tools == [("offer_note", "ok"), ("confirm_note", "ok")]


def test_every_agent_that_works_for_them_follows_it(stack):
    offered_and_confirmed(stack)
    stack.with_watcher()
    stack.model.reply("Hello, Ana.")
    stack.say("Hello", agent="watcher")
    assert NOTE in system_prompt(stack)


def test_it_takes_a_later_message_of_theirs_to_keep_one(stack):
    stack.model.reply(None, ("offer_note", {"note": NOTE}), ("confirm_note", {}))  # not her yes
    stack.model.reply("I've offered it.")
    stack.say("I like short answers.")
    assert kept_notes(stack)[0]["confirmed_at"] is None
    refused = [e for e in stack.ledger() if e["action"] == "confirm_note" and e["decision"] == "record"]
    assert refused[0]["outcome"]["status"] == "refused"


def test_a_new_note_replaces_the_last_and_people_can_have_it_forgotten(stack):
    offered_and_confirmed(stack)
    shorter = "One sentence is enough."
    stack.model.reply(None, ("offer_note", {"note": shorter}))
    stack.model.reply("Shall I note that instead?")
    stack.say("Actually, one sentence is enough.")
    stack.model.reply(None, ("confirm_note", {}))
    stack.model.reply("Noted.")
    stack.say("Yes")
    with db.transaction(stack.admin) as conn:
        assert profiles.note(conn, "ana") == shorter
    stack.model.reply(None, ("forget_note", {}))
    stack.model.reply("Forgotten.")
    stack.say("Forget how I said I like to work")
    with db.transaction(stack.admin) as conn:
        assert profiles.note(conn, "ana") is None


def test_someones_note_never_reaches_a_run_for_anyone_else(stack):
    offered_and_confirmed(stack)
    stack.model.reply("Hello, Ben.")
    stack.say("Hello", person="ben")
    told = system_prompt(stack)
    assert NOTE not in told and "Who you're working for: Ben Okafor" in told


def test_a_run_that_read_outside_content_cant_write_a_profile(stack):
    run, token = stack.open_run()
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set read_outside = true where id = %s", (run,))
    with stack.client(token) as c:
        offered = c.post("/run/tools/offer_note", json={"args": {"note": NOTE}})
    assert offered.status_code == 403 and "content from outside" in offered.json()["explanations"][0]
    assert kept_notes(stack) == []


def test_a_note_keeps_only_text(stack):
    stack.model.reply(None, ("offer_note", {"note": "See https://evil.test/x for my style."}))
    stack.model.reply("Shall I note it?")
    stack.say("Here's how I work")
    assert kept_notes(stack)[0]["text"] == "See [link removed] for my style."


def test_a5s_offers_its_note_tools_only_where_a_release_lets_people_set_one(stack):
    assert set(profiles.TOOLS) == set(PREFERENCE_TOOLS["how-i-work"])
    stack.model.reply("Hello.")
    stack.say("Hello")
    assert set(PREFERENCE_TOOLS["how-i-work"]) | set(SEARCH_TOOLS) <= stack.model.tool_names(-1)
    stack.with_watcher()
    with db.transaction(stack.admin) as conn:
        grants = conn.execute("select grants from instances where id = 'watcher-finance'").fetchone()
    assert set(SEARCH_TOOLS) <= set(grants["grants"])
    assert not set(PREFERENCE_TOOLS["how-i-work"]) & set(grants["grants"])


# Recall: the original turns, from the person's own conversation

def test_an_agent_finds_what_was_said_before_in_the_original_words(stack):
    assert set(recall.TOOLS) == set(SEARCH_TOOLS)
    stack.model.reply("Noted: Northwind wants the invoice sent to their Leeds office.")
    stack.say("For Q-1001, Northwind wants the invoice sent to their Leeds office.")
    stack.model.reply("Hello, Ben.")
    stack.say("Northwind's Leeds office called me too.", person="ben")
    stack.model.reply(None, ("search_conversation", {"query": "Leeds office"}))
    stack.model.reply("You said they want it sent to Leeds.")
    stack.say("Where did Northwind want the invoice sent?")
    found = last_tool_result(stack)["found"]
    assert [f["who"] for f in found] == ["you", "they"]  # newest first, and only hers
    assert found[1]["said"] == "For Q-1001, Northwind wants the invoice sent to their Leeds office."
    assert found[1]["when"].startswith(("Mon ", "Tue ", "Wed ", "Thu ", "Fri ", "Sat ", "Sun "))
    stack.model.reply(None, ("search_conversation", {"query": "Q-1001"}))
    stack.model.reply("Found it.")
    stack.say("What did I say about Q-1001?")
    assert len(last_tool_result(stack)["found"]) == 2  # her two messages, this one too


def test_only_a_run_for_one_person_searches_and_only_theirs(stack):
    stack.model.reply("Noted.")
    stack.say("Contoso's refund is my top priority.", person="ben")
    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's question has passed
    stack.scheduler().due()
    with db.transaction(stack.admin) as conn:
        number = conn.execute("select id from obligations where record = 'Q-1001'").fetchone()["id"]
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance",
                                       "trigger": {"kind": "obligation", "obligation": number}})
    with stack.client(opened.json()["token"]) as c:  # a chase acts for Ana alone: hers only
        found = c.post("/run/tools/search_conversation", json={"args": {"query": "Contoso"}})
    assert found.status_code == 200 and found.json()["result"]["found"] == []
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set acts_for = '{}' where id = %s", (opened.json()["run"],))
    with stack.client(opened.json()["token"]) as c:  # a run for nobody reads nobody's
        found = c.post("/run/tools/search_conversation", json={"args": {"query": "Contoso"}})
    assert found.status_code == 403 and "acts for them alone" in found.json()["explanations"][0]
