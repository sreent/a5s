"""Parts: each instance works in the parts of the business its settings name, with a level in
each, approved by each part's owner. It works only on records in its parts, and only on those
everyone its run acts for may see. In the sample, Ana owns billing and Omar owns orders."""

import yaml

from a5s import db
from a5s.core import approvals, registry
from conftest import SAMPLE_SETTINGS, signed

OMAR_TOO = ["ana", "ben", "omar"]


def tool(stack, token: str, name: str, **args):
    with stack.client(token) as c:
        return c.post(f"/run/tools/{name}", json={"args": args})


def reasons(response) -> list[str]:
    return response.json()["reasons"]


def test_an_instance_works_only_on_records_in_its_parts(stack):
    assert not stack.settle(serves=OMAR_TOO).refused  # billing alone: Ana's to approve
    _, token = stack.open_run(sender="omar")
    out_of_scope = tool(stack, token, "get_record", key="Q-1003")  # orders: Omar may see it
    assert out_of_scope.status_code == 403
    assert reasons(out_of_scope) == ["instances-work-only-in-their-parts"]
    assert out_of_scope.json()["explanations"] == [
        "the record is in a part the instance doesn't work in"]


def test_a_run_works_only_on_records_everyone_it_acts_for_may_see(stack):
    assert not stack.settle(serves=OMAR_TOO).refused
    _, token = stack.open_run(sender="omar")
    unseen = tool(stack, token, "get_record", key="Q-1001")  # billing's team is finance
    assert unseen.status_code == 403 and reasons(unseen) == ["people-see-only-what-they-may"]
    _, token = stack.open_run(sender="ben")
    seen = tool(stack, token, "get_record", key="Q-1001")  # Ana's, and Ben is in finance
    assert seen.status_code == 200 and seen.json()["result"]["key"] == "Q-1001"


def test_what_a_tool_returns_leaves_out_records_the_run_may_not_work_on(stack):
    run, token = stack.open_run(sender="ana")
    found = tool(stack, token, "search_records", query="invoice refund delivery")
    assert [r["key"] for r in found.json()["result"]] == ["Q-1001", "Q-1002"]  # not Q-1003
    [called] = [e for e in stack.ledger(run) if e["action"] == "search_records"
                and e["decision"] == "record"]
    assert called["outcome"]["withheld"] == 1


def test_a_call_works_at_the_level_of_its_records_part(stack):
    assert not stack.settle(serves=OMAR_TOO, parts={"billing": 1, "orders": 0},
                            signers=("ana", "omar")).refused
    _, token = stack.open_run(sender="omar")
    in_orders = tool(stack, token, "create_draft", title="Delivery", body="When?", record="Q-1003")
    assert in_orders.status_code == 403 and reasons(in_orders) == ["level-0-only-observes"]
    about_nothing = tool(stack, token, "create_draft", title="Note", body="Hello")
    assert about_nothing.status_code == 403  # at its own level, the lowest of its parts'
    _, token = stack.open_run(sender="ana")
    in_billing = tool(stack, token, "create_draft", title="Invoice", body="Resent.", record="Q-1001")
    assert in_billing.status_code == 200
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select level, parts from instances where id = 'assistant-finance'"
                            ).fetchone() == {"level": 0, "parts": {"billing": 1, "orders": 0}}


def test_each_part_an_instance_works_in_needs_its_owners_approval(stack):
    wider = {"serves": OMAR_TOO, "parts": ["billing", "orders"]}
    refused = stack.settle(**wider).refused  # Ana alone
    assert refused == ["the owner of orders hasn't approved it"]
    assert stack.settle(signers=("omar",), **wider).refused == [
        "the owner of billing hasn't approved it"]
    assert not stack.settle(signers=("ana", "omar"), **wider).refused


def test_an_instance_in_no_part_needs_an_instance_approver(stack):
    assert not stack.settle(parts=[], signers=("ana", "omar")).refused
    assert stack.settle(parts=[], level=0, signers=("omar",)).refused == [
        "no instance-approver has approved it, for the instances in no part"]


def test_retiring_an_instance_needs_its_parts_owners_too(stack):
    assert not stack.settle(serves=OMAR_TOO, parts=["billing", "orders"],
                            signers=("ana", "omar")).refused
    refused = stack.settle(instances={}, signers=("omar",)).refused
    assert refused == ["the owner of billing hasn't approved it"]


def test_nobody_widens_an_instances_parts_by_editing_its_record(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set parts = '{\"billing\": 1, \"orders\": 1}' "
                     "where id = 'assistant-finance'")
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})
    assert opened.status_code == 409
    assert "doesn't match its signed settings" in opened.json()["detail"]["reasons"][0]


def test_a_reminder_is_only_about_a_record_its_person_may_see(stack):
    stack.model.reply(None, ("offer_reminder", {"about": "chase the delivery", "on": "2026-11-20",
                                                "record": "Q-1003"}))
    stack.model.reply("I can't set that one.")
    stack.say("Remind me about Q-1003")
    told = [m["content"] for m in stack.model.requests[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "there's no record Q-1003 that they may see" in told[0]


def test_approvers_see_the_parts_a_version_changes_in_words(stack):
    before = stack.gateway.scenario.settings()
    stack.settle(serves=OMAR_TOO, parts={"billing": 1, "orders": 0}, signers=("ana", "omar"))
    after = stack.gateway.scenario.settings()
    found = approvals.changes(before, after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert found == [
        {"text": "assistant-finance serves Omar Haddad as well.", "widens": True},
        {"text": "assistant-finance works in orders as well, at level 0.", "widens": True}]
    back = approvals.changes(after, before, stack.gateway.definitions, stack.gateway.scenario.person)
    assert {"text": "assistant-finance no longer works in orders.", "widens": False} in back


def test_a_case_brief_is_only_of_a_record_its_people_may_see(stack):
    stack.model.reply("I can't see that one.")
    stack.say("What's happening with Q-1003?")  # Chen's, in orders
    told = stack.model.requests[-1]["body"]["messages"][0]["content"]
    assert "## The case: Q-1003, from the records" in told
    assert "a5s has nothing on Q-1003 for this run" in told and "7781" not in told


def test_the_watcher_reports_only_on_records_in_its_parts(stack):
    stack.with_watcher(serves=("ana", "ben", "chen"))  # in billing alone
    stack.at("2026-10-29T09:30:00+00:00")  # 09:30 in London: Ana's and Ben's first mornings
    stack.model.reply("Ana, you have Q-1001 open.")
    stack.model.reply("Ben, you have Q-1002 open.")
    stack.scheduler().work_due()
    stack.at("2026-10-30T02:00:00+00:00")  # 10:00 in Singapore, Chen's first morning
    asked = len(stack.model.requests)
    assert stack.scheduler().work_due() == 0  # nothing in its parts is Chen's, so no model starts
    assert len(stack.model.requests) == asked
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select outcome from report_fires where person = 'chen'"
                            ).fetchone()["outcome"] == "nothing new"


def test_only_an_instance_that_works_in_a_records_part_chases_it(stack):
    def acting() -> dict:
        stack.scheduler().due()  # the core works out what the records owe
        with db.transaction(stack.admin) as conn:
            return {r["record"]: r["instance_id"] for r in conn.execute(
                "select record, instance_id from obligations order by record")}

    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    assert acting() == {"Q-1001": "assistant-finance", "Q-1002": "assistant-finance",
                        "Q-1003": None}  # in orders, so code escalates it when it's due
    assert not stack.settle(serves=["ana", "ben", "chen"], parts=["billing", "orders"],
                            signers=("ana", "omar")).refused
    assert acting()["Q-1003"] == "assistant-finance"


def test_only_an_instance_approver_sets_the_classes_of_data(stack):
    folder, scenario = stack.cfg.scenario_dir, stack.gateway.scenario
    orders = {**SAMPLE_SETTINGS["instances"]["assistant-finance"], "parts": ["orders"],
              "serves": ["chen", "omar"]}
    assert not stack.settle(instances={"assistant-finance": orders}, signers=("ana", "omar")).refused

    in_force = yaml.safe_load((folder / "settings.yaml").read_text())

    def as_omar(**changes) -> list[str]:  # he owns orders, and holds no other role
        signed(folder, {**in_force, **changes}, ("omar",))
        with db.transaction(stack.admin) as conn:
            return registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused

    assert as_omar(data_class="internal") == [
        "no instance-approver has approved its classes of data"]
    assert as_omar(classified={"contact": "synthetic"}) != []
    assert as_omar() == []  # the same classes: his part is his to approve alone
