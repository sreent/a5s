"""Round 9, reviewer C: bank details as handles, in master data governance.

The scenario says bank details reach an agent only as handles, and docs/data-protection.md
says the values a run was handed as handles go an hour after the run ends. But where the agent
writes a handle in what it says, as its instructions tell it to ("Write the handle where the
value goes"), a5s fills the value in, and keeps the message as filled in: in the outbox, which
retention keeps with the conversation, 12 months. The live run of tests/test_master_data.py
did just this: it told Tess the request "touches the IBAN, which arrives only as a handle
GB29NWBK60161331926819"."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from a5s import db
from a5s.core import retention
from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from scenario_stack import opened, running_scenario

SCENARIO = "a5s.master_data:MasterDataScenario"
IBAN = "GB29NWBK60161331926819"  # what CR0000102 proposes: another supplier's account


@pytest.fixture
def mdg(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "master-data",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_a_bank_account_written_as_a_handle_is_kept_no_longer_than_an_hour(mdg):
    token = opened(mdg, "mdg-desk", "tess", "mdg-assistant")
    with mdg.client(token) as client:
        got = client.post("/run/tools/get_record", json={"args": {"key": "CR0000102"}}).json()
        handle = got["result"]["values"]["iban"]
        assert handle.startswith("[h:") and IBAN not in str(got)  # the agent never sees it
        sent = client.post("/run/messages", json={
            "to": "tess", "text": f"CR0000102 moves Contoso's payments to {handle}."})
        assert sent.status_code == 200, sent.text
    with db.transaction(mdg.admin) as conn:
        conn.execute("update runs set closed_at = now() - interval '2 hours', "
                     "opened_at = opened_at - interval '3 hours', outcome = 'done'")
        retention.sweep(conn, mdg.gateway.clock() + timedelta(hours=3), "master-data")
        handles = conn.execute("select count(*) as n from run_handles").fetchone()["n"]
        kept = [r["text"] for r in conn.execute("select text from outbox where person = 'tess'")]
        said = [r["content"] for r in conn.execute("select content from turns where person = 'tess'")]
    assert handles == 0  # the run's handles went, as the data protection page says
    assert not any(IBAN in t for t in said)  # the conversation keeps the handle, as written
    # FAILS: the message a5s sent Tess keeps the bank account itself, in the outbox, kept as
    # long as the conversation, 12 months, not the hour the page gives handled values.
    assert not any(IBAN in t for t in kept), kept


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
