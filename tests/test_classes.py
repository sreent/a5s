"""Classes of data: the scenario's signed settings say what class its data is, and which
fields are of a class of their own. A model sees no data of a class it isn't approved for:
the core refuses to call it, or hands it those fields as handles, and leaves them out of
what it tells it from the records."""

from dataclasses import replace

import yaml

from a5s import db
from a5s.core import registry
from conftest import signed

NORTHWIND = "Northwind"


def resettle(stack, **changes) -> None:
    """A new version of the settings, signed by Ana, an instance approver, and applied."""
    folder = stack.cfg.scenario_dir
    signed(folder, {**yaml.safe_load((folder / "settings.yaml").read_text()), **changes})
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused


def approve(stack, *classes: str) -> None:
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"],
                                           data_classes=("synthetic", *classes))


def test_a_model_never_sees_data_of_a_class_it_isnt_approved_for(stack):
    resettle(stack, data_class="internal")  # real data, and the model is for made-up data only
    told = stack.say("Hello")
    assert told.startswith("I couldn't finish that.") and stack.model.requests == []
    refused = [e for e in stack.ledger() if e["kind"] == "model" and e["decision"] == "deny"]
    assert refused[0]["reasons"] == ["models-see-only-data-they-are-approved-for"]
    approve(stack, "internal")
    stack.model.reply("Hello, Ana.")
    assert stack.say("Hello again") == "Hello, Ana."


def test_a_classified_field_reaches_only_a_model_approved_for_its_class(stack):
    resettle(stack, classified={"customer": "confidential"})
    stack.scheduler().due()
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("Tell me about Q-1001")
    sent = str(stack.model.requests)
    assert NORTHWIND not in sent  # not in the tool's result, nor in the case's brief
    assert "[h:" in stack.model.requests[-1]["body"]["messages"][-1]["content"]

    approve(stack, "confidential")
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is Northwind's.")
    stack.say("Whose is Q-1001?")
    assert NORTHWIND in stack.model.requests[-1]["body"]["messages"][-1]["content"]


def test_a_report_leaves_out_what_its_model_may_not_see(stack):
    stack.with_watcher(serves=("ana",))
    resettle(stack, classified={"customer": "confidential"})
    stack.at("2026-10-29T09:30:00+00:00")  # the watcher's first morning
    stack.model.reply("Ana, you have Q-1001, open.")
    stack.scheduler().work_due()
    assert NORTHWIND not in str(stack.model.requests)
