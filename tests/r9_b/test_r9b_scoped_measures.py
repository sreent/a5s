"""Round 9, reviewer B: the measures scoped to an agent or an instance (core/measures.py, for
the studio's dashboards), against the deployment's. With two instances of the assistant, as
the studio's own tests make (test_studio_pages.with_ops), each instance's figures should be
its own, and together they should come to the agent's and the deployment's."""

from __future__ import annotations

import uuid
from datetime import timedelta

import yaml
from psycopg.types.json import Jsonb

from a5s import db

OPS = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
       "owner": "omar"}


def with_ops(stack) -> dict:
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    assert not stack.settle(instances={**settings["instances"], "assistant-ops": OPS},
                            signers=("ana", "omar")).refused
    return settings


def measures(stack, path: str) -> dict:
    with stack.client() as c:
        found = c.get(path)
    assert found.status_code == 200, found.text
    return found.json()


def test_a_group_chat_one_instance_heard_isnt_in_another_instances_figures(stack):
    """Inbound messages have an agent but no instance, so the scoped 'groups' figure is the
    agent's: assistant-ops, which serves only Chen, shows the billing team's group chat that
    assistant-finance answered, and the two instances' figures count it twice."""
    with_ops(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into inbound (id, channel, source_id, person, agent, text, reply_to, "
            "received_at, conversation, members, answered_at) values "
            "(%s, 'matrix', %s, 'ana', 'assistant', '@assistant what is open in billing?', "
            "%s, %s, 'group:billing-room', '{ana,ben}', %s)",
            (str(uuid.uuid4()), str(uuid.uuid4()), Jsonb({"room": "!billing"}),
             stack.gateway.clock() - timedelta(hours=1), stack.gateway.clock()))
    ops = measures(stack, "/studio/instances/assistant-ops/measures")["groups"]
    finance = measures(stack, "/studio/instances/assistant-finance/measures")["groups"]
    whole = measures(stack, "/measures")["groups"]
    total = sum(g["messages"] for g in ops + finance)
    assert ops == [] and total == sum(g["messages"] for g in whole), (
        f"assistant-ops shows {ops}; the instances together count {total} of the "
        f"deployment's {sum(g['messages'] for g in whole)}")


def test_an_agents_figures_keep_the_runs_of_an_instance_retired_within_the_window(stack):
    """studio.instances() leaves retired instances out, so once assistant-ops is retired its
    runs drop out of the assistant's 30-day figures, though /measures still counts them, and
    its own page and runs can't be found at all."""
    settings = with_ops(stack)
    stack.model.reply("Q-1003 is waiting on the warehouse.")
    stack.say("Where's Q-1003?", person="chen")  # assistant-ops answers Chen
    assert not stack.settle(instances=settings["instances"], signers=("ana", "omar")).refused  # retired
    whole = measures(stack, "/measures")["runs"]
    agent = measures(stack, "/studio/agents/assistant/measures")["runs"]
    assert [r["instance"] for r in whole] == ["assistant-ops"]
    with stack.client() as c:
        own = c.get("/studio/instances/assistant-ops/runs").status_code
    assert agent == whole, f"the assistant's figures show {agent}; its runs page answers {own}"


def test_an_agents_figures_and_a5s_measures_agree_on_whom_it_serves_while_its_suspended(stack):
    """docs/studio.md: a dashboard 'shows the same figures as `a5s measures`'. /measures
    counts whom an agent serves from its active instances; the studio from every instance
    but the retired, so while an instance is suspended the two disagree on 'served', 'came
    back of those it serves' and their shares."""
    for person in ("ana", "ben"):
        with db.transaction(stack.admin) as conn:  # each wrote to the assistant last month
            conn.execute(
                "insert into inbound (id, channel, source_id, person, agent, text, reply_to, "
                "received_at, answered_at) values (%s, 'local', %s, %s, 'assistant', 'hello', "
                "%s, %s, %s)", (str(uuid.uuid4()), str(uuid.uuid4()), person,
                                Jsonb({"channel": "local"}),
                                stack.gateway.clock() - timedelta(days=40),
                                stack.gateway.clock() - timedelta(days=40)))
    stack.suspend(by="ben")
    whole = measures(stack, "/measures")["returning"]
    agent = measures(stack, "/studio/agents/assistant/measures")["returning"]
    assert agent == whole, f"a5s measures: {whole}; the assistant's dashboard: {agent}"


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
