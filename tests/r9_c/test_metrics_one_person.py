"""Round 9, reviewer C: operators' figures, "never by a person" (core/metrics.py), for an
instance that serves one person, which the settings allow and a5s's own studio tests set up
(assistant-ops, serving Chen alone). Counted by instance, its figures are that person's: how
much they used an agent each day, and when they ran out of budget, sent each minute to the
organisation's monitoring, kept there for as long as it keeps anything."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from a5s import build
from a5s.core import metrics, registry
from test_metrics import collected
from test_studio_pages import with_ops


@pytest.fixture
def figures(stack):
    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", lambda: build.read_status(stack.gateway), reader)
    yield reader
    metrics.shutdown()


def test_no_figure_is_one_persons_use(stack, figures):
    with_ops(stack)
    stack.model.reply("Nothing's open for you.")
    stack.say("What's open?", person="chen")
    served = {i.id: registry.served(stack.gateway.scenario, i.serves)
              for i in stack.gateway.scenario.settings().instances}
    print(served)
    alone = {i for i, people in served.items() if len(people) == 1}
    assert alone == {"assistant-ops"}  # Chen's alone
    found = collected(figures)
    theirs = [(name, value) for name, points in found.items() for value, attributes in points
              if attributes.get("a5s.instance") in alone]
    # FAILS: a5s.tokens and a5s.budget.warnings by instance are Chen's own use of the agent,
    # day by day, in the organisation's monitoring.
    assert theirs == [], theirs


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
