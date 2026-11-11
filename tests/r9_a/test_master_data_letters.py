"""Round 9, reviewer A: master data says "Bank details reach an agent only as handles" and
"neither ever sees a bank account's number" (scenarios/master-data.md). Its assistant may ask
a5s's reader about a supplier's letter (context.documents), and the reader answers in free
text, with the letter's new IBAN in clear."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from scenario_stack import running_scenario

SCENARIO = "a5s.master_data:MasterDataScenario"
NEW_IBAN = "GB82 WEST 1234 5698 7654 32"  # the published example IBAN


@pytest.fixture
def mdg(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "master-data",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_a_suppliers_letter_puts_a_bank_account_in_front_of_the_agent(mdg):
    mdg.gateway.scenario._letters[:] = [{  # what a fraudster's letter says
        "record": "CR0000102", "from": "accounts@contoso-supplies.test", "at": "2026-11-03",
        "body": f"Please move our payments to our new bank account, {NEW_IBAN}, from 5 "
                "November. It is urgent."}]
    mdg.model.reply(None, ("get_letters", {"key": "CR0000102"}))
    mdg.model.reply(json.dumps({"asks_for": "a bank change", "date": "5 November",
                                "request": "CR0000102"}))  # a5s's reader fills its form
    mdg.model.reply(None, ("ask_about", {"document": "D-1",
                                         "question": "Which account do they want paid?"}))
    mdg.model.reply(f"They want payments to go to {NEW_IBAN} from 5 November.")  # the reader
    mdg.model.reply(f"Contoso asks for its payments to go to {NEW_IBAN}.")
    said = mdg.say("What does Contoso's letter on CR0000102 ask for?", person="ada",
                   agent="mdg-assistant")
    given = json.dumps([m["content"] for m in mdg.model.requests[-1]["body"]["messages"]
                        if m["role"] == "tool"])
    # FAILS NOW: the agent was given the account's number, not a handle, and repeats it
    assert "GB82" not in given and "GB82" not in said, said


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
