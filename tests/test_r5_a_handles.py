"""Round 5, reviewer a: the gateway puts a handle's value into a tool's arguments after policy
has checked them, and nothing stops the value coming back to the model in what the tool
returns, such as an error that repeats the argument.

The sample's get_record answers a key it doesn't know with "no record <key>". A run that acts
for someone can't name a record that doesn't exist, since nobody may see it. A run that acts
for nobody, such as a schedule's, can. The reference agents have no schedules, so this needs
a release that has one, as test_schedules.py makes.
"""

from test_parts import tool
from test_schedules import with_schedule

CONTACT = "accounts@northwind.test"  # Q-1001's customer's contact, a handle for the model


def test_a_handles_value_never_comes_back_to_the_model(stack):
    with_schedule(stack)
    stack.at("2026-10-29T09:00:30+00:00")
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "schedule", "schedule": "morning"}})
    token = opened.json()["token"]
    record = tool(stack, token, "get_record", key="Q-1001").json()["result"]
    assert record["contact"].startswith("[h:") and CONTACT not in str(record)
    echoed = tool(stack, token, "get_record", key=record["contact"])
    assert CONTACT not in echoed.text, echoed.json()  # today: {"error": "no record accounts@..."}
