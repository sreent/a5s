"""Round 9 of the critique: operators' figures (core/metrics.py) when the database is down or
hung, and for an instance that serves too few people to count by. A collection reads the
status once, within its deadline, and says first whether it could, so the monitoring still
gets the 0 its runbook alerts on (docs/runbooks.md), and the log one line; and an instance's
own figures go out only once it serves enough people that they're nobody's own use of it
(docs/critique.md, round 9)."""

from __future__ import annotations

import logging
import socket
import threading
import time

import psycopg
import pytest
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    PeriodicExportingMetricReader,
)

from a5s import db
from a5s.core import metrics, registry
from test_metrics import collected
from test_studio_pages import with_ops


class Recording(MetricExporter):
    """An exporter that keeps what it's sent, as a collector would get it."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict[str, list[float]]] = []

    def export(self, metrics_data, timeout_millis: float = 10_000, **kwargs) -> MetricExportResult:
        found: dict[str, list[float]] = {}
        for resource in metrics_data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    found[metric.name] = [p.value for p in metric.data.data_points]
        self.sent.append(found)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


def test_a_status_that_cant_be_read_is_tried_once_a_collection_and_logged_once(caplog):
    """A failed reading serves the whole collection, as a good one does: one read, one line."""
    reads = 0

    def down() -> dict:
        nonlocal reads
        reads += 1
        raise psycopg.OperationalError("connection refused")

    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", down, reader)
    try:
        with caplog.at_level(logging.ERROR, logger="a5s.core.metrics"):
            reader.get_metrics_data()
    finally:
        metrics.shutdown()
    logged = [r for r in caplog.records if r.name == "a5s.core.metrics"]
    assert (reads, len(logged)) == (1, 1), f"{reads} reads and {len(logged)} tracebacks"


@pytest.fixture
def hung_database():
    """A database that takes the connection and never answers, as a server stuck in
    recovery, or a proxy that can't reach it, does: a read fails after the pool's half
    second and A5S_DB_CONNECT_TIMEOUT's two."""
    hung = socket.socket()
    hung.bind(("127.0.0.1", 0))
    hung.listen(128)
    url = f"postgresql://a5s@127.0.0.1:{hung.getsockname()[1]}/postgres"
    yield url
    pool = db._pools.pop(url, None)
    if pool is not None:
        pool.close(timeout=1)
    hung.close()


def test_while_the_database_hangs_the_figures_still_say_its_status_cant_be_read(hung_database):
    """The periodic reader collects within OTEL_METRIC_EXPORT_TIMEOUT, 30 seconds by default,
    as its ticker does: one reading, within its deadline, leaves it time to send the 0."""

    def read_status() -> dict:  # as build.read_status reads it, against the hung database
        with db.transaction(hung_database) as conn:
            return conn.execute("select 1").fetchone()

    exporter = Recording()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=3_600_000)
    assert metrics.setup("a5s-gateway", read_status, reader)
    started = time.monotonic()
    try:
        try:
            reader.collect(timeout_millis=30_000)  # what _ticker does each minute
            problem = None
        except Exception as exc:  # noqa: BLE001  # MetricsTimeoutError: _ticker logs it, sends nothing
            problem = f"{type(exc).__name__}: {exc}"
        took = time.monotonic() - started
        sent = [s for s in exporter.sent if s]
    finally:
        metrics.shutdown()
    assert sent and sent[-1].get("a5s.status.readable") == [0.0], (
        f"after {took:.0f}s, {problem}; the collector got {sent}")


def test_a_reading_that_hangs_is_given_up_on_in_time_and_not_started_again():
    started, release = [], threading.Event()

    def hangs() -> dict:
        started.append(1)
        release.wait(30)
        raise psycopg.OperationalError("it never answered")

    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", hangs, reader)
    try:
        begun = time.monotonic()
        assert collected(reader) == {"a5s.status.readable": [(0.0, {})]}
        assert time.monotonic() - begun < metrics.DEADLINE + 2
        assert started == [1]
    finally:
        release.set()
        metrics.shutdown()


@pytest.fixture
def figures(stack):
    from a5s import build
    reader = InMemoryMetricReader()
    assert metrics.setup("a5s-gateway", lambda: build.read_status(stack.gateway), reader)
    yield reader
    metrics.shutdown()


def test_no_figure_is_one_persons_use(stack, figures):
    with_ops(stack)  # assistant-ops, in orders, serving Chen alone
    stack.model.reply("Nothing's open for you.")
    stack.say("What's open?", person="chen")
    stack.model.reply("Nothing's open for you.")
    stack.say("What's open?", person="ana")
    served = {i.id: registry.served(stack.gateway.scenario, i.serves)
              for i in stack.gateway.scenario.settings().instances}
    small = {i for i, people in served.items() if len(people) < metrics.FEWEST}
    assert {"assistant-ops", "assistant-finance"} <= small  # Chen's alone; Ana's and Ben's
    found = collected(figures)
    theirs = [(name, value) for name, points in found.items() for value, attributes in points
              if attributes.get("a5s.instance") in small]
    assert theirs == [], theirs  # and the three of them together are still too few
    assert "a5s.tokens" not in found or found["a5s.tokens"] == []


def test_smaller_instances_go_out_together_once_together_they_serve_enough(stack, figures,
                                                                          monkeypatch):
    monkeypatch.setattr(metrics, "FEWEST", 3)
    with_ops(stack)
    for person in ("chen", "ana"):
        stack.model.reply("Nothing's open for you.")
        stack.say("What's open?", person=person)
    found = collected(figures)
    assert found["a5s.tokens"] == [(30.0, {"a5s.instance": metrics.SMALLER})]  # 1 + 2 people
