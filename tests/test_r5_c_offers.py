"""Round 5, reviewer c: offers that count once the person says yes.

- reminders.offer treats any reminder for the same person, day and record as the same one,
  whatever it's about, and answers with the old reminder's number, the new reminder's words
  and "it's set". Two reminders for the same day about no record are the common case.
- confirm_reminder and confirm_note take no argument: they keep the offer made last. With
  two offers waiting, the person can't say yes to the one they want.
- note_waiting said "Reminders to them about it pause until then", and the assistant was told
  to say it won't remind them, but the person's own reminders about the record still came: now
  it says so, and names them, so the person can cancel them.
"""

from a5s import db


def kept(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from reminders order by id").fetchall()


def tool_results(stack, request: int = -1) -> list[str]:
    return [m["content"] for m in stack.model.requests[request]["body"]["messages"]
            if m["role"] == "tool"]


def offer(stack, about: str, on: str = "2026-11-06", **more) -> None:
    stack.model.reply(None, ("offer_reminder", {"about": about, "on": on, **more}))
    stack.model.reply("Shall I? Say yes, and I'll set it.")
    stack.say(f"Remind me on Friday to {about}.")


def test_two_reminders_for_the_same_day_are_two_reminders(stack):
    offer(stack, "call Northwind")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done.")
    stack.say("Yes")
    offer(stack, "send Contoso their refund")
    said = tool_results(stack)[-1]
    assert [r["about"] for r in kept(stack)] == ["call Northwind", "send Contoso their refund"], (
        "a5s kept no second reminder, and told the agent it's set already, under the first "
        f"one's number, in the second one's words: {said}")


def test_the_person_says_yes_to_the_offer_they_mean(stack):
    offer(stack, "call Northwind", on="2026-11-06")
    offer(stack, "send Contoso their refund", on="2026-11-09")
    first = f"R-{kept(stack)[0]['id']}"
    stack.model.reply(None, ("confirm_reminder", {"reminder": first}))
    stack.model.reply("Done: I'll remind you on Friday to call Northwind.")
    stack.say("Yes to the Friday one, about Northwind. Not the other.")
    confirmed = [(r["about"], r["confirmed_at"] is not None) for r in kept(stack)]
    assert confirmed == [("call Northwind", True), ("send Contoso their refund", False)], (
        f"confirm_reminder takes no argument and keeps the last offer: {confirmed}; "
        f"it told the agent {tool_results(stack)[-1]}")


def test_waiting_on_something_says_which_of_their_own_reminders_still_come(stack):
    stack.model.reply(None, ("offer_reminder", {"about": "chase Northwind", "on": "2026-11-03",
                                                "record": "Q-1001"}))
    stack.model.reply("Shall I?")
    stack.say("Remind me on Tuesday to chase Northwind about Q-1001")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Set.")
    stack.say("Yes")
    stack.scheduler().due()  # the core works out what the records owe
    stack.model.reply(None, ("note_waiting", {"record": "Q-1001", "waiting_on": "Northwind's new "
                                              "address", "until": "2026-11-10"}))
    stack.model.reply("Noted: a5s won't chase you about Q-1001 until Tue 10 Nov. Your reminder "
                      "on Tuesday still comes: shall I cancel it?")
    stack.say("I'm waiting on Northwind's new address for Q-1001 until the 10th.")
    said = tool_results(stack)[-1]
    number = kept(stack)[0]["id"]
    assert "a5s won't chase them about it until" in said and f"R-{number} on Tue 3 Nov" in said, (
        f"the tool must say their own reminder about it still comes: {said}")
    from a5s.core.reminders import TOOLS
    assert "Reminders to them about it pause" not in TOOLS["note_waiting"].description
