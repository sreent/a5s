"""A shadow's model and the data it may read (round 14, C1): a shadow is given the conversation
the instance it shadows had, which holds what that instance's model may read, so the core opens
its run only on a model approved for each of those classes of data, as a shadow's judge."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.core import registry
from a5s.sample import SampleScenario
from conftest import PROVIDER_KEY, FakeModel, Stack, build_root, running, signed

TWO = """
models:
  fake:
    provider: test
    api: openai
    base_url: https://fake.test/v1
    model: fake-1
    reported_model: fake-1
    key_env: A5S_TEST_PROVIDER_KEY
    data_classes: [synthetic, personal]
  fake-next:
    provider: test
    api: openai
    base_url: https://fake.test/v1
    model: fake-2
    reported_model: fake-2
    key_env: A5S_TEST_PROVIDER_KEY
    data_classes: [synthetic]
"""


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The sample, with the assistant on a model approved for personal data, and its next
    version, to shadow it, on one approved for made-up data alone."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", TWO)
    candidate = root / "agents" / "assistant-next"
    shutil.copytree(root / "agents" / "assistant", candidate)
    spec = candidate / "agent.yaml"
    spec.write_text(spec.read_text().replace("id: assistant\n", "id: assistant-next\n")
                    .replace("model: fake\n", "model: fake-next\n"))
    tools = SampleScenario(root / "scenarios" / "sample", database).tools()
    definitions.pin(candidate, {n: t.schema_hash for n, t in tools.items()})
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def test_a_shadow_on_a_model_not_approved_for_what_its_conversation_holds_never_answers(stack):
    """The settings call a customer's name personal; the assistant's model may read it, its
    next version's may not, so the shadow's run is never opened: no call goes to its model,
    with what Ben was told, and the ledger says why."""
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    settings["classified"] = {"customer": "personal"}
    settings["data_protection"] = {"shadow_runs": True}
    settings["instances"]["assistant-next-finance"] = {
        "definition": "assistant-next", "serves": ["ana", "ben"], "parts": ["billing"],
        "level": 1, "owner": "ana", "deputy": "ben", "shadows": "assistant-finance"}
    signed(folder, settings, ("ana", "noor"))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        applied = registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                 scenario.tools(), scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    stack.model.reply(None, ("get_record", {"key": "Q-1002"}))
    stack.model.reply("Q-1002 is the refund for Contoso.")
    assert stack.say("Whose refund is Q-1002?", person="ben") == "Q-1002 is the refund for Contoso."
    assert [r["body"]["model"] for r in stack.model.requests] == ["fake-1", "fake-1"]
    with db.transaction(stack.admin) as conn:
        refused = conn.execute("select entry from ledger where entry::jsonb->>'instance' = "
                               "'assistant-next-finance' and entry::jsonb->>'action' = 'open'"
                               ).fetchone()
    assert refused is not None
    assert "isn't approved for personal data" in json.dumps(json.loads(refused["entry"]))
