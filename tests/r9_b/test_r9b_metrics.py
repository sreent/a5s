"""Round 9, reviewer B: operators' figures (core/metrics.py) when the database is down or hung.
The runbook's alert for that is `a5s.status.readable` at 0 (docs/runbooks.md)."""

from __future__ import annotations

import logging
import socket
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
from a5s.core import metrics


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
    """Readings keeps a failure for no time at all (`not self._ok` forces a new read), so
    each of the 31 gauges reads the status again in the same collection, and logs a full
    traceback each time: 31 database round trips and 31 tracebacks a minute while it's down."""
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
    as its ticker does. Each of the 31 gauges waits 2.5 seconds for its own failed read, so
    the collection times out about twelve gauges in, before a5s.status.readable, the last:
    nothing at all is exported, not even the 0 the runbook alerts on."""

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


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
