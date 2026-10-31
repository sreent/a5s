"""Round 5, reviewer a: when the settings in force stop checking out during a run, the core
goes on as if no field were classified, and as if the data were internal.

gateway.unseen() returns no fields when settings_in_force() fails, so tools hand classified
fields over as they are, and a model call takes the class of data to be "internal". Tool
calls don't consult the settings in force at all. architecture.md: "If policy, the
settings, the counts or the ledger can't be reached, calls are denied."

Here the settings in force class each customer as confidential, and the model is approved
for synthetic and internal data, not confidential. Mid-run, the version in force stops
checking out, as it does when its approver loses the role, or its signatures are edited.
"""

from a5s import db
from test_classes import approve, resettle
from test_parts import tool


def broken_mid_run(stack) -> str:
    resettle(stack, classified={"customer": "confidential"})
    approve(stack, "internal")
    _, token = stack.open_run(sender="ana")
    with db.transaction(stack.admin) as conn:
        conn.execute("update settings_versions set signatures = '[]' "
                     "where serial = (select max(serial) from settings_versions)")
    with db.transaction(stack.cfg.database_url) as conn:
        assert stack.gateway.settings_in_force(conn)[0] is None
    return token


def test_a_classified_field_stays_hidden_when_the_settings_dont_check_out(stack):
    token = broken_mid_run(stack)
    got = tool(stack, token, "get_record", key="Q-1001")
    assert "Northwind" not in got.text, got.json()  # today: the customer, in clear


def test_a_model_call_is_denied_when_the_settings_dont_check_out(stack):
    token = broken_mid_run(stack)
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "fake", "messages": [{"role": "user", "content": "Hello"}]})
    assert r.status_code == 403, r.json()  # today: allowed, as internal data
