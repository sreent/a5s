"""Round 5, reviewer a: the core checks a call's record, and filters what a tool returns, only
when the record's key is a string. A key of any other type, such as a number, is let through
both times, as if the call were about no record in particular.

Many scenarios number their records. Here one of the sample's records, Q-1003 in orders, is
also known by the number 1003, as a scenario with numbered records would know it. The
assistant works in billing alone, for Ana, who may not see orders' records. The gateway
doesn't check a tool's arguments against its schema either, so the model can send a number
where the schema says a string.
"""

from test_parts import tool


def numbered(stack, monkeypatch) -> None:
    scenario = stack.gateway.scenario
    records = dict(scenario._records)
    records[1003] = {**records["Q-1003"], "key": 1003}
    monkeypatch.setattr(scenario, "_records", records)
    assert scenario.part_of(1003) == "orders" and not scenario.sees("ana", 1003)


def test_a_call_about_a_numbered_record_outside_the_instances_parts_is_denied(stack, monkeypatch):
    numbered(stack, monkeypatch)
    _, token = stack.open_run(sender="ana")
    assert tool(stack, token, "get_record", key="Q-1003").status_code == 403  # as a string
    got = tool(stack, token, "get_record", key=1003)
    assert got.status_code == 403, got.json()  # today: orders' record, Fabrikam's contact and all


def test_what_a_tool_returns_leaves_out_numbered_records_too(stack, monkeypatch):
    numbered(stack, monkeypatch)
    _, token = stack.open_run(sender="ana")
    found = tool(stack, token, "search_records", query="delivery").json()["result"]
    assert found == [], found  # today: Q-1003 is left out, and 1003, the same record, isn't
