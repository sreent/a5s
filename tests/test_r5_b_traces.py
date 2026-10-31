"""Round 5, reviewer b: traces say how long each call took.

The runbooks send the team to the traces to find what's slow, and the design says spans
carry "how long it took". But the gateway opens the spans for a scenario's tools, for
outgoing messages and for opening runs only after the work is done, around nothing
(`with traces.span(...): pass`), so each says its call took no time at all.
"""

import time

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from a5s.core import traces


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    traces.setup("a5s-test", exporter, at_once=True)
    yield exporter
    traces._provider = None


def test_a_slow_tool_shows_as_slow_in_its_span(stack, spans, monkeypatch):
    scenario = stack.gateway.scenario
    real = scenario._get_record

    def slow(call):  # the scenario's records system takes a second and a half to answer
        time.sleep(1.5)
        return real(call)

    monkeypatch.setattr(scenario, "_get_record", slow)
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is about an invoice sent to the wrong address.")
    stack.say("What's the invoice question about?")
    [tool] = [s for s in spans.get_finished_spans() if s.name == "execute_tool get_record"]
    took = (tool.end_time - tool.start_time) / 1e9
    assert took >= 1.5, f"the span says get_record took {took * 1000:.2f} ms; it took 1,500 ms"
