"""Undoing a change an agent made (docs/agent-model.md#undoing-a-change). A tool that changes a
record can say how the change is reversed: by calling a tool of the scenario's, such as the same
one, with arguments from the change's own and from the record as it stood before it, for as long
as the tool says, a day unless it says otherwise, and a week at most (contract.Undo).

- When a5s makes such a change, at level 2 or once its deciders approve it, it keeps how to
  undo it: the call that reverses it, worked out then, and, read again just after, the fields
  it restores and every field the change itself altered, as the change left them.
- Whoever it was for, and whoever decides its type of change in the record's part, may undo it,
  so long as they may see the record, on its page in the studio, `/studio/undo?change=<id>`,
  signing in afresh for that act alone, as for deciding. a5s tells them how, and until when,
  itself: in its own note beside the agent's next message to them, for a change at level 2, as
  its link is a5s's, which no agent's message may carry, and in its own message for one its
  deciders approved. The channels app records it with the
  sign-in, and can undo nothing. The core checks the sign-in again, as it checks a decision,
  and whether they may now, and makes the call that reverses it, within a minute, but only
  while the record is as the change left it: one changed since is for whoever changed it to put
  right, in the records system, and a tool that changed since undoes nothing.
- An undone change counts against its agent's accuracy, as a wrong grade of it, which the core
  seals, whether or not it was drawn as a sample: so an agent whose changes people undo loses
  level 2 sooner, and earns it later (core/samples.py). A critical grade stays critical.
- The ledger records each undo and who asked for it, never what the record held. Whoever the
  change was for hears of it in their digest, as do the instance's owner and deputy, and the
  agent's next run knows, from their conversation.

What a5s keeps to undo a change goes a day after it can no longer be undone (core/retention.py).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import Person, Scenario, Tool
from a5s.core import acting, languages, ledger, proposals, words
from a5s.core.approvals import HASHED, Refused, afresh

PAGE = "/studio/undo"  # its page, as ?change=<id>, on the channels' address


def problems(tools: dict[str, Tool]) -> list[str]:
    """What's wrong with how a scenario's tools say they're undone: each undoes with a tool of
    the scenario's that changes the same type of thing, naming its record from the change's."""
    found = []
    for name, tool in sorted(tools.items()):
        undo = tool.undo
        if undo is None:
            continue
        by = tools.get(undo.tool)
        if by is None or not by.action or not by.record_arg:
            found.append(f"{name} is undone with {undo.tool}, which isn't a tool here that changes "
                         "a record")
            continue
        given = dict(undo.args)
        if given.get(by.record_arg) != f"args.{tool.record_arg}":
            found.append(f"{name} is undone with {undo.tool}, whose {by.record_arg} must name the "
                         f"record the change did, as args.{tool.record_arg}")
        if extra := sorted(set(given) - set(by.schema.get("properties") or {})):
            found.append(f"{name} is undone with {undo.tool}, which takes no {', '.join(extra)}")
        if missing := sorted(set(by.schema.get("required") or ()) - set(given)):
            found.append(f"{name} is undone with {undo.tool}, which needs {', '.join(missing)}")
        if unknown := sorted(s for s in given.values() if s.startswith("args.")
                             and s.removeprefix("args.") not in (tool.schema.get("properties") or {})):
            found.append(f"{name} takes no {', '.join(u.removeprefix('args.') for u in unknown)}, "
                         "which its undo names")
    return found


def planned(tool: Tool, given: dict[str, Any], before: dict | None) -> dict | None:
    """The call that reverses a change, worked out as it's made: its tool and arguments, from
    the change's own, as the tool was given them, and the record as it stood before. None if
    it can't be, such as for a record a5s couldn't read before."""
    undo = tool.undo
    if undo is None:
        return None
    fields = (before or {}).get("fields") if isinstance(before, dict) else None
    args: dict[str, Any] = {}
    for name, source in undo.args:
        kind, _, of = source.partition(".")
        if kind == "args":
            if of not in given:
                return None
            args[name] = given[of]
        else:
            if not isinstance(fields, dict) or of not in fields:
                return None
            args[name] = fields[of]
    return {"tool": undo.tool, "args": args}


def restores(tool: Tool) -> list[str]:
    """The fields of its record an undo puts back as they were."""
    return [s.removeprefix("before.") for _, s in (tool.undo.args if tool.undo else ())
            if s.startswith("before.")]


def left(tool: Tool, after: dict | None, before: dict | None = None) -> dict | None:
    """The fields the change left as they are, from the record read again just after it: those
    an undo restores, and every one the change itself altered, from the record as it stood
    before: what the record must still hold for the undo to be made, so an undo never puts back
    what someone has changed since, such as a question they closed."""
    fields = (after or {}).get("fields") if isinstance(after, dict) else None
    if not isinstance(fields, dict):
        return None
    was = (before or {}).get("fields") if isinstance(before, dict) else None
    altered = {f for f in fields if isinstance(was, dict) and was.get(f) != fields.get(f)}
    return {f: fields.get(f) for f in sorted({*restores(tool), *altered})}


def still(as_left: dict, now: dict | None) -> dict | None:
    """The fields a change left, as the record holds them now: the same as `as_left`, while
    nobody has changed them since. None if it can't be read."""
    fields = (now or {}).get("fields") if isinstance(now, dict) else None
    if not isinstance(fields, dict):
        return None
    return {f: fields.get(f) for f in as_left}


_SEALED = ("id", "run_id", "instance_id", "definition", "release", "tool", "schema_hash", "action",
           "record", "parts", "said", "undo", "as_left", "acts_for", "proposal_id", "until")


def _mac(key: str, row: dict) -> str:
    shown = {k: (v.astimezone(UTC).isoformat() if isinstance(v, datetime) else
                 str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items() if k in _SEALED}
    return hmac.new(key.encode(), ledger.canonical(shown).encode(), hashlib.sha256).hexdigest()


def seal_of(keys: tuple[str, ...], row: dict) -> str:
    """The core's seal over a change kept to undo, with the first of its keys."""
    return _mac(keys[0], row)


def intact(keys: tuple[str, ...], row: dict) -> bool:
    """Whether a change kept to undo is as the core kept it: its undo, how it left its record,
    whom it was for, until when (round 15, B1)."""
    return bool(keys) and bool(row.get("seal")) and any(
        hmac.compare_digest(_mac(k, row), row["seal"]) for k in keys)


def keep(conn: db.Connection, run: dict, tool: Tool, record: str, parts: list[str], said: str,
         undo: dict, as_left: dict, asked: list[str], proposal: int | None = None,
         offered: bool = False, keys: tuple[str, ...] = ()) -> dict:
    """Keep how to undo a change a5s has made, for as long as its tool says, and whether a5s
    has told whoever it was for how already, sealed with the core's key, so what's undone is
    what the core kept. Its row."""
    assert tool.undo is not None
    row = conn.execute(
        "insert into changes_made (run_id, instance_id, definition, release, tool, schema_hash, "
        "action, record, parts, said, undo, as_left, acts_for, proposal_id, until, offered_at) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now() + %s, "
        "case when %s then now() end) returning *",
        (run["run"], run["id"], run["definition"], run["release"], tool.name, tool.schema_hash,
         tool.action, record, parts, said.split("\n", 1)[0], Jsonb(undo), Jsonb(as_left),
         asked, proposal, tool.undo.within, offered)).fetchone()
    assert row is not None
    if keys:
        conn.execute("update changes_made set seal = %s where id = %s", (_mac(keys[0], row),
                                                                         row["id"]))
    return row


def link(public_url: str, change: int) -> str:
    return f"{public_url}{PAGE}?change={change}"


def offered(until: datetime, public_url: str, change: int, language: str = languages.ENGLISH,
            timezone: str = "UTC") -> str:
    """What whoever a change was for is told they can do, and until when, in the language they
    read and by their clock, which it names."""
    return words.say(language, "It can be undone until {until}, on its page: {link}",
                     until=languages.when(until, timezone),
                     link=link(public_url, change))


def for_agent(until: datetime) -> str:
    """What the agent that made a change at level 2 hears of undoing it: never the page's link,
    which is a5s's, and which its message can't carry, as a5s gives it them itself."""
    return (f"It can be undone until {until.strftime('%d %b %Y, %H:%M')} UTC, by whoever it was "
            "for, on its page. a5s tells them how itself, with the page's link, in its own note "
            "beside your next message to them: give no link yourself, as your message can't "
            "carry one of a5s's.")


# a5s's own note beside the agent's message to whoever a change at level 2 was for: its link is
# a5s's, which no agent's message may carry, so a5s writes it itself, once
OFFER = "(a5s: what the {agent} just changed can be undone until {until}, on its page: {link})"


def offers(conn: db.Connection, run: str, person: str, agent: str, public_url: str,
           language: str, timezone: str = "UTC") -> str:
    """a5s's note on how to undo each change at level 2 this run made for someone, which it
    hasn't told them of yet, in the language they read, in the caller's transaction: nothing,
    if none waits."""
    rows = conn.execute(
        "update changes_made set offered_at = now() where run_id = %s and %s = any(acts_for) "
        "and offered_at is null and state is null returning id, until", (run, person)).fetchall()
    return "\n".join(words.say(language, OFFER, agent=agent, link=link(public_url, r["id"]),
                               until=languages.when(r["until"], timezone))
                     for r in sorted(rows, key=lambda r: r["id"]))


# Who may, and asking

def nonce(change: int, salt: str) -> str:
    """What a sign-in to undo this change carries, so the provider's signature covers the act.
    The page picks the salt, so each sign-in is different."""
    bound = hashlib.sha256(f"a5s undo change {change} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


def may(scenario: Scenario, person: Person, change: dict, now_open: bool) -> str | None:
    """Why someone may not undo a change now, if they may not: it's theirs to undo if it was for
    them, or they decide its type of change in its record's part, and they may see the record,
    while it can still be undone (`now_open`), once."""
    if change["undone_at"] is not None:
        return "it's undone already"
    if change["asked_by"] is not None and change["state"] in ("asked", "undoing"):
        return "a5s is undoing it already, as someone asked"
    if not now_open:
        return "it can no longer be undone here: the time to undo it has passed"
    if not scenario.sees(person.id, change["record"]):
        return "you may not see its record"
    deciders = {p.id for ps in proposals.deciders(scenario, [change["record"]], []).values() for p in ps}
    if person.id not in change["acts_for"] and person.id not in deciders:
        return ("undoing it is for whoever it was for, and whoever decides changes like it in "
                "its record's part")
    return None


SHOWN = ("id, run_id, instance_id, definition, record, parts, said, acts_for, made_at, until, "
         "state, asked_by, asked_at, outcome, undone_at, undone_by")  # what the channels app reads


def found(conn: db.Connection, change: int) -> dict | None:
    """A change a5s keeps to undo, as the channels app may read it, with whether it can still
    be undone, by the database's clock."""
    return conn.execute(f"select {SHOWN}, until > now() as open from changes_made where id = %s",
                        (change,)).fetchone()


def shown(conn: db.Connection, scenario: Scenario, person: Person, change: int) -> dict | None:
    """A change as its page shows someone it's theirs to see: whoever it was for, and whoever
    may undo it, with why they may not, and how it ended, in the language they read (round 15,
    A12). None for anyone else, as if there were no such change."""
    row = found(conn, change)
    if row is None or not scenario.sees(person.id, row["record"]):
        return None
    why = may(scenario, person, row, bool(row["open"]))
    deciders = {p.id for ps in proposals.deciders(scenario, [row["record"]], []).values() for p in ps}
    if person.id not in row["acts_for"] and person.id not in deciders:
        return None
    named = [p.name if (p := scenario.person(w)) else w for w in row["acts_for"]]
    by = scenario.person(row["undone_by"] or row["asked_by"] or "")
    spoken = languages.of(person)
    return {"id": row["id"], "agent": row["definition"], "instance": row["instance_id"],
            "record": row["record"], "said": row["said"], "made_at": row["made_at"].isoformat(),
            "until": row["until"].isoformat(), "whom": named, "may": why is None,
            "why_not": words.say(spoken, why) if why else None, "state": row["state"] or "kept",
            "by": by.name if by else (row["undone_by"] or row["asked_by"]),
            "outcome": words.say(spoken, row["outcome"]) if row["outcome"] else None,
            **acting.shown(acting.undoing(person, scenario.part_of(row["record"]), spoken)
                           if why is None and person.id not in row["acts_for"] else None)}


def check(verifier: Any, scenario: Scenario, client_id: str, token: str, change: int, salt: str,
          now: float) -> tuple[Person, dict]:
    """Who signed in to undo this change, and what the provider signed, if the sign-in checks
    out for it alone, made afresh, with a second factor where the deployment asks for one.
    Otherwise, Refused. Whether they may is for `may`."""
    return afresh(verifier, scenario, client_id, token, nonce(change, salt), salt, now,
                  f"undo change {change}", "undo a change")


def record(conn: db.Connection, change: int, person: str, token: str, salt: str,
           claims: dict) -> dict:
    """Record someone asking to undo a change, with the sign-in that asked, for the core to check
    again and carry out, and the ledger that it was asked for. Refused if the sign-in was used
    before, or someone asked first."""
    hashed = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "update changes_made set state = 'asked', asked_by = %s, asked_at = now(), nonce = %s, "
        "salt = %s, token = %s, proof = %s, issuer = %s, subject = %s, outcome = null where "
        "id = %s and (state is null or state in ('refused', 'failed')) and undone_at is null "
        "and not exists (select 1 from changes_made c where c.token = %s) "
        "returning id, asked_at, instance_id, run_id",
        (person, claims["nonce"], salt, HASHED + hashed, token, claims["iss"],
         str(claims.get("sub") or ""), change, HASHED + hashed)).fetchone()
    if row is None:
        raise Refused(409, "someone has asked to undo it already, or that sign-in has been used: "
                           "look again in a minute")
    ledger.append(conn, {"kind": "admin", "action": "ask-undo", "run": str(row["run_id"]),
                         "instance": row["instance_id"], "acts_for": [person], "decision": "record",
                         "args": {"change": change, "asker": person, "issuer": claims["iss"],
                                  "token_sha256": hashed}})  # a stand-in, unlike `by` (round 15, E2)
    return dict(row)


def asked(conn: db.Connection) -> list[dict]:
    """In the core: each undo asked for that it hasn't checked yet, held while it does."""
    return conn.execute("select c.*, c.until > now() as open from changes_made c where "
                        "state = 'asked' order by asked_at for update skip locked").fetchall()


def end(conn: db.Connection, change: int, state: str, outcome: str, by: str | None = None) -> None:
    """End an undo asked for: undone, refused or failed, letting its sign-in go."""
    conn.execute("update changes_made set state = %s, outcome = %s, proof = null, "
                 "undone_at = case when %s = 'undone' then now() end, undone_by = %s "
                 "where id = %s", (state, outcome[:300], state, by if state == "undone" else None,
                                   change))
