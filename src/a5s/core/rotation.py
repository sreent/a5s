"""Rotating the core's seal key (docs/runbooks.md#rotating-the-seal-key; round 15, D2).

The core seals what it checked with the first of A5S_SEAL_KEYS, and takes a seal made with any
of them. To rotate the key, an operator puts a new one first, keeps the old one after it,
restarts the core and runs `a5s seal-again`: what the old key sealed that still checks out is
sealed again with the new one, and the old key is retired, to be dropped.

The core remembers each key it starts with by a fingerprint, never the key, and won't start
without one it hasn't retired: what that key sealed would stop counting unsaid, the approvals of
the settings in force among it, so every run would be refused and level 2 lost. What checks out
under no key, such as a row someone wrote into the database, stays as it is and counts for
nothing, now as before.

A key that leaked is another matter: whoever holds it could have sealed what nobody approved,
and sealing that again would make it count. `a5s seal-again --leaked` retires every key after
the first without sealing anything again, and says what stops counting with them: the settings
must be approved again, caps earn level 2 again from graded samples, and people connect their
accounts again. A key retired as leaked never comes back: the core won't start with it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, LiteralString

from a5s import db
from a5s.core import approvals, delegation, proposals, samples, undoing

RUNBOOK = "docs/runbooks.md#rotating-the-seal-key"

Check = Callable[[tuple[str, ...], dict], bool]
Again = Callable[[db.Connection, tuple[str, ...], dict], None]


class Refused(RuntimeError):
    """What the core's start, or `a5s seal-again`, won't do, and why."""


def fingerprint(key: str) -> str:
    """What a5s keeps of a seal key: enough to know it again, nothing to make it from."""
    return hashlib.sha256(b"a5s seal key\n" + key.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Kind:
    """Something the core seals: its sealed rows, whether one checks out only under a key after
    the first, and sealing it again with the first."""
    name: str
    rows: LiteralString
    older: Check
    again: Again


def _older(check: Check) -> Check:
    return lambda keys, row: not check(keys[:1], row) and check(keys[1:], row)


def _approval_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    conn.execute("update settings_approvals set seal = %s where id = %s",
                 (approvals.seal(keys, row), row["id"]))


def _version(keys: tuple[str, ...], row: dict) -> bool:
    return approvals.vouched(keys, row["scenario"], row["serial"], bytes(row["raw"] or b""),
                             row["sealed"])


def _version_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    conn.execute("update settings_versions set sealed = %s where scenario = %s and serial = %s",
                 (approvals.vouch(keys, row["scenario"], row["serial"], bytes(row["raw"] or b"")),
                  row["scenario"], row["serial"]))


def _decision_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    conn.execute("update proposal_decisions set seal = %s where id = %s",
                 (proposals.seal_of(keys, row), row["id"]))


def _cap_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    conn.execute("update caps set seal = %s where behaviour = %s and part = %s and action = %s",
                 (samples.cap_seal(keys, row), row["behaviour"], row["part"], row["action"]))


def _sample_older(keys: tuple[str, ...], row: dict) -> bool:
    """A sample the core drew, or a grade it sealed, under a key after the first alone."""
    first, later = keys[:1], keys[1:]
    drawn = not samples.drawn_by_core(first, row) and samples.drawn_by_core(later, row)
    graded = not samples.grade_sealed(first, row) and samples.grade_sealed(later, row)
    return drawn or graded


def _sample_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    """A sample's draw, and its grade, whose seal holds the draw's, sealed with the first key."""
    fresh = dict(row)
    if samples.drawn_by_core(keys, row) and not samples.drawn_by_core(keys[:1], row):
        fresh["drawn_seal"] = samples.draw_seal(keys, row)
        conn.execute("update samples set drawn_seal = %s where id = %s",
                     (fresh["drawn_seal"], row["id"]))
    if samples.grade_sealed(keys, row) and (fresh["drawn_seal"] != row["drawn_seal"]
                                            or not samples.grade_sealed(keys[:1], row)):
        conn.execute("update samples set grade_seal = %s where id = %s",
                     (samples.seal(keys, fresh), row["id"]))


def _undo_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    conn.execute("update changes_made set seal = %s where id = %s",
                 (undoing.seal_of(keys, row), row["id"]))


def _tokens(keys: tuple[str, ...], row: dict) -> bool:
    try:
        delegation.unseal(keys, row["person"], row["system"], bytes(row["sealed"]))
    except delegation.NotConnected:
        return False
    return True


def _tokens_again(conn: db.Connection, keys: tuple[str, ...], row: dict) -> None:
    tokens = delegation.unseal(keys, row["person"], row["system"], bytes(row["sealed"]))
    conn.execute("update delegations set sealed = %s where person = %s and system = %s",
                 (delegation.seal(keys, row["person"], row["system"], tokens), row["person"],
                  row["system"]))


KINDS = (
    Kind("approvals of the settings", "select * from settings_approvals where seal is not null",
         _older(approvals.sealed), _approval_again),
    Kind("versions of the settings", "select scenario, serial, raw, sealed from settings_versions "
         "where sealed is not null", _older(_version), _version_again),
    Kind("decisions on held changes", "select * from proposal_decisions where seal is not null",
         _older(proposals.sealed), _decision_again),
    Kind("caps", "select * from caps where seal is not null", _older(samples.cap_sealed),
         _cap_again),
    Kind("samples and their grades", "select * from samples where drawn_seal is not null or "
         "grade_seal is not null", _sample_older, _sample_again),
    Kind("changes kept to undo", "select * from changes_made where seal is not null",
         _older(undoing.intact), _undo_again),
    Kind("connected accounts", "select person, system, sealed from delegations", _older(_tokens),
         _tokens_again),
)


def waiting(conn: db.Connection, keys: tuple[str, ...]) -> dict[str, int]:
    """Of each kind the core seals, how many check out only under a key after the first: what
    `a5s seal-again` would seal again. Nothing, while the core holds one key."""
    if len(keys) < 2:
        return {}
    found: dict[str, int] = {}
    for kind in KINDS:
        if count := sum(1 for row in conn.execute(kind.rows).fetchall() if kind.older(keys, row)):
            found[kind.name] = count
    return found


def started(conn: db.Connection, keys: tuple[str, ...]) -> None:
    """Remember the keys the core starts with, and that it seals with the first: refused, so it
    won't start, without a key it held that isn't retired, or with one retired as leaked."""
    if not keys:
        return
    prints = [fingerprint(k) for k in keys]
    back = [r["fingerprint"] for r in conn.execute(
        "select fingerprint from seal_keys where leaked and fingerprint = any(%s)", (prints,))]
    if back:
        raise Refused(f"A5S_SEAL_KEYS holds a key retired as leaked ({', '.join(back)}): take "
                      f"it out, and start the core without it ({RUNBOOK})")
    for found in prints:
        conn.execute("insert into seal_keys (fingerprint) values (%s) on conflict do nothing",
                     (found,))
    conn.execute("update seal_keys set retired_at = null where fingerprint = %s", (prints[0],))
    missing = [r["fingerprint"] for r in conn.execute(
        "select fingerprint from seal_keys where retired_at is null and not (fingerprint = "
        "any(%s)) order by first_seen", (prints,))]
    if missing:
        raise Refused(
            f"A5S_SEAL_KEYS no longer holds a key the core sealed with ({', '.join(missing)}), "
            "so what it sealed would stop counting, the approvals of the settings in force "
            "among it: put it back after the first, start the core, run `a5s seal-again`, and "
            f"drop it once that retires it ({RUNBOOK})")
    conn.execute("update seal_keys set sealing_since = case when fingerprint = %s then "
                 "coalesce(sealing_since, now()) end", (prints[0],))


def again(conn: db.Connection, keys: tuple[str, ...], *, leaked: bool = False) -> dict[str, Any]:
    """Seal again with the first key what checks out only under the others, and retire them;
    or, for a key that leaked, retire them at once, sealing nothing again. What was sealed
    again, what stopped counting, and the keys retired, by fingerprint."""
    first = conn.execute("select sealing_since from seal_keys where fingerprint = %s",
                         (fingerprint(keys[0]),)).fetchone()
    if first is None or first["sealing_since"] is None:
        raise Refused("the core at work doesn't seal with the first of these keys: start it with "
                      f"this A5S_SEAL_KEYS first, then run this again ({RUNBOOK})")
    later = [fingerprint(k) for k in keys[1:]]
    sealed: dict[str, int] = {}
    stopped = waiting(conn, keys) if leaked else {}
    for kind in () if leaked else KINDS:
        for row in conn.execute(kind.rows + " for update").fetchall():
            if kind.older(keys, row):
                kind.again(conn, keys, row)
                sealed[kind.name] = sealed.get(kind.name, 0) + 1
    conn.execute("update seal_keys set retired_at = now(), sealing_since = null, leaked = "
                 "leaked or %s where fingerprint = any(%s)", (leaked, later))
    return {"leaked": leaked, "sealed": sealed, "stopped": stopped, "retired": later}


def told(done: dict[str, Any]) -> str:
    """What `a5s seal-again` did, in words."""
    if not done["retired"]:
        return "A5S_SEAL_KEYS holds one key: there's nothing to seal again, and no key to retire."

    def counted(found: dict[str, int]) -> str:
        return "; ".join(f"{kind}, {n}" for kind, n in found.items()) or "nothing"

    retired = ", ".join(done["retired"])
    said = (f"Retired as leaked, sealing nothing again: {retired}. These stop counting: "
            f"{counted(done['stopped'])}." if done["leaked"] else
            f"Sealed again with the first key: {counted(done['sealed'])}. Retired: {retired}.")
    return (f"{said}\nDrop what's retired from A5S_SEAL_KEYS, keeping the first, and restart "
            f"the core ({RUNBOOK}).")
