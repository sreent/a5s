"""The alert rules and dashboard in deploy/monitoring name only what the core sends.

The core sends its figures over OpenTelemetry, named a5s.* (core/metrics.py), and the rules and
dashboard name them as the OpenTelemetry Collector's Prometheus exporters write them by default.
So every metric and label they name must be one a figure has, as the collector writes it; each
alert names a runbook section that's there; and the alerts that page out of hours are those the
runbooks' on-call section says page (deploy/monitoring/README.md)."""

from __future__ import annotations

import json
import re

import yaml

from a5s.core import metrics
from conftest import ROOT

MONITORING = ROOT / "deploy" / "monitoring"
METRIC = re.compile(r"\ba5s_[a-z0-9_]+")


def written(name: str, unit: str) -> str:
    """A figure's name, as the collector's Prometheus exporters write it by default."""
    return name.replace(".", "_") + ("_seconds" if unit == "s" else "_ratio" if unit == "1" else "")


SENT = {written(name, unit) for name, (unit, _) in metrics.FIGURES.items()}
# The labels the figures carry, as the collector writes them: the keys core/metrics.py gives each
# value, which aren't figures' own names
LABELS = {key.replace(".", "_") for key in re.findall(
    r'"((?:a5s|gen_ai)\.[a-z0-9_.]+)":', (ROOT / "src/a5s/core/metrics.py").read_text(
        encoding="utf-8")) if key not in metrics.FIGURES}


def rules() -> list[dict]:
    found = yaml.safe_load((MONITORING / "alerts.yaml").read_text(encoding="utf-8"))
    return [dict(rule, group=group["name"]) for group in found["groups"] for rule in group["rules"]]


def exprs() -> list[str]:
    board = json.loads((MONITORING / "dashboard.json").read_text(encoding="utf-8"))
    return [rule["expr"] for rule in rules()] + [
        target["expr"] for panel in board["panels"] for target in panel["targets"]]


def anchors() -> set[str]:
    """Each heading's anchor in the runbooks, as GitHub makes it."""
    text = (ROOT / "docs" / "runbooks.md").read_text(encoding="utf-8")
    return {re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
            for heading in re.findall(r"^#+ (.+)$", text, re.MULTILINE)}


def test_every_metric_and_label_named_is_one_the_core_sends():
    bare = [re.sub(r"by \([^)]*\)|\{[^}]*\}", "", expr) for expr in exprs()]  # labels apart
    named = {m for expr in bare for m in METRIC.findall(expr)}
    assert named and named <= SENT, named - SENT
    grouped = {label.strip() for expr in exprs()
               for labels in re.findall(r"by \(([^)]*)\)", expr) for label in labels.split(",")}
    selected = {label for expr in exprs() for label in re.findall(r"\{(\w+)=", expr)}
    assert grouped | selected <= LABELS, (grouped | selected) - LABELS


def test_each_alert_says_when_and_names_a_runbook_section_thats_there():
    sections = anchors()
    for rule in rules():
        assert rule["labels"]["when"] in ("now", "working hours"), rule["alert"]
        assert rule["annotations"]["summary"].endswith("."), rule["alert"]
        page, _, section = rule["annotations"]["runbook"].partition("#")
        assert page == "docs/runbooks.md" and section in sections, rule["alert"]


def test_what_pages_out_of_hours_is_what_the_on_call_section_says_pages():
    """The ledger's copies failing to copy, lock or verify, and a change stopped part way
    (docs/runbooks.md#on-call): those alone, in the group that pages."""
    paging = {rule["annotations"]["runbook"] for rule in rules() if rule["group"] == "a5s-now"}
    assert paging == {"docs/runbooks.md#the-ledgers-copies-stop",
                      "docs/runbooks.md#changes-wait-or-stop-part-way"}
    assert all(rule["labels"]["when"] == ("now" if rule["group"] == "a5s-now" else "working hours")
               for rule in rules())
