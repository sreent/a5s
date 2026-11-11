"""Round 9 of the critique: the operators' figures (core/metrics.py) and the studio's figures
(core/studio.py) count never by a person or a record, nor with anything anyone said: a run's
outcome comes from a fixed set, a denial's reasons show as the policies' ids, and an
instance's figures count only its own group chats (docs/critique.md, round 9)."""

import json

import httpx
import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from a5s import build, db
from a5s.core import metrics
from a5s.services import context
from conftest import SERVICE_TOKEN


@pytest.fixture
def figures(stack):
    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", lambda: build.read_status(stack.gateway), reader)
    yield reader
    metrics.shutdown()


def collected(reader: InMemoryMetricReader) -> dict[str, list[tuple[float, dict]]]:
    found: dict[str, list[tuple[float, dict]]] = {}
    for resource in reader.get_metrics_data().resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                found[metric.name] = [(p.value, dict(p.attributes)) for p in metric.data.data_points]
    return found


def a_long_conversation(stack) -> None:
    """Ana told the assistant what she earns, in her words, long ago (as tests/test_summaries.py
    sets up a conversation that no longer fits a run)."""
    with db.transaction(stack.admin) as conn:
        context.add_turn(conn, person="ana", agent="assistant", role="person",
                         content="My bonus this year is 18,500 after tax, and my rent is 2,100.")
        context.add_turn(conn, person="ana", agent="assistant", role="agent", content="Noted.")
        for n in range(5):
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content=f"Note {n}: " + "the weekly sync went through invoices. " * 25)
    stack.gateway.definitions["assistant"].context.budget_tokens = 1000


def test_what_someone_said_reaches_the_monitoring_through_a_summary_runs_outcome(
        stack, figures, approving, provider):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(json.dumps({"decisions": ["Ana's bonus is £18,500 and her rent £2,100."],
                                  "commitments": [], "open_questions": []}))
    stack.say("Hello")  # her turns no longer fit: a5s's summary run folds them
    outcomes = {a["a5s.outcome"] for _, a in collected(figures)["a5s.runs"]}
    leaked = [o for o in outcomes if "18,500" in o]
    # The studio shows it too, to whoever may watch the instance
    headers = {"Authorization": f"Bearer {provider.id_token(person='ben')}"}
    ended = httpx.get(f"{approving}/studio/api/instances/assistant-finance", headers=headers,
                      timeout=30).json()["ended"]
    shown = [e["outcome"] for e in ended if "18,500" in e["outcome"]]
    assert not leaked and not shown, (leaked, shown)  # outcomes come from a fixed set


def test_the_studios_figures_name_people_in_the_reasons_for_denials(stack, approving, provider):
    """A run the core won't open is denied in the ledger with reasons that name people, such as
    whose budget is spent; the studio's figures show them to anyone who may watch it."""
    with db.transaction(stack.admin) as conn:  # Ana has used her day's budget with the assistant
        conn.execute("insert into spend (instance_id, person, day, tokens) "
                     "values ('assistant-finance', 'ana', %s, 10000000) "
                     "on conflict (instance_id, person, day) do update set tokens = 10000000",
                     (stack.gateway.clock().date(),))
    with httpx.Client(base_url=stack.url, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
                      timeout=60) as core:
        opened = core.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("What's open?", "ana")}})
    assert opened.status_code == 409
    headers = {"Authorization": f"Bearer {provider.id_token(person='ben')}"}
    denied = httpx.get(f"{approving}/studio/api/instances/assistant-finance", headers=headers,
                       timeout=30).json()["denied"]
    named = [r for d in denied for r in d["reasons"] if "ana" in r.split()]
    assert not named, denied  # reasons show as the policies' ids, any other words as "other"


def test_an_instances_figures_count_group_chats_of_the_agents_other_instances(
        stack, approving, provider):
    """The studio's figures are "of those instances alone" (core/measures.py), but group chats
    that mention the agent are counted by agent: Omar, who may watch only assistant-ops, sees how
    often and by how many people finance's group chats called on the assistant."""
    import uuid

    import yaml
    ops = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
           "owner": "omar"}
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    assert not stack.settle(instances={**settings["instances"], "assistant-ops": ops},
                            signers=("ana", "omar")).refused
    with db.transaction(stack.admin) as conn:  # finance's own group chat, with assistant-finance
        for who in ("ana", "ben", "ana"):
            conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                         "reply_to, conversation, members) values (%s, 'matrix', %s, %s, "
                         "'assistant', 'about the refunds', '{}', 'matrix:!fin:a5s.test', "
                         "'{ana,ben}')", (str(uuid.uuid4()), str(uuid.uuid4()), who))
    headers = {"Authorization": f"Bearer {provider.id_token(person='omar')}"}
    groups = httpx.get(f"{approving}/studio/api/instances/assistant-ops", headers=headers,
                       timeout=30).json()["groups"]
    assert groups == [], groups  # finance's chats are counted for those who watch finance

