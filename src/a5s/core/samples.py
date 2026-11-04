"""Samples: graded evidence of how accurate an agent's work is, which raises or lowers a5s's
cap on its level.

a5s keeps a cap for each behaviour, part and type of action, which starts at 1, and an
instance works at the lower of its settings and the cap (core/parts.py). A behaviour is what
decides how a release acts on a type of action: its agent, its model, and the tools of that
type it may use, as pinned. A release that changes only instructions keeps its behaviours,
and the level their grades earned, as the release table says, since it needs the regression
suite and a re-run of the last graded samples; one that changes a tool of that type, or the
model, has a new behaviour, and starts again at 1 for what it widens.

Code draws samples of each behaviour's changes: every held change someone decided, while the
cap is still 1, and at level 2 changes made, at random, about 100 a quarter, spread through
it. A sample keeps what code flagged to the decider and the records as they stood when the
change was asked for. People who hold the grader role grade them on the core's page, as
right, wrong or critical, signing in afresh to give exactly those grades, which the core
seals. Never anyone from the team that built the agent, or of the instance's owner or
deputy, nor anyone the change was for or who decided it, nor anyone who reports to whoever
decided it, and only for records they may see. A sample nobody grades in a quarter lapses.

A sequential test weighs the sealed grades for each behaviour, part and type of action given
since its cap last changed, so each change starts a fresh test. It raises the cap to 2 once
the evidence shows, with 95% confidence, that accuracy meets the part's threshold in the
settings, and lowers it to 1 once the evidence shows accuracy below it, at once on a critical
error, or when the part's threshold rises past what the grades that earned it show. A part
with no threshold never earns level 2, and while the settings in force don't check out the
test weighs nothing. The test is anytime-valid: a mixture likelihood ratio, a test
supermartingale under the hypothesis it tests, so checking it after every grade keeps its
error at 5%, by Ville's inequality. With no errors, a 98% threshold needs 224 graded items,
and a 95% one 88. The core seals each cap with the ledger entry that set it, so a row written
into the database, or an old one put back, doesn't count, and anyone who may can lower a cap
at once (`a5s caps lower`), never raise one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import random
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Person, Scenario, Tool
from a5s.core import ledger
from a5s.core.ledger import canonical

GRADER = "grader"  # the directory's role for people who grade agents' work
GRADES = ("right", "wrong", "critical")
ALPHA = 0.05  # the test's error: 95% confidence
PER_QUARTER = 100  # changes made at level 2 sampled, for each behaviour, part and type
LAPSE = timedelta(days=91)  # a sample nobody grades in a quarter lapses
_SEALED_GRADE = ("scenario", "id", "grade", "graded_by", "graded_at", "grade_token",
                 "grade_nonce", "grade_salt", "grade_issuer", "grade_subject")
_SEALED_CAP = ("behaviour", "part", "action", "cap", "since", "why", "threshold", "window_from",
               "seq")


def behaviour(agent: str, model: str, pins: dict[str, str], tool_names: Iterable[str],
              tools: dict[str, Tool], action: str) -> str:
    """What decides how a release acts on a type of action: its agent, its model, and the
    tools of that type it may use, as pinned."""
    used = sorted(n for n in tool_names if (t := tools.get(n)) is not None and t.action == action)
    return hashlib.sha256(canonical({"agent": agent, "model": model,
                                     "tools": {n: pins.get(n) for n in used}}).encode()).hexdigest()


def note_behaviours(conn: psycopg.Connection, definitions: Iterable[Any],
                    tools: dict[str, Tool]) -> None:
    """Keep each release's behaviour for each type of action its tools take."""
    for d in definitions:
        for action in sorted({t.action for n in d.tool_names if (t := tools.get(n)) and t.action}):
            conn.execute("insert into behaviours (release, action, behaviour) values (%s, %s, %s) "
                         "on conflict do nothing",
                         (d.release_id, action,
                          behaviour(d.id, d.model, d.pins, d.tool_names, tools, action)))


# The test

def _log_tail(n: int, k: int, x: float, upper: bool) -> float:
    """log P(Binomial(n, x) >= k), or, not upper, <= k - 1, exactly."""
    if (upper and k <= 0) or (not upper and k > n):
        return 0.0
    if x <= 0:
        return -math.inf if upper else 0.0
    if x >= 1:
        return 0.0 if upper else -math.inf
    terms = [math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1)
             + j * math.log(x) + (n - j) * math.log1p(-x)
             for j in (range(k, n + 1) if upper else range(k))]
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def _log_minus(a: float, b: float) -> float:
    """log(exp(a) - exp(b)), for a >= b."""
    if b == -math.inf:
        return a
    if b >= a:
        return -math.inf
    return a + math.log1p(-math.exp(b - a))


def _log_integral(errors: int, rights: int, lo: float, hi: float) -> float:
    """log of the integral of q^errors (1 - q)^rights over [lo, hi], exactly: the beta
    function times the difference of the regularised incomplete beta at hi and lo, each a
    binomial tail, from whichever tail doesn't cancel."""
    n, k = errors + rights + 1, errors + 1
    log_beta = math.lgamma(errors + 1) + math.lgamma(rights + 1) - math.lgamma(n + 1)
    up_hi = _log_tail(n, k, hi, upper=True)
    if up_hi < math.log(0.5):
        return log_beta + _log_minus(up_hi, _log_tail(n, k, lo, upper=True))
    return log_beta + _log_minus(_log_tail(n, k, lo, upper=False), _log_tail(n, k, hi, upper=False))


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


# Caps, which count only as the core sealed them, with the ledger's last word on each

def _mac(key: str, fields: dict, names: tuple[str, ...]) -> str:
    shown = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()
             if k in names}
    return hmac.new(key.encode(), canonical(shown).encode(), hashlib.sha256).hexdigest()


def _sealed(keys: tuple[str, ...], row: dict, names: tuple[str, ...], seal: str | None) -> bool:
    return bool(keys) and bool(seal) and any(
        hmac.compare_digest(_mac(k, row, names), seal) for k in keys)


def _last_entries(conn: psycopg.Connection) -> dict[tuple[str, str, str], int]:
    """The ledger's last entry for each cap: what a cap's row must carry to count."""
    last = {}
    for row in conn.execute("select seq, entry from ledger where kind = 'cap' order by seq"):
        args = json.loads(row["entry"]).get("args") or {}
        if args.get("behaviour"):
            last[(args["behaviour"], args["part"], args["action"])] = row["seq"]
    return last


def standing_caps(conn: psycopg.Connection, keys: tuple[str, ...],
                  where: str = "true", params: tuple = ()) -> list[dict]:
    """The caps that count: sealed by the core, each with the ledger's last entry for it."""
    last = _last_entries(conn)
    return [r for r in conn.execute(f"select * from caps where behaviour is not null and {where}",
                                    params).fetchall()
            if _sealed(keys, r, _SEALED_CAP, r["seal"])
            and last.get((r["behaviour"], r["part"], r["action"])) == r["seq"]]


def caps(conn: psycopg.Connection, keys: tuple[str, ...], release: str) -> dict[tuple[str, str], int]:
    """a5s's caps for a release's types of action in each part: 1 where there's none."""
    mine = {r["action"]: r["behaviour"] for r in conn.execute(
        "select action, behaviour from behaviours where release = %s", (release,))}
    if not mine:
        return {}
    return {(r["part"], r["action"]): r["cap"] for r in standing_caps(
        conn, keys, "behaviour = any(%s)", (list(mine.values()),))
        if mine.get(r["action"]) == r["behaviour"]}


def _cap_row(conn: psycopg.Connection, keys: tuple[str, ...], kind: str, part: str,
             action: str) -> dict | None:
    found = standing_caps(conn, keys, "behaviour = %s and part = %s and action = %s",
                          (kind, part, action))
    return found[0] if found else None


def behaviour_of(conn: psycopg.Connection, release: str, action: str) -> str | None:
    row = conn.execute("select behaviour from behaviours where release = %s and action = %s",
                       (release, action)).fetchone()
    return row["behaviour"] if row else None


def set_cap(conn: psycopg.Connection, keys: tuple[str, ...], kind: str, part: str, action: str,
            to: int, why: str, now: datetime, evidence: dict | None = None,
            threshold: float | None = None, window_from: datetime | None = None) -> dict:
    """Set a cap, recorded in the ledger and sealed with that entry: what changed."""
    found = {"behaviour": kind, "part": part, "action": action, "cap": to, "why": why,
             **(evidence or {})}
    seq = ledger.append(conn, {"kind": "cap", "action": "raise" if to >= 2 else "lower",
                               "run": None, "instance": None, "acts_for": [],
                               "decision": "record", "args": found})
    row = {"behaviour": kind, "part": part, "action": action, "cap": to, "since": now, "why": why,
           "threshold": threshold, "window_from": window_from, "seq": seq}
    conn.execute("insert into caps (behaviour, part, action, cap, since, why, threshold, "
                 "window_from, seq, seal) values (%(behaviour)s, %(part)s, %(action)s, %(cap)s, "
                 "%(since)s, %(why)s, %(threshold)s, %(window_from)s, %(seq)s, %(seal)s) "
                 "on conflict (behaviour, part, action) do update set cap = excluded.cap, "
                 "since = excluded.since, why = excluded.why, threshold = excluded.threshold, "
                 "window_from = excluded.window_from, seq = excluded.seq, seal = excluded.seal",
                 {**row, "seal": _mac(keys[0], row, _SEALED_CAP)})
    return found


# Drawing samples

def draw(conn: psycopg.Connection, keys: tuple[str, ...], scenario: str, kind: str, release: str,
         definition: str, instance: str, run: str, part: str, action: str, said: str,
         records: dict[str, dict | None], acts_for: list[str], now: datetime,
         proposal: int | None = None, decided: str | None = None,
         decided_by: str | None = None, flags: list[str] | None = None) -> bool:
    """Draw a change as a sample for grading, if it's one a5s samples now: a decided held
    change while the cap is still 1, or, at level 2, a change made, at random, at a rate that
    spreads about 100 through the quarter, by how many the last 30 days made. Whether it drew
    one."""
    behaves = behaviour_of(conn, release, action)
    current = _cap_row(conn, keys, behaves, part, action) if behaves else None
    if kind == "proposal" and current is not None and current["cap"] >= 2:
        return False
    if kind == "action":
        starts = date(now.year, 3 * ((now.month - 1) // 3) + 1, 1)
        drawn = conn.execute(
            "select count(*) as n from samples where kind = 'action' and release = %s "
            "and part = %s and action = %s and drawn_at >= %s",
            (release, part, action, starts)).fetchone()["n"]
        lately = conn.execute(
            "select coalesce(sum(records), 0) as n from action_counts where action = %s "
            "and state = 'made' and at > %s and instance_id = %s",
            (action, now - timedelta(days=30), instance)).fetchone()["n"]
        rate = min(1.0, PER_QUARTER / max(3 * lately, 1))
        if drawn >= PER_QUARTER or random.random() >= rate:  # a sample, not a secret
            return False
    conn.execute(
        "insert into samples (scenario, kind, proposal_id, run_id, instance_id, release, "
        "definition, part, action, said, records, acts_for, decided, decided_by, drawn_at, flags) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (scenario, kind, proposal, run, instance, release, definition, part, action, said,
         Jsonb(records), acts_for, decided, decided_by, now, Jsonb(list(flags or []))))
    return True


# Grading

def may_grade(scenario: Scenario, sample: dict, person: Person,
              minders: Iterable[str] = ()) -> str | None:
    """Why someone may not grade a sample, if they may not. `minders` are the owner and the
    deputy of the sample's instance."""
    if GRADER not in person.roles:
        return f"{person.name} doesn't grade agents' work"
    builders = {p.team for p in scenario.holders(f"agent-owner:{sample['definition']}")}
    if person.team in builders:
        return f"graders come from outside the team that built the {sample['definition']}"
    if person.team in {who.team for m in minders if m and (who := scenario.person(m))}:
        return "graders come from outside the teams of the instance's owner and deputy"
    if person.id in sample["acts_for"] or person.id == sample["decided_by"]:
        return "nobody grades a change they asked for or decided"
    above, seen = scenario.person(person.manager) if person.manager else None, set()
    while above is not None and above.id not in seen:
        if above.id == sample["decided_by"]:
            return "nobody grades the decisions of someone they report to"
        seen.add(above.id)
        above = scenario.person(above.manager) if above.manager else None
    if not all(scenario.sees(person.id, r) for r in sample["records"]):
        return "it names a record they may not see"
    return None


def nonce(grades: dict[int, str], salt: str) -> str:
    """What a sign-in to grade carries, so the provider's signature covers exactly these
    grades of these samples. The page picks the salt, so each sign-in is different."""
    pairs = ",".join(f"{s}:{g}" for s, g in sorted(grades.items()))
    bound = hashlib.sha256(f"a5s grades samples {pairs} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


def seal(keys: tuple[str, ...], row: dict) -> str:
    """The core's seal over a grade."""
    return _mac(keys[0], row, _SEALED_GRADE)


def seal_pending(conn: psycopg.Connection, keys: tuple[str, ...], verifier: Any,
                 scenario: Scenario, client_id: str | None) -> list[str]:
    """Check again each grade the channels app recorded, by its sign-in, which covers every
    grade given with it, seal each, and let the sign-in go, in the gateway: or refuse them, so
    the samples wait to be graded again. Why each refused one was."""
    from a5s.core import sealing  # the check people's sign-ins share

    if not keys:
        return []  # they wait for a gateway that can seal them
    rows = conn.execute("select * from samples where scenario = %s and grade_proof is not null "
                        "and grade_seal is null order by id for update skip locked",
                        (scenario.name,)).fetchall()
    signed: dict[str, list[dict]] = {}
    for row in rows:
        signed.setdefault(row["grade_token"], []).append(row)
    refused = []
    for together in signed.values():
        first = together[0]
        given = {r["id"]: r["grade"] for r in conn.execute(
            "select id, grade from samples where grade_token = %s", (first["grade_token"],))}
        why = sealing.check(verifier, scenario, client_id, first["grade_proof"],
                            nonce(given, first["grade_salt"]), first["graded_by"])
        for row in together:
            if why is not None:
                conn.execute(
                    "update samples set grade = null, graded_by = null, graded_at = null, "
                    "grade_token = null, grade_nonce = null, grade_salt = null, grade_issuer = "
                    "null, grade_subject = null, grade_proof = null where id = %s", (row["id"],))
                refused.append(f"{row['graded_by']}'s grade of sample {row['id']}: {why}")
            else:
                conn.execute("update samples set grade_seal = %s, grade_proof = null where id = %s",
                             (seal(keys, row), row["id"]))
    return refused


def counted(keys: tuple[str, ...], row: dict) -> bool:
    """Whether a grade counts: one the core sealed."""
    return _sealed(keys, row, _SEALED_GRADE, row.get("grade_seal"))


# Weighing the grades

def assess(conn: psycopg.Connection, keys: tuple[str, ...], kind: str, part: str, action: str,
           threshold: float | None, now: datetime) -> dict | None:
    """Raise or lower a cap for a type of action in a part, if the grades given since it last
    changed now show it should: what changed, with the evidence, for the ledger. None if
    nothing did."""
    current = _cap_row(conn, keys, kind, part, action)
    now_cap, since = (current["cap"], current["since"]) if current else (1, None)
    rows = conn.execute(
        "select s.* from samples s join behaviours b on b.release = s.release "
        "and b.action = s.action where b.behaviour = %s and s.part = %s and s.action = %s "
        "and s.grade is not null order by s.graded_at", (kind, part, action)).fetchall()
    grades = [r for r in rows if counted(keys, r)]
    fresh = [g for g in grades if since is None or g["graded_at"] > since]
    graded, errors = len(fresh), sum(g["grade"] != "right" for g in fresh)
    evidence = {"graded": graded, "errors": errors, "threshold": threshold}
    if now_cap >= 2:
        if any(g["grade"] == "critical" for g in fresh):
            return set_cap(conn, keys, kind, part, action, 1, "a critical error", now, evidence,
                           threshold)
        if threshold is None:
            return set_cap(conn, keys, kind, part, action, 1, "the part has no threshold", now,
                           evidence)
        if (current["threshold"] or 0) < threshold:  # it rose: do the grades that earned it show it?
            earned = [g for g in grades if current["window_from"] is None
                      or g["graded_at"] > current["window_from"]]
            wrong = sum(g["grade"] != "right" for g in earned)
            if not shows(len(earned), wrong, threshold, "up"):
                return set_cap(conn, keys, kind, part, action, 1, "the part's threshold rose past "
                               "what its grades show", now,
                               {"graded": len(earned), "errors": wrong, "threshold": threshold},
                               threshold)
        if shows(graded, errors, threshold, "down"):
            return set_cap(conn, keys, kind, part, action, 1, "graded samples show it falls short",
                           now, evidence, threshold)
        return None
    if threshold is not None and shows(graded, errors, threshold, "up"):
        return set_cap(conn, keys, kind, part, action, 2, "graded samples show it meets the "
                       "threshold", now, evidence, threshold, window_from=since)
    return None


def lower(conn: psycopg.Connection, keys: tuple[str, ...], release: str, part: str, action: str,
          by: str, now: datetime) -> dict | None:
    """Lower a release's cap for a type of action in a part, at someone's word: never raise
    one. What changed, or None if it was 1 already."""
    kind = behaviour_of(conn, release, action)
    current = _cap_row(conn, keys, kind, part, action) if kind else None
    if current is None or current["cap"] < 2:
        return None
    return set_cap(conn, keys, kind, part, action, 1, f"lowered by {by}", now,
                   threshold=current["threshold"])


def lapse(conn: psycopg.Connection, now: datetime) -> int:
    """Samples nobody graded in a quarter lapse: they're no longer offered, and go a year
    after they were drawn. How many lapsed."""
    return conn.execute("update samples set lapsed_at = %s where grade is null and lapsed_at is "
                        "null and drawn_at < %s", (now, now - LAPSE)).rowcount


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
