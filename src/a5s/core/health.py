"""The reliability ledger (docs/model-execution.md): per model, per day, how its calls went,
and the SLO gate. A model that fails too often is stopped from answering — tightening is
automatic — and returns only when a person restores it, as every loosening needs one."""
from __future__ import annotations

from typing import Any

from a5s import db

# What a model must keep to stay answerable: over a day, with at least this many calls, at
# most this share may fail. One model's own may come from its release later; a default is
# the same for every approved model, and the gate still lifts only by a person.
SLO = {"min_calls": 20, "stall_rate": 0.5, "window_days": 1}


def record(conn: db.Connection, scenario: str, alias: str, status: int,
           seconds: float) -> None:
    """One model call's outcome, counted into the day's row: calls, failures, stalls and
    their time, so a page or a policy can measure the model rather than argue about it."""
    conn.execute(
        "insert into model_health (scenario, model, day, calls, failed, stalls, seconds) "
        "values (%s, %s, current_date, 1, %s, %s, %s) "
        "on conflict (scenario, model, day) do update set calls = model_health.calls + 1, "
        "failed = model_health.failed + excluded.failed, "
        "stalls = model_health.stalls + excluded.stalls, "
        "seconds = model_health.seconds + excluded.seconds",
        (scenario, alias, 1 if status >= 400 else 0, 1 if status >= 500 else 0, seconds))


def gated(conn: db.Connection, scenario: str, alias: str,
          slo: dict[str, Any] | None = None) -> str | None:
    """Why the model isn't answerable, or None: over its window, with at least its SLO's
    calls, more than its share failed, and a person hasn't restored it since."""
    if slo is None:
        slo = SLO
    row = conn.execute(
        "select sum(calls)::int as calls, sum(stalls)::int as stalls, max(gated_at) as gate, "
        "(max(restored_at) >= date_trunc('day', now())) as restored_today "
        "from model_health where scenario = %s and model = %s and "
        "day > current_date - make_interval(days => %s)",
        (scenario, alias, slo["window_days"])).fetchone()
    if row is None:
        return None  # no calls recorded for it: nothing to gate
    if row["gate"] is not None:
        return f"{alias} failed too much, and a person hasn't put it back"
    if row["restored_today"]:
        return None  # a person put it back today: their decision stands for the day
    calls, stalls = row["calls"] or 0, row["stalls"] or 0
    if calls >= slo["min_calls"] and stalls / calls > slo["stall_rate"]:
        conn.execute("update model_health set gated_at = now() where scenario = %s and "
                     "model = %s and day = current_date", (scenario, alias))
        return f"{alias} failed {stalls} of its last {calls} calls: a5s stopped using it"
    return None


def restore(conn: db.Connection, scenario: str, alias: str) -> None:
    """A person puts the model back, and it stays gated in the day's row as the record of
    why it was stopped. Their decision stands for the day; tomorrow's calls are judged again."""
    conn.execute("update model_health set gated_at = null, restored_at = now() "
                 "where scenario = %s and model = %s", (scenario, alias))


def report(database: str, scenario: str, days: int = 1) -> list[dict[str, Any]]:
    """Each model's day: calls, failures, stalls, their mean time, and whether it's gated,
    for a page or the command line."""
    with db.connect(database) as conn:
        rows = conn.execute(
            "select model, sum(calls)::int as calls, sum(failed)::int as failed, "
            "sum(stalls)::int as stalls, "
            "round((sum(seconds) / nullif(sum(calls), 0)::real)::numeric, 2) as mean_seconds, "
            "max(gated_at) as gated_at from model_health where scenario = %s and "
            "day > current_date - make_interval(days => %s) group by model order by model",
            (scenario, days)).fetchall()
    return [dict(row) for row in rows]