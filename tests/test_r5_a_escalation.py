"""Round 5, reviewer a: an escalation names a record, its title and what its owner said they
were waiting on, to whoever is next up the owner's reporting line, without asking the
directory whether they may see it.

The sample's directory lets each record's owner's reporting line see it, so its own data
can't show this. Here, as in a scenario that keeps records to their part's team, Chen
reports to Lena, in technology, who may not see orders' records.
"""

from dataclasses import replace


def test_an_escalation_tells_nobody_of_a_record_they_may_not_see(stack, monkeypatch):
    scenario = stack.gateway.scenario
    people = scenario._people
    monkeypatch.setitem(people, "chen", replace(people["chen"], manager="lena"))
    sees = scenario.sees
    monkeypatch.setattr(scenario, "sees", lambda person, record: person != "lena" and sees(person, record))
    assert not scenario.sees("lena", "Q-1003")

    stack.at("2026-11-03T09:00:00+00:00")  # Q-1003 is overdue; 09:00 in London, Lena's hours
    stack.model.reply("Ana, Q-1001 is due tomorrow.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    told = " ".join(m["text"] for m in stack.inbox("lena"))
    assert "Q-1003" not in told and "order 7781" not in told, told
