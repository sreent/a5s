# Monitoring a5s

The core sends its status's figures to the deployment's OpenTelemetry endpoint each minute
(`OTEL_EXPORTER_OTLP_ENDPOINT`, or the chart's `telemetry.endpoint`), named `a5s.*`
([`core/metrics.py`](../../src/a5s/core/metrics.py)). Here are alert rules and a dashboard for
them, as most organisations' monitoring reads them:

- [`alerts.yaml`](alerts.yaml): Prometheus rules, for Prometheus or anything that reads its rule
  files, such as Grafana Mimir or Thanos. Load it as a rule file, or wrap its `groups` in a
  `PrometheusRule` where the Prometheus Operator runs. Its first group pages out of hours too, as
  the [runbooks' on-call section](../../docs/runbooks.md#on-call) says: the ledger's copies
  stopping, failing, falling behind or not matching, and a change stopped part way through being
  made. The second waits for working hours. Each alert's `runbook` names the section on what to do.
- [`dashboard.json`](dashboard.json): a Grafana dashboard. Import it, and choose the Prometheus
  data source that holds a5s's figures.

Both name the figures as the OpenTelemetry Collector's Prometheus exporters write them by
default: dots become underscores, a figure in seconds ends in `_seconds`, and one that's 1 or 0
ends in `_ratio`, so `a5s.ledger.copies.age` is `a5s_ledger_copies_age_seconds`. With
`add_metric_suffixes: false`, drop those two endings. A test keeps every name here to a figure
the core sends ([`tests/test_monitoring.py`](../../tests/test_monitoring.py)).

Without an endpoint, `a5s status` and the studio's Status page say the same, for the team that
runs a5s, and `a5s doctor` checks a deployment as a whole
([runbooks](../../docs/runbooks.md#start-with-a5s-doctor)).
