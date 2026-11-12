"""Operators' figures: how a5s is doing, as OpenTelemetry metrics, for the organisation's own
monitoring, such as Prometheus or Azure Monitor through a collector (docs/studio.md).

They're the status's figures (core/status.py), over the last day, each counted by what it
counts, such as an instance, a model, a tool, a trigger or an outcome, and never by a person or
a record, nor with anything anyone said: so whoever reads the monitoring learns how a5s is
doing, and nothing about anyone. Who suspended an instance, and the deciders a rubber-stamp
flag would name, stay in the status alone. An instance's own figures go out only once it
serves at least FEWEST people, since one that serves an executive alone would count their use
of it: smaller ones go together, once together they serve that many, and otherwise not at all.

The figures go to the OpenTelemetry endpoint the deployment names, as the traces do, each
minute by default (OTEL_METRIC_EXPORT_INTERVAL), and nowhere if it names none. Only the
gateway sends them, since it alone reads all they count. A collection reads the status once,
within DEADLINE seconds, and whether it could, a5s.status.readable, is the first figure, so a
database that's down or hung still leaves the monitoring the 0 its runbook alerts on, and the
log one line for each time it went.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

log = logging.getLogger(__name__)
FRESH = 10.0  # seconds one reading of the status serves, so a collection reads it once
DEADLINE = 5.0  # seconds a collection waits for its reading, well within the export's 30
FEWEST = 5  # people an instance serves before its own figures go out [TBC: the officer]
SMALLER = "smaller instances"  # what instances serving fewer go out as, together

# Each figure: its unit and what it says. Its values come from figures(), below.
FIGURES: dict[str, tuple[str, str]] = {
    "a5s.status.readable": ("1", "Whether the gateway could read its status: 1, or 0"),
    "a5s.queue.waiting": ("{message}", "Messages waiting for an answer"),
    "a5s.queue.oldest": ("s", "How long the oldest message waiting has waited"),
    "a5s.runs": ("{run}", "Runs opened over the last day, by trigger and how they ended"),
    "a5s.denied": ("{call}", "Calls denied over the last day, by kind and action, such as a tool"),
    "a5s.turned_away": ("{message}", "Chats a5s turned away over the last day"),
    "a5s.tokens": ("{token}", "Tokens used over the last day, by instance"),
    "a5s.budget.warnings": ("{warning}", "Budget warnings over the last day, by instance"),
    "a5s.deliveries.retrying": ("{message}", "Messages a channel is still trying to deliver"),
    "a5s.deliveries.left_in_inbox": ("{message}", "Messages left in the local inbox"),
    "a5s.deliveries.kept_back": ("{message}", "Answers kept back from a chat someone joined"),
    "a5s.urgent.held": ("{message}", "Urgent messages held past each person's cap"),
    "a5s.changes.waiting": ("{change}", "Held changes waiting for a decision"),
    "a5s.changes.oldest": ("s", "How long the oldest held change has waited"),
    "a5s.changes.stuck": ("{change}", "Approved changes a5s hasn't made after ten minutes"),
    "a5s.changes.not_made": ("{change}", "Approved changes a5s couldn't make, over the last day"),
    "a5s.changes.lapsed": ("{change}", "Held changes that lapsed undecided, over the last day"),
    "a5s.samples.to_grade": ("{sample}", "Samples waiting for a grade"),
    "a5s.samples.lapsed": ("{sample}", "Samples that lapsed ungraded, over the last 91 days"),
    "a5s.caps.level_2": ("{cap}", "Types of action in a part whose cap stands at level 2"),
    "a5s.caps.lowered": ("{cap}", "Caps lowered over the last day"),
    "a5s.unsealed": ("{entry}", "Approvals, decisions and grades the gateway hasn't sealed"),
    "a5s.departures.missing": ("{person}", "People the directory no longer names, not archived"),
    "a5s.instances.not_active": ("{instance}", "Instances not active, by status"),
    "a5s.breakers.open": ("{model}", "Models a5s isn't calling for now, by model"),
    "a5s.replies.answered": ("{message}", "Messages answered over the last day"),
    "a5s.replies.p90": ("s", "How long nine in ten answers took, over the last day"),
    "a5s.chases.on_time": ("1", "The share of what fell due over the last week chased in time"),
    "a5s.questions.answered": ("{question}", "Questions agents answered each other, last day"),
    "a5s.questions.unanswered": ("{question}", "Questions agents left unanswered, last day"),
    "a5s.notebook.kept": ("{note}", "Notes agents keep"),
    "a5s.tasks": ("{task}", "People's tasks by state, and those done or failed in the last day"),
    "a5s.tasks.oldest_due": ("s", "How long the task due longest has waited"),
    "a5s.sign_ins.refused": ("{sign-in}", "Refused for want of a second factor, last day"),
}

_provider: MeterProvider | None = None


def by_instance(rows: list[dict], serving: dict[str, set[str]], *fields: str) -> list[dict]:
    """Rows by instance as the monitoring may have them: each instance's own, if it serves at
    least FEWEST people, and the rest's together, as SMALLER, if together they serve as many."""
    kept = [r for r in rows if len(serving.get(r["instance"], ())) >= FEWEST]
    rest = [r for r in rows if len(serving.get(r["instance"], ())) < FEWEST]
    people = set().union(*(serving.get(r["instance"], set()) for r in rest))
    if rest and len(people) >= FEWEST:
        kept.append({"instance": SMALLER, **{f: sum(r[f] for r in rest) for f in fields}})
    return kept


def figures(status: dict[str, Any]) -> dict[str, list[tuple[float, dict[str, str]]]]:
    """Each figure's values, each with what it counts: never whom. By instance, only as
    `status["serving"]` allows, whom each serves, as by_instance() has them."""
    queue, deliveries, changes = status["queue"], status["deliveries"], status["changes"]
    samples, replies = status["samples"], status["objectives"]["replies"]
    on_time = status["objectives"]["chases"]["on_time"]

    def one(value: Any) -> list[tuple[float, dict[str, str]]]:
        return [] if value is None else [(float(value), {})]

    not_active = Counter(r["status"] for r in status["not_active"])  # never who suspended it
    tokens = by_instance(status["tokens"], status.get("serving", {}), "tokens", "budget_warnings")
    return {
        "a5s.queue.waiting": one(queue["waiting"]),
        "a5s.queue.oldest": one(queue["oldest_seconds"] or 0),
        "a5s.runs": [(float(r["n"]), {"a5s.trigger": str(r["kind"]),
                                      "a5s.outcome": str(r["outcome"])}) for r in status["runs"]],
        "a5s.denied": [(float(r["n"]), {"a5s.kind": str(r["kind"]),
                                        "a5s.action": str(r["action"])})
                       for r in status["denied"]],
        "a5s.turned_away": one(status["turned_away"]),
        "a5s.tokens": [(float(r["tokens"]), {"a5s.instance": r["instance"]}) for r in tokens],
        "a5s.budget.warnings": [(float(r["budget_warnings"]), {"a5s.instance": r["instance"]})
                                for r in tokens],
        "a5s.deliveries.retrying": one(deliveries["retrying"]),
        "a5s.deliveries.left_in_inbox": one(deliveries["left_in_inbox"]),
        "a5s.deliveries.kept_back": one(deliveries["kept_back"]),
        "a5s.urgent.held": one(status["urgent_held"]["messages"]),
        "a5s.changes.waiting": one(changes["waiting"]),
        "a5s.changes.oldest": one(changes["oldest_seconds"] or 0),
        "a5s.changes.stuck": one(changes["stuck"]),
        "a5s.changes.not_made": one(changes["not_made"]),
        "a5s.changes.lapsed": one(changes["lapsed"]),
        "a5s.samples.to_grade": one(samples["to_grade"]),
        "a5s.samples.lapsed": one(samples["lapsed"]),
        "a5s.caps.level_2": one(len(samples["level_2"])),
        "a5s.caps.lowered": one(samples["caps_lowered"]),
        "a5s.unsealed": one(status["unsealed"]),
        "a5s.departures.missing": one(status["missing"]),
        "a5s.instances.not_active": [(float(n), {"a5s.status": s})
                                     for s, n in sorted(not_active.items())] or one(0),
        "a5s.breakers.open": [(1.0, {"gen_ai.request.model": m})
                              for m in status["breakers_open"]] or one(0),
        "a5s.replies.answered": one(replies["answered"]),
        "a5s.replies.p90": one(replies["p90_seconds"]),
        "a5s.chases.on_time": one(on_time),
        "a5s.questions.answered": one(status["questions"]["answered"]),
        "a5s.questions.unanswered": one(status["questions"]["unanswered"]),
        "a5s.notebook.kept": one(status["notebook"]["kept"]),
        "a5s.tasks": [(float(tasks[k]), {"a5s.status": k}) for k in (
            "at_work", "due", "blocked", "lapsed", "done", "failed")] if (
                tasks := status.get("tasks")) else one(0),
        "a5s.tasks.oldest_due": one((status.get("tasks") or {}).get("oldest_due_seconds") or 0),
        "a5s.sign_ins.refused": [(float(n), {"a5s.action": doing}) for doing, n in sorted(
            ((status.get("sign_ins") or {}).get("refused") or {}).items())] or one(0),
    }


class Readings:
    """The status, read at most once each FRESH seconds, whether or not it could be, so each
    figure of a collection comes from the same reading. None while it can't be read, or takes
    longer than DEADLINE: no figures, rather than stale ones. One read at a time: while one
    hangs, the next collection waits for it again, and starts no other."""

    def __init__(self, read: Callable[[], dict[str, Any]], deadline: float = DEADLINE):
        self._read, self._deadline, self._lock = read, deadline, threading.Lock()
        self._at, self._found = float("-inf"), None
        self._reading: threading.Thread | None = None
        self._got: dict[str, Any] = {}
        self._down = False  # whether it was last unreadable: said once a time it goes

    def now(self) -> dict[str, list[tuple[float, dict[str, str]]]] | None:
        with self._lock:
            if time.monotonic() - self._at <= FRESH:
                return self._found
            if self._reading is None or not self._reading.is_alive():
                self._got = {}
                self._reading = threading.Thread(target=self._reads, args=(self._got,),
                                                 name="a5s-metrics-status", daemon=True)
                self._reading.start()
            self._reading.join(self._deadline)
            self._at = time.monotonic()
            got = {} if self._reading.is_alive() else self._got
            self._found = got.get("figures")
            if self._found is None and not self._down:
                log.error("couldn't read the status for the metrics: %s",
                          got.get("error") or f"it took longer than {self._deadline:g}s")
            elif self._found is not None and self._down:
                log.info("could read the status for the metrics again")
            self._down = self._found is None
            return self._found

    def _reads(self, got: dict[str, Any]) -> None:
        try:
            got["figures"] = figures(self._read())
        except Exception as exc:  # noqa: BLE001 - said by now(), once a time it goes
            got["error"] = f"{type(exc).__name__}: {exc}"[:300]


def setup(service: str, read: Callable[[], dict[str, Any]],
          reader: MetricReader | None = None) -> bool:
    """Send the status's figures, as `read` reads it, to the deployment's endpoint, or to
    `reader`. Whether they go anywhere: without an endpoint, nothing is read or sent."""
    global _provider
    if reader is None:
        if not (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                or os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")):
            return False
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    readings = Readings(read)
    _provider = MeterProvider(metric_readers=[reader],
                              resource=Resource.create({"service.name": service}))
    meter = _provider.get_meter("a5s")
    for name, (unit, description) in FIGURES.items():
        meter.create_observable_gauge(name, callbacks=[_observing(readings, name)], unit=unit,
                                      description=description)
    return True


def _observing(readings: Readings, name: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
    def observe(options: CallbackOptions) -> Iterable[Observation]:
        found = readings.now()
        if name == "a5s.status.readable":
            return [Observation(0.0 if found is None else 1.0)]
        return [Observation(value, attributes) for value, attributes in (found or {}).get(name, [])]
    return observe


def shutdown() -> None:
    """Send what's left, and stop: for tests, and a part that stops."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None
