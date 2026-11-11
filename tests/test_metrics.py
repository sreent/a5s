"""Operators' figures: the status's, as OpenTelemetry metrics for the organisation's own
monitoring, each counted by what it counts and never by whom (core/metrics.py)."""

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from a5s import build
from a5s.core import metrics

# What a figure may be counted by: never a person, a record, or anything said
COUNTED_BY = {"a5s.trigger", "a5s.outcome", "a5s.kind", "a5s.action", "a5s.instance",
              "a5s.status", "gen_ai.request.model"}


def collected(reader: InMemoryMetricReader) -> dict[str, list[tuple[float, dict]]]:
    found: dict[str, list[tuple[float, dict]]] = {}
    for resource in reader.get_metrics_data().resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                found[metric.name] = [(p.value, dict(p.attributes)) for p in metric.data.data_points]
    return found


@pytest.fixture
def figures(stack):
    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", lambda: build.read_status(stack.gateway), reader)
    yield reader
    metrics.shutdown()


def test_the_status_goes_out_as_figures_counted_by_what_they_count(stack, figures):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's open?", person="ana")
    _, token = stack.open_run()
    with stack.client(token) as c:
        assert c.post("/run/tools/search_records", json={"args": {"query": 5}}).status_code == 403
    found = collected(figures)
    assert (1.0, {"a5s.trigger": "message", "a5s.outcome": "done"}) in found["a5s.runs"]
    assert found["a5s.denied"] == [(1.0, {"a5s.kind": "tool", "a5s.action": "search_records"})]
    assert found["a5s.tokens"] == [(30.0, {"a5s.instance": "assistant-finance"})]
    assert found["a5s.breakers.open"] == [(0.0, {})]
    assert found["a5s.status.readable"] == [(1.0, {})]
    assert set(found) <= set(metrics.FIGURES)


def test_the_figures_never_name_anyone(stack, figures):
    for person in ("ana", "ben"):
        stack.model.reply("Nothing's open for you.")
        stack.say("What's open?", person=person)
    stack.suspend(by="ben")
    found = collected(figures)
    assert found["a5s.instances.not_active"] == [(1.0, {"a5s.status": "suspended"})]  # not by whom
    people = {"ana", "ben", "Ana Ortiz", "Ben Okafor"}
    for name, points in found.items():
        for _, attributes in points:
            assert set(attributes) <= COUNTED_BY, name
            assert not people & set(attributes.values()), name


def test_while_the_status_cant_be_read_there_are_no_figures_but_that():
    def down() -> dict:
        raise RuntimeError("the database is down")

    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", down, reader)
    try:
        assert collected(reader) == {"a5s.status.readable": [(0.0, {})]}
    finally:
        metrics.shutdown()


def test_without_an_endpoint_nothing_is_read_or_sent(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    read = []
    assert not metrics.setup("a5s-gateway", lambda: read.append(1) or {})
    assert not read
