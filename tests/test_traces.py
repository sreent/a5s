"""Traces: the core's calls go out as OpenTelemetry spans in the GenAI conventions, masked by
what they leave out: nothing anyone said, no tool's arguments or results, and no person."""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from a5s.core import traces


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    traces.setup("a5s-test", exporter, at_once=True)
    yield exporter
    traces._provider = None


def test_the_cores_calls_go_out_as_spans_without_what_was_said(stack, spans):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is about an invoice sent to the wrong address.")
    stack.say("What's the invoice question about? My secret word is Bluebird.")
    found = spans.get_finished_spans()
    assert [s.name for s in found] == ["open_run", "chat fake", "execute_tool get_record",
                                       "chat fake", "send_message"]
    chat = found[1]
    assert dict(chat.attributes) == {
        "gen_ai.operation.name": "chat", "gen_ai.provider.name": "test",
        "gen_ai.request.model": "fake", "gen_ai.response.model": "fake-1",
        "gen_ai.usage.input_tokens": 10, "gen_ai.usage.output_tokens": 5,
        "a5s.run.id": chat.attributes["a5s.run.id"], "a5s.instance": "assistant-finance"}
    assert chat.instrumentation_scope.schema_url == traces.SCHEMA
    told = str([(s.name, dict(s.attributes)) for s in found])
    for said in ("Bluebird", "Q-1001", "wrong address", "'ana'", "Ana Ortiz"):
        assert said not in told


def test_without_an_endpoint_spans_go_nowhere(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert traces.setup("a5s-test") is False
    with traces.span("nothing", **{"a5s.instance": "x"}) as current:
        assert not current.is_recording()
