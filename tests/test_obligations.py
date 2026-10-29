"""Obligations: worked out by code from the records, chased by an agent, escalated in code.

The sample's open records, with their owners' working hours:
  Q-1001, Ana's, in London: half its time has passed on Sat 31 Oct, and it's due Wed 4 Nov at 17:00.
  Q-1002, Ben's, in London: half on Sun 1 Nov, due Fri 6 Nov at 17:00. Ben reports to Ana.
  Q-1003, Chen's, in Singapore: due Mon 2 Nov at 17:00 there. No agent works for Chen,
  who reports to Omar, also in Singapore.
"""

from dataclasses import replace

from a5s import db
from a5s.services import context


def owed(stack) -> dict[str, dict]:
    with db.transaction(stack.admin) as conn:
        rows = conn.execute("select * from obligations order by record").fetchall()
    return {r["record"]: r for r in rows}


def escalations(stack) -> list[tuple[str, str]]:
    return [(e["args"]["record"], e["args"]["to"]) for e in stack.ledger()
            if e["kind"] == "notice" and e["action"] == "escalate"]


def test_obligations_come_from_the_records_each_naming_the_instance_that_acts(stack):
    stack.at("2026-10-29T10:00:00+00:00")
    assert stack.scheduler().work_due() == 0  # half their time hasn't passed
    found = owed(stack)
    assert {k: (r["person"], r["instance_id"]) for k, r in found.items()} == {
        "Q-1001": ("ana", "assistant-finance"),
        "Q-1002": ("ben", "assistant-finance"),
        "Q-1003": ("chen", None),  # nobody's assistant serves Chen
    }  # and closed Q-1004 owes nothing
    assert not stack.model.requests


def test_its_agent_reminds_the_person_once_half_the_time_has_passed_in_their_hours(stack):
    stack.at("2026-10-31T12:00:00+00:00")  # Saturday: half has passed for Ana, but not at work
    assert stack.scheduler().work_due() == 0

    stack.at("2026-11-02T09:30:00+00:00")  # Monday morning in London
    stack.model.reply("Ana, Q-1001 is due on Wednesday at 17:00. Shall I draft a reply?")
    stack.model.reply("Ben, the duplicate refund, Q-1002, is due on Friday.")
    assert stack.scheduler().work_due() == 2
    assert stack.scheduler().work_due() == 0  # once each

    asked = stack.model.requests[0]["body"]["messages"][-1]["content"]
    assert "from a5s, not the person] Remind Ana Ortiz that Q-1001, Invoice sent to the wrong " \
           "address, is due by 17:00 on Wed 4 Nov and is still open." in asked
    [reminder] = stack.inbox("ana")  # Ana hasn't written to it, so she collects it here
    assert (reminder["from"], reminder["instance"]) == ("assistant", "assistant-finance")
    assert reminder["text"] == "Ana, Q-1001 is due on Wednesday at 17:00. Shall I draft a reply?"
    assert [m["text"] for m in stack.inbox("ben")] == [
        "Ben, the duplicate refund, Q-1002, is due on Friday."]

    opened = [e for e in stack.ledger() if e["action"] == "open"]
    assert [(e["args"]["record"], e["acts_for"], e["decision"]) for e in opened] == [
        ("Q-1001", ["ana"], "allow"), ("Q-1002", ["ben"], "allow")]
    with db.transaction(stack.admin) as conn:  # the next run with Ana knows what it said
        turns = context.recent(conn, person="ana", agent="assistant")
    assert [t["role"] for t in turns] == ["task", "agent"]
    assert stack.verify().ok


def test_the_next_conversation_knows_about_the_reminder(stack):
    stack.at("2026-11-02T09:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    stack.model.reply("Yes: Q-1001, the invoice sent to the wrong address.")
    stack.say("Which one did you remind me about?")
    said = str(stack.model.requests[-1]["body"]["messages"])
    assert "Remind Ana Ortiz that Q-1001" in said and "Ana, Q-1001 is due on Wednesday." in said


def test_an_overdue_obligation_escalates_in_code_in_the_recipients_hours(stack):
    stack.at("2026-11-02T09:00:00+00:00")  # Q-1003 is due: 17:00 in Singapore, after hours
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    assert escalations(stack) == []

    stack.at("2026-11-03T01:00:00+00:00")  # 09:00 on Tuesday in Singapore
    stack.scheduler().work_due()
    assert escalations(stack) == [("Q-1003", "omar")]
    [told] = stack.inbox("omar")
    assert told == {"from": "a5s", "about": None, "instance": None, "at": told["at"], "text": (
        "Q-1003, Delivery date for order 7781, was due on Mon 2 Nov and is still open. "
        "It's Chen Wei's. No agent works on it for them, so nobody reminded them first. You're "
        "next in their reporting line, so a5s is letting you know. "
        "https://sample.a5s.dev/records/Q-1003")}

    stack.at("2026-11-05T02:00:00+00:00")
    stack.scheduler().work_due()
    assert escalations(stack) == [("Q-1003", "omar")]  # Omar is the top of Chen's line
    assert len(stack.model.requests) == 2  # the two reminders: escalating starts no model


def test_escalation_goes_up_the_line_a_working_day_at_a_time(stack, monkeypatch):
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "omar", replace(people["omar"], manager="ana"))
    stack.at("2026-11-03T01:00:00+00:00")
    stack.scheduler().work_due()
    stack.at("2026-11-04T00:59:00+00:00")  # not yet a working day after Omar heard
    stack.scheduler().work_due()
    stack.at("2026-11-04T01:00:00+00:00")  # it is, but it's 01:00 in London, where Ana works
    stack.scheduler().work_due()
    assert escalations(stack) == [("Q-1003", "omar")]

    stack.at("2026-11-04T09:00:00+00:00")
    stack.model.reply("Ana, Q-1001 is due today.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    assert escalations(stack) == [("Q-1003", "omar"), ("Q-1003", "ana")]
    told = [m["text"] for m in stack.inbox("ana") if m["from"] == "a5s"]
    assert told and "Omar Haddad heard on Tue 3 Nov." in told[0]


def test_escalation_waits_a_working_day_after_the_reminder(stack):
    stack.at("2026-11-06T10:00:00+00:00")  # Friday: Ben's Q-1002 is due at 17:00 today
    stack.model.reply("Ana, Q-1001 was due on Wednesday and is still open.")
    stack.model.reply("Ben, Q-1002 is due at 17:00 today.")
    assert stack.scheduler().work_due() == 2
    stack.at("2026-11-06T17:30:00+00:00")  # due, but after hours
    stack.scheduler().work_due()
    stack.at("2026-11-09T09:30:00+00:00")  # Monday, but not yet a working day after the reminder
    stack.scheduler().work_due()
    assert escalations(stack) == []

    stack.at("2026-11-09T10:00:00+00:00")
    stack.scheduler().work_due()
    assert escalations(stack) == [("Q-1002", "ana")]
    [told] = [m["text"] for m in stack.inbox("ana") if m["from"] == "a5s"]
    assert told.startswith("Q-1002, Refund for a duplicate payment, was due on Fri 6 Nov and is "
                           "still open. It's Ben Okafor's. The assistant reminded them on Fri 6 Nov.")
    assert "Q-1001" not in str(escalations(stack))  # Ana is the top of her own line


def test_a_suspended_agent_doesnt_silence_what_is_owed(stack):
    stack.suspend(by="ben")
    stack.at("2026-11-02T09:30:00+00:00")
    assert stack.scheduler().work_due() == 0  # no reminders from a suspended agent
    stack.at("2026-11-09T09:00:00+00:00")
    stack.scheduler().work_due()
    assert ("Q-1002", "ana") in escalations(stack)
    [told] = [m["text"] for m in stack.inbox("ana") if "Q-1002" in m["text"]]
    assert "The assistant couldn't remind them first, because it's suspended." in told
    assert not stack.model.requests


def test_a_closed_record_owes_nothing_and_a_new_due_date_is_owed_afresh(stack, monkeypatch):
    records = stack.gateway.scenario._records
    stack.at("2026-11-02T09:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    assert owed(stack)["Q-1001"]["chased_at"] is not None

    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "closed"})
    stack.scheduler().work_due()
    assert owed(stack)["Q-1001"]["done_at"] is not None

    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "open",
                                            "due": "2026-11-20"})
    stack.scheduler().work_due()
    again = owed(stack)["Q-1001"]
    assert again["done_at"] is None and again["chased_at"] is None  # owed, and chased, afresh


def test_the_core_decides_each_reminder(stack):
    stack.at("2026-10-29T10:00:00+00:00")
    stack.scheduler().due()
    number = owed(stack)["Q-1001"]["id"]

    def remind(instance: str = "assistant-finance"):
        with stack.client() as c:
            return c.post("/runs", json={"instance": instance, "trigger": {
                "kind": "obligation", "obligation": number}})

    assert remind().json()["detail"]["reasons"] == ["half its time hasn't passed yet"]
    stack.at("2026-11-02T09:30:00+00:00")
    opened = remind()
    assert opened.status_code == 200 and "Q-1001" in opened.json()["task"]
    again = remind()
    assert again.status_code == 409 and again.json()["detail"]["answered"]  # once

    with stack.client(opened.json()["token"]) as c:
        to_ben = c.post("/run/messages", json={"to": "ben", "text": "Psst, Ben."})
        to_ana = c.post("/run/messages", json={"to": "ana", "text": "Q-1001 is due Wednesday."})
    assert to_ben.status_code == 403
    assert to_ben.json()["reasons"] == ["writes-to-whom-it-acts-for"]
    assert to_ana.status_code == 200 and stack.inbox("ana") == []  # it waits for her digest
    with stack.client() as c:
        c.post(f"/runs/{opened.json()['run']}/close", json={"outcome": "done"}).raise_for_status()
    stack.scheduler().digest()  # which goes once the run is done
    assert [m["text"] for m in stack.inbox("ana")] == ["Q-1001 is due Wednesday."]


def test_a_withdrawn_instance_leaves_its_obligations_to_escalate(stack):
    stack.settle(instances={})  # the settings leave the assistant out, so it's retired
    stack.at("2026-11-02T09:30:00+00:00")
    stack.scheduler().work_due()
    assert {r["instance_id"] for r in owed(stack).values()} == {None}
    assert not stack.model.requests


def test_escalation_skips_anyone_a5s_may_not_write_to(stack, monkeypatch):
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "omar", replace(people["omar"], in_audience=False))
    stack.at("2026-11-03T01:00:00+00:00")  # Q-1003 is overdue, and it's working hours in Singapore
    stack.scheduler().work_due()
    assert escalations(stack) == [] and stack.inbox("omar") == []


def test_records_that_cant_be_read_leave_obligations_as_they_were(stack, monkeypatch):
    stack.at("2026-10-29T10:00:00+00:00")
    stack.scheduler().work_due()

    def down():
        raise ConnectionError("the records system isn't answering")

    monkeypatch.setattr(stack.gateway.scenario, "obligations", down)
    with stack.client() as c:
        swept = c.post("/obligations/sweep")
    assert swept.status_code == 503 and "ConnectionError" in swept.json()["detail"]
    assert stack.scheduler().work_due() == 0
    assert all(r["done_at"] is None for r in owed(stack).values())  # nothing owed went unseen
