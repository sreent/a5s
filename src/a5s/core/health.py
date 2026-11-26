"""The reliability ledger (docs/model-execution.md): per model, per day, how its calls went,
and the SLO gate. A model that fails too often is stopped from answering — tightening is
automatic — and returns only when a person restores it, as every loosening needs one: the
release approver, through the core, which records who did in the ledger. A stop outlasts the
day it was made in, so a new day doesn't put a model back by itself."""
from __future__ import annotations

from typing import Any

from a5s import db
from a5s.core import registry

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
    """Why the model isn't answerable, or None: the gate stopped it, on any day, and a person
    hasn't put it back since; or over its window, with at least its SLO's calls, more than its
    share failed."""
    if slo is None:
        slo = SLO
    if stopped(conn, scenario, alias):
        return f"{alias} failed too much, and a person hasn't put it back"
    row = conn.execute(
        "select sum(calls)::int as calls, sum(stalls)::int as stalls, "
        "(max(restored_at) >= date_trunc('day', now())) as restored_today "
        "from model_health where scenario = %s and model = %s and "
        "day > current_date - make_interval(days => %s)",
        (scenario, alias, slo["window_days"])).fetchone()
    if row is None:
        return None  # no calls recorded for it: nothing to gate
    if row["restored_today"]:
        return None  # a person put it back today: their decision stands for the day
    calls, stalls = row["calls"] or 0, row["stalls"] or 0
    if calls >= slo["min_calls"] and stalls / calls > slo["stall_rate"]:
        conn.execute("update model_health set gated_at = now() where scenario = %s and "
                     "model = %s and day = current_date", (scenario, alias))
        return f"{alias} failed {stalls} of its last {calls} calls: a5s stopped using it"
    return None


def stopped(conn: db.Connection, scenario: str, alias: str) -> bool:
    """Whether the gate stopped the model and nobody has put it back since."""
    return conn.execute("select 1 from model_health where scenario = %s and model = %s and "
                        "gated_at is not null limit 1", (scenario, alias)).fetchone() is not None


def running_on(conn: db.Connection, alias: str) -> list[dict[str, Any]]:
    """The instances at work whose own model it is, and whom each serves, as the settings name
    them: what putting it back reaches first."""
    return conn.execute("select id, serves from instances where model = %s and status <> "
                        "'retired' order by id", (alias,)).fetchall()


def reach(conn: db.Connection, scenario: Any, alias: str) -> tuple[list[str], int]:
    """Whom putting a stopped model back reaches, said before it's done and once it is
    (docs/design.md): the instances at work whose own model it is, which call it again from
    their next run, and how many people they serve, as the directory says now. A release that
    falls back to it may call it again too, as `model_for` chooses."""
    rows = running_on(conn, alias)
    people = {p for r in rows for p in registry.served(scenario, r["serves"] or [])}
    return [r["id"] for r in rows], len(people)


def reached(instances: list[str], people: int) -> str:
    """What putting a model back reaches, in a sentence, as `reach` found it."""
    if not instances:
        return ("No instance at work runs on it, though a release that falls back to it may "
                "call it again.")
    one = len(instances) == 1
    which = instances[0] if one else ", ".join(instances[:-1]) + " and " + instances[-1]
    whom = "the one person" if people == 1 else f"the {people} people"
    return (f"{which} {'calls' if one else 'call'} it again from {'its' if one else 'their'} "
            f"next run, for {whom} {'it serves' if one else 'they serve'}.")


def restore(conn: db.Connection, scenario: str, alias: str) -> None:
    """A person puts the model back, and it stays gated in the day's row as the record of
    why it was stopped. Their decision stands for the day; tomorrow's calls are judged again."""
    conn.execute("update model_health set gated_at = null, restored_at = now() "
                 "where scenario = %s and model = %s", (scenario, alias))


def report(database: str, scenario: str, days: int = 1) -> list[dict[str, Any]]:
    """Each model's days: calls, failures, stalls and their mean time over the last `days`,
    and when the gate stopped it, if nobody has put it back since, for a page or the command
    line. A stopped model is listed even with no calls in those days, since a5s calls it no
    more: it's what the release approver may put back."""
    recent = "filter (where day > current_date - make_interval(days => %(days)s))"
    with db.connect(database) as conn:
        rows = conn.execute(
            f"select model, coalesce(sum(calls) {recent}, 0)::int as calls, "
            f"coalesce(sum(failed) {recent}, 0)::int as failed, "
            f"coalesce(sum(stalls) {recent}, 0)::int as stalls, "
            f"round((sum(seconds) {recent} / nullif(sum(calls) {recent}, 0)::real)::numeric, 2) "
            "as mean_seconds, max(gated_at) as gated_at from model_health "
            "where scenario = %(scenario)s group by model "
            f"having count(*) {recent} > 0 or max(gated_at) is not null order by model",
            {"scenario": scenario, "days": days}).fetchall()
    return [dict(row) for row in rows]