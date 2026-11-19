"""Who may read what a run read (round 14, core/studio.py): beside the records it handled, a
document's own readers, and what only those it acted for may read, a document read with their
own permissions or a file they sent. The studio shows a run, its answer and its words only to
whom may read all of it: its pages, the pairs graders grade, cases kept from it, and briefs."""

from __future__ import annotations

import base64
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.connectors import libraries
from a5s.core import shadows, studio
from a5s.sample import SampleScenario
from conftest import FAKE_MODELS, PROVIDER_KEY, FakeModel, Stack, build_root, running
from test_libraries import document

LIBS = "  documents: [create_draft]\n  libraries: [search_runbooks, read_runbooks]\n"


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The sample, with finance's runbooks, a docs repository its release trusts, whose
    month-end runbook finance alone may read, and the assistant's next version, to shadow it."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    folder = root / "scenarios" / "sample"
    (folder / libraries.FILE).write_text(yaml.safe_dump({"libraries": {
        "runbooks": {"title": "Finance runbooks", "kind": "repository", "outside": False,
                     "site": "https://forge.example.test/finance/runbooks/blob/main"}}}), encoding="utf-8")
    document(root / "libraries" / "runbooks", "month-end.md", "Month end closes on the third "
             "working day; the bonus pool this year is 4.2% of payroll.", teams=["finance"])
    spec = root / "agents" / "assistant" / "agent.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("  documents: [create_draft]\n", LIBS))
    candidate = root / "agents" / "assistant-next"
    shutil.copytree(root / "agents" / "assistant", candidate)
    nspec = candidate / "agent.yaml"
    nspec.write_text(nspec.read_text(encoding="utf-8").replace("id: assistant\n", "id: assistant-next\n"))
    sample = SampleScenario(folder, database)
    tools = {**sample.tools(), **libraries.tools(libraries.declared(folder), folder, sample,
                                                 root=root / "libraries")}
    definitions.pin(candidate, {n: t.schema_hash for n, t in tools.items()})
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def shadowed(stack: Stack) -> None:
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text(encoding="utf-8"))
    applied = stack.settle(instances={**settings["instances"], "assistant-next-finance": {
        "definition": "assistant-next", "serves": ["ana", "ben"], "parts": ["billing"],
        "level": 1, "owner": "ana", "deputy": "ben", "shadows": "assistant-finance"}},
        data_protection={"shadow_runs": True}, signers=("ana", "noor"))
    assert not applied.refused, applied.refused


def latest_run(stack: Stack, person: str) -> str:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select id::text as id from runs where acts_for = array[%s] and "
                            "trigger->>'kind' = 'message' order by opened_at desc limit 1",
                            (person,)).fetchone()["id"]


def test_a_pair_from_a_document_finance_alone_may_read_goes_to_no_grader_outside_it(stack):
    """A-H1: Dana grades in quality, and may not read the month-end runbook. Ana's question
    read it, so neither answer of its pair is Dana's to grade; Ben's hello, beside it, is."""
    shadowed(stack)
    stack.model.reply(None, ("read_runbooks", {"id": "month-end.md"}))
    stack.model.reply("Month end closes on the third working day, and the bonus pool is 4.2% "
                      "of payroll.")
    stack.model.reply("The third working day; the bonus pool is 4.2%.")  # its shadow, beside it
    assert "bonus pool is 4.2%" in stack.say("When does month end close?", person="ana")
    stack.model.reply("Hello, Ben.")
    stack.model.reply("Hi, Ben.")
    stack.say("Hello", person="ben")
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from shadow_answers").fetchone()["n"] == 2
        pairs = shadows.gradeable(conn, scenario, scenario.person("dana"))
    assert [p["sent"] for p in pairs] == ["Hello, Ben."]


def test_what_someone_sent_is_theirs_alone_to_read_in_the_studio(stack):
    """A file Ben sent is his alone: a5s keeps that for the run that read it, so the studio
    shows the run to him, whom it acted for, and to none of the assistant's owners."""
    stack.model.reply("It says what you'll pay this month.")
    stack.say("What's this?", person="ben", files=[{
        "name": "payslip.txt", "type": "text/plain",
        "data": base64.b64encode(b"November: 3,200.00 after tax").decode()}])
    run = latest_run(stack, "ben")
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert [r["rule"] for r in conn.execute("select rule from run_readers where run_id = %s",
                                                (run,))] == ['{"alone":true}']
        assert studio.seeable(conn, scenario, scenario.person("ana"), [run]) == set()
        assert studio.seeable(conn, scenario, scenario.person("ben"), [run]) == {run}


def test_a_later_run_given_its_words_takes_who_may_read_them(stack):
    """What a run read reaches the runs given its turns: Ana's next question, about nothing in
    particular, is given her month-end answer, so it too is for finance alone."""
    stack.model.reply(None, ("read_runbooks", {"id": "month-end.md"}))
    stack.model.reply("Month end closes on the third working day, and the bonus pool is 4.2%.")
    stack.say("When does month end close?", person="ana")
    stack.model.reply("You're welcome.")
    stack.say("Thanks!", person="ana")
    run = latest_run(stack, "ana")
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert [r["rule"] for r in conn.execute("select rule from run_readers where run_id = %s",
                                                (run,))] == ['{"teams":["finance"]}']
        assert studio.seeable(conn, scenario, scenario.person("dana"), [run]) == set()
