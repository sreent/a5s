"""Samples: graded evidence of how accurate an agent's work is, which raises or lowers a5s's
cap on its level.

a5s keeps a cap for each release, part and type of action, which starts at 1, and an
instance works at the lower of its settings and the cap (core/parts.py). Code draws samples
of each release's changes: every held change someone decided, while the cap is still 1, and
at level 2 every change made until there are 100 in the quarter. People who hold the grader
role grade them on the core's page, as right, wrong or critical: never anyone from the team
of the agent's owner, nor anyone the change was for or who decided it, and only for records
they may see.

A sequential test, pooled across the release's instances, weighs the grades for each
release, part and type of action. It raises the cap to 2 once the evidence shows, with 95%
confidence, that accuracy meets the part's threshold in the settings, and lowers it to 1
once the evidence shows accuracy below it, or at once on a critical error. A part with no
threshold never earns level 2. The test is anytime-valid: a mixture likelihood ratio, a
test supermartingale under the hypothesis it tests, so checking it after every grade keeps
its error at 5%, by Ville's inequality. With no errors, a 98% threshold needs 224 graded
items, and a 95% one 88. A release that changes starts again at 1, since caps are its own.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Person, Record, Scenario

GRADER = "grader"  # the directory's role for people who grade agents' work
GRADES = ("right", "wrong", "critical")
ALPHA = 0.05  # the test's error: 95% confidence
PER_QUARTER = 100  # changes made at level 2 sampled, for each release, part and type
_STEPS = 2000  # for integrating the mixture: even, for Simpson's rule


def _log_integral(errors: int, rights: int, lo: float, hi: float) -> float:
    """log of the integral of q^errors (1 - q)^rights over [lo, hi], by Simpson's rule."""
    h = (hi - lo) / _STEPS
    terms = []
    for i in range(_STEPS + 1):
        q = lo + i * h
        if (q <= 0 and errors) or (q >= 1 and rights):
            continue  # the integrand is 0 there
        value = (errors * math.log(q) if errors else 0.0) + (rights * math.log1p(-q) if rights else 0.0)
        terms.append(value + math.log(1 if i in (0, _STEPS) else 4 if i % 2 else 2))
    if not terms:
        return -math.inf
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms)) + math.log(h / 3)


def log_evidence(graded: int, errors: int, threshold: float, toward: str) -> float:
    """The log of the evidence that the error rate is below 1 - threshold (toward 'up') or
    above it ('down'): the likelihood of the grades mixed uniformly over the error rates on
    that side, against their likelihood at the threshold itself."""
    q0 = 1 - threshold
    lo, hi = (0.0, q0) if toward == "up" else (q0, 1.0)
    rights = graded - errors
    at = (errors * math.log(q0) if errors else 0.0) + (rights * math.log1p(-q0) if rights else 0.0)
    return _log_integral(errors, rights, lo, hi) - math.log(hi - lo) - at


def shows(graded: int, errors: int, threshold: float, toward: str) -> bool:
    """Whether the grades show, with 95% confidence, that accuracy meets the threshold ('up')
    or falls below it ('down')."""
    return graded > 0 and log_evidence(graded, errors, threshold, toward) >= math.log(1 / ALPHA)


def needed(threshold: float, errors: int = 0) -> int:
    """How many graded items, with this many errors, raise the cap: for the starting values."""
    graded = errors + 1
    while not shows(graded, errors, threshold, "up"):
        graded += 1
    return graded


# Drawing samples

def cap(conn: psycopg.Connection, release: str, part: str, action: str) -> int:
    row = conn.execute("select cap from caps where release = %s and part = %s and action = %s",
                       (release, part, action)).fetchone()
    return row["cap"] if row else 1


def _snapshot(records: dict[str, Record | None]) -> dict:
    return {k: {"title": r.title, "fields": r.fields, "link": r.link} if r else None
            for k, r in records.items()}


def draw(conn: psycopg.Connection, scenario: str, kind: str, release: str, definition: str,
         instance: str, run: str, part: str, action: str, said: str,
         records: dict[str, Record | None], acts_for: list[str], now: datetime,
         proposal: int | None = None, decided: str | None = None,
         decided_by: str | None = None) -> bool:
    """Draw a change as a sample for grading, if it's one a5s samples now: a decided held
    change while the cap is still 1, or a change made at level 2 while the quarter has fewer
    than 100. Whether it drew one."""
    if kind == "proposal" and cap(conn, release, part, action) >= 2:
        return False
    if kind == "action":
        starts = date(now.year, 3 * ((now.month - 1) // 3) + 1, 1)
        drawn = conn.execute(
            "select count(*) as n from samples where kind = 'action' and release = %s "
            "and part = %s and action = %s and drawn_at >= %s",
            (release, part, action, starts)).fetchone()["n"]
        if drawn >= PER_QUARTER:
            return False
    conn.execute(
        "insert into samples (scenario, kind, proposal_id, run_id, instance_id, release, "
        "definition, part, action, said, records, acts_for, decided, decided_by, drawn_at) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (scenario, kind, proposal, run, instance, release, definition, part, action, said,
         Jsonb(_snapshot(records)), acts_for, decided, decided_by, now))
    return True


# Grading

def may_grade(scenario: Scenario, sample: dict, person: Person) -> str | None:
    """Why someone may not grade a sample, if they may not."""
    if GRADER not in person.roles:
        return f"{person.name} doesn't grade agents' work"
    builders = {p.team for p in scenario.holders(f"agent-owner:{sample['definition']}")}
    if person.team in builders:
        return f"graders come from outside the team that built the {sample['definition']}"
    if person.id in sample["acts_for"] or person.id == sample["decided_by"]:
        return "nobody grades a change they asked for or decided"
    if not all(scenario.sees(person.id, r) for r in sample["records"]):
        return "it names a record they may not see"
    return None


# Weighing the grades

def assess(conn: psycopg.Connection, release: str, part: str, action: str,
           threshold: float | None, now: datetime) -> dict | None:
    """Raise or lower a release's cap for a type of action in a part, if its grades now show
    it should: what changed, with the evidence, for the ledger. None if nothing did."""
    grades = conn.execute("select grade, graded_at from samples where release = %s and part = %s "
                          "and action = %s and grade is not null", (release, part, action)).fetchall()
    row = conn.execute("select cap, since from caps where release = %s and part = %s "
                       "and action = %s", (release, part, action)).fetchone()
    now_cap, since = (row["cap"], row["since"]) if row else (1, None)
    graded = len(grades)
    errors = sum(g["grade"] != "right" for g in grades)
    critical = any(g["grade"] == "critical" and (since is None or g["graded_at"] > since)
                   for g in grades)
    evidence = {"graded": graded, "errors": errors, "threshold": threshold}
    if critical and now_cap >= 2:
        return _set(conn, release, part, action, 1, "a critical error", evidence, now)
    if threshold is None:
        return None if now_cap < 2 else _set(conn, release, part, action, 1,
                                             "the part has no threshold", evidence, now)
    if now_cap < 2 and not critical and shows(graded, errors, threshold, "up"):
        return _set(conn, release, part, action, 2, "graded samples show it meets the threshold",
                    evidence, now)
    if now_cap >= 2 and shows(graded, errors, threshold, "down"):
        return _set(conn, release, part, action, 1, "graded samples show it falls short",
                    evidence, now)
    return None


def _set(conn: psycopg.Connection, release: str, part: str, action: str, to: int, why: str,
         evidence: dict, now: datetime) -> dict:
    conn.execute("insert into caps (release, part, action, cap, since, why) values "
                 "(%s, %s, %s, %s, %s, %s) on conflict (release, part, action) do update set "
                 "cap = excluded.cap, since = excluded.since, why = excluded.why",
                 (release, part, action, to, now, why))
    return {"release": release, "part": part, "action": action, "cap": to, "why": why, **evidence}


def rubber_stamps(conn: psycopg.Connection) -> list[dict]:
    """Deciders whose approvals are graded wrong far more often than everyone else's: at least
    three wrong, and over twice the rate of the rest."""
    rows = conn.execute(
        "select decided_by as person, count(*) as approved, "
        "count(*) filter (where grade <> 'right') as wrong from samples "
        "where kind = 'proposal' and decided = 'approve' and grade is not null "
        "and decided_by is not null group by decided_by").fetchall()
    flagged = []
    for row in rows:
        rest = [r for r in rows if r["person"] != row["person"]]
        rest_approved = sum(r["approved"] for r in rest)
        rest_rate = sum(r["wrong"] for r in rest) / rest_approved if rest_approved else 0.0
        if row["wrong"] >= 3 and row["wrong"] / row["approved"] > 2 * rest_rate:
            flagged.append({"person": row["person"], "approved": row["approved"],
                            "graded_wrong": row["wrong"]})
    return flagged
