"""Held proposals: a change to a part's data that an agent may not make alone.

Below level 2, policy holds a call to a tool that changes a part's data, rather than allowing
it (core/policy.py). The gateway keeps the exact call: its arguments as the agent wrote them,
the values of any handles in them, and each record it names, as it stood. The agent hears who
decides, and carries on.

The owners of the part the record is in decide it, never anyone the run acts for, and only
people who may see the record. Each gets a card, or a link in other chats, that opens the
core's page. There they see what the change does, in words code works out, with what they
should know, such as values the agent wrote itself. They decide it by signing in afresh at
the organisation's identity provider, with a nonce that commits to their decision on exactly
that change, or on a list of changes none of which is sensitive, so the provider's signature
covers the decision. The core seals each decision it checked, and each sign-in decides once.

Once a decider approves it, the gateway makes the call, if the records haven't changed since,
and the instance may still act; whoever the run acted for is told what was decided, and so
is the agent's next run. A decider whose authenticator was reset in the last day has their
decision wait until a day has passed. A change nobody decides reminds its deciders once,
after two working days, tells their managers after five, and lapses after ten.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import INSTANCE_APPROVER, PART_OWNER, Person, Record, Scenario, Tool, record_of
from a5s.core import approvals
from a5s.core.handles import TOKEN
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, whose
from a5s.core.ledger import canonical
from a5s.core.obligations import a_working_day_after

REMIND, ESCALATE, LAPSE = 2, 5, 10  # working days: remind its deciders, tell their managers, lapse [TBC]
AFTER_RESET = timedelta(days=1)  # how long a decision waits after its decider's authenticator was reset
DECISIONS = ("approve", "reject")
_SEALED = ("scenario", "digest", "decision", "person", "nonce", "salt", "issuer", "subject")


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def key(proposal: dict) -> str:
    """How people name a proposal, such as P-12."""
    return f"P-{proposal['id']}"


def fingerprint(record: Record | None) -> str:
    """A digest of a record as it stands, to tell whether it's changed since."""
    if record is None:
        return "none"
    shown = {"key": record.key, "person": record.person, "title": record.title,
             "fields": record.fields, "link": record.link}
    return hashlib.sha256(canonical(shown).encode()).hexdigest()


def deciders(scenario: Scenario, records: list[str], acts_for: list[str]) -> list[Person]:
    """Who may decide a change to these records: the owners of their parts, or the instance
    approvers for a record in none, who may see them all, and never anyone the run acts for."""
    parts = {scenario.part_of(r) for r in records} or {None}
    roles = [f"{PART_OWNER}:{p}" if p else INSTANCE_APPROVER for p in sorted(parts, key=str)]
    found: dict[str, Person] = {}
    for role in dict.fromkeys(roles):
        for person in scenario.holders(role):
            if (person.id not in acts_for and person.id not in found
                    and all(scenario.sees(person.id, r) for r in records)):
                found[person.id] = person
    return list(found.values())


def working_days_after(person: Person, at: datetime, days: int) -> datetime:
    for _ in range(days):
        at = a_working_day_after(person, at)
    return at


def said(scenario: Scenario, tool: Tool, args: dict, records: dict[str, Record | None],
         acts_for: list[str], agent: str) -> str:
    """What a change does, in words code works out from the tool and the call, for its
    deciders: never the agent's own account of it."""
    named = [k for k in records]
    shown = ", ".join(f"{k} {_plain(v)}" for k, v in args.items() if k != tool.record_arg)
    lines = [f"{tool.description.rstrip('.')}: {', '.join(named) or 'no record'}"
             + (f", with {shown}" if shown else "") + "."]
    for k, record in records.items():
        if record is not None:
            facts = ", ".join(f"{name} {value}" for name, value in record.fields.items())
            lines.append(f"{k}, {record.title}, as it stands: {facts}.")
    people = [p.name if (p := scenario.person(who)) else who for who in acts_for]
    lines.append(f"The {agent} asked for it" + (f", for {approvals.names_of(people)}" if people
                                                 else ", for nobody in particular") + ".")
    return "\n".join(lines)


def _plain(value: Any) -> str:
    return value if isinstance(value, str) else canonical(value)


def handles_in(args: Any) -> set[str]:
    """The handles an agent wrote in a call, at any depth."""
    if isinstance(args, str):
        return set(TOKEN.findall(args))
    if isinstance(args, list):
        return set().union(*(handles_in(a) for a in args)) if args else set()
    if isinstance(args, dict):
        return set().union(*(handles_in(a) for a in args.values())) if args else set()
    return set()


def resolved(args: Any, values: dict[str, str]) -> Any:
    """A held call's arguments with its handles put back, at any depth, from what it kept."""
    if isinstance(args, str):
        return TOKEN.sub(lambda m: values.get(m.group(1), m.group(0)), args)
    if isinstance(args, list):
        return [resolved(a, values) for a in args]
    if isinstance(args, dict):
        return {k: resolved(v, values) for k, v in args.items()}
    return args


def waiting(conn: psycopg.Connection, run: str, change: str) -> dict | None:
    """The same change, held already in the same run and still waiting: the call made again."""
    return conn.execute("select * from proposals where run_id = %s and change = %s "
                        "and status = 'waiting'", (run, change)).fetchone()


def hold(conn: psycopg.Connection, scenario: Scenario, run: dict, tool: Tool, args: dict,
         records: list[str], who: list[Person], seq: int, flags: list[str], now: datetime,
         change: str | None = None) -> dict:
    """Keep a held call for its deciders, in the transaction that decided it."""
    standing = {r: record_of(scenario, r) for r in records}
    first = who[0]
    sensitive = tool.destructive or tool.sends_outside
    body = {"scenario": scenario.name, "run": run["run"], "instance": run["id"], "tool": tool.name,
            "args": args, "records": {r: fingerprint(v) for r, v in standing.items()},
            "nonce": secrets.token_hex(16)}  # each proposal is its own, even for the same call
    row = conn.execute(
        "insert into proposals (scenario, digest, run_id, instance_id, definition, release, tool, "
        "schema_hash, action, args, records, parts, acts_for, deciders, said, flags, sensitive, "
        "read_outside, seq, proposed_at, lapses_at, change) values (%s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (scenario.name, hashlib.sha256(canonical(body).encode()).hexdigest(), run["run"], run["id"],
         run["definition"], run["release"], tool.name, tool.schema_hash, tool.action, Jsonb(args),
         Jsonb(body["records"]), sorted({p for r in records if (p := scenario.part_of(r))}),
         list(run["acts_for"]), [p.id for p in who],
         said(scenario, tool, args, standing, list(run["acts_for"]), run["definition"]),
         Jsonb(flags), sensitive, bool(run["read_outside"]), seq, now,
         working_days_after(first, now, LAPSE), change)).fetchone()
    for handle in sorted(handles_in(args)):  # the values it stands for, kept until it's decided
        conn.execute("insert into proposal_values (proposal_id, handle, value) "
                     "select %s, handle, value from run_handles where run_id = %s and handle = %s",
                     (row["id"], run["run"], handle))
    return row


def unchanged(scenario: Scenario, proposal: dict) -> list[str]:
    """The records a held change names that have changed since it was held."""
    return [r for r, was in proposal["records"].items()
            if fingerprint(record_of(scenario, r)) != was]


def values(conn: psycopg.Connection, proposal: dict) -> dict[str, str]:
    return {r["handle"]: r["value"] for r in conn.execute(
        "select handle, value from proposal_values where proposal_id = %s", (proposal["id"],))}


# Deciding: signed through the identity provider for that one decision, and sealed by the core

def nonce(digests: list[str], decision: str, salt: str) -> str:
    """What a sign-in to decide carries, so the provider's signature covers the decision on
    exactly these changes. The page picks the salt, so each sign-in is different."""
    bound = hashlib.sha256(
        f"a5s {decision}s proposals {','.join(sorted(digests))} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


def check(verifier: Verifier, scenario: Scenario, client_id: str, token: str, digests: list[str],
          decision: str, salt: str, now: float) -> tuple[Person, dict]:
    """Who signed in to make this decision on these changes, and what the provider signed, if
    the sign-in checks out for it. Otherwise, Refused."""
    if decision not in DECISIONS:
        raise Refused(400, "a change is approved or rejected")
    try:
        claims = verifier.claims(token)
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    audience = claims.get("aud")
    if client_id not in ([audience] if isinstance(audience, str) else audience or []):
        raise Refused(401, "that sign-in is for something else")
    if not 16 <= len(salt) <= 128 or claims.get("nonce") != nonce(digests, decision, salt):
        raise Refused(403, f"your sign-in wasn't to {decision} these changes")
    if not isinstance(claims.get("auth_time"), int | float) or any(
            not isinstance(claims.get(c), int | float) or now - claims[c] > approvals.FRESH
            for c in ("iat", "auth_time")):  # a session's silent sign-in decides nothing
        raise Refused(401, "deciding needs you to sign in again, from the last ten minutes, "
                           "not a sign-in your browser kept")
    try:
        person = whose(verifier, scenario, claims)
    except UnknownPerson as exc:
        raise Refused(403, str(exc)) from None
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    return person, claims


def may_decide(scenario: Scenario, proposal: dict, person: str) -> bool:
    """Whether someone may decide a held change now: one of its deciders, still owning what
    it touches, never anyone it was for, and able to see its records."""
    now = {p.id for p in deciders(scenario, list(proposal["records"]), list(proposal["acts_for"]))}
    return person in proposal["deciders"] and person in now


def record(conn: psycopg.Connection, keys: tuple[str, ...], scenario: str, found: list[dict],
           decision: str, person: str, token: str, salt: str, claims: dict,
           now: datetime) -> list[dict]:
    """Record a decision on each of these changes, sealed. Refused if the sign-in was used, or
    the person has decided one of them already."""
    made = []
    for proposal in found:
        entry = {"scenario": scenario, "digest": proposal["digest"], "decision": decision,
                 "person": person, "nonce": claims["nonce"], "salt": salt,
                 "issuer": claims["iss"], "subject": str(claims.get("sub") or ""),
                 "token": approvals.HASHED + hashlib.sha256(token.encode()).hexdigest(),
                 "decided_at": now}  # by the core's clock, as everything that falls due is
        entry["seal"] = _mac(keys[0], entry)
        row = conn.execute(
            "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, salt, "
            "issuer, subject, seal, decided_at) values (%(scenario)s, %(digest)s, %(decision)s, "
            "%(person)s, %(token)s, %(nonce)s, %(salt)s, %(issuer)s, %(subject)s, %(seal)s, "
            "%(decided_at)s) on conflict do nothing returning id", entry).fetchone()
        if row is None:
            raise Refused(409, f"{key(proposal)} has been decided with that sign-in, or by you, "
                               "already")
        made.append({**entry, **row})
    return made


def sealed(keys: tuple[str, ...], entry: dict) -> bool:
    return bool(keys) and any(hmac.compare_digest(_mac(k, entry), entry["seal"]) for k in keys)


def _mac(key: str, entry: dict) -> str:
    fields = {k: entry[k] for k in _SEALED}
    fields["token"] = entry["token"].removeprefix(approvals.HASHED)
    return hmac.new(key.encode(), canonical(fields).encode(), hashlib.sha256).hexdigest()


def decision(conn: psycopg.Connection, keys: tuple[str, ...], scenario: Scenario,
             proposal: dict) -> tuple[dict | None, list[str]]:
    """The decision that counts on a held change: the first the core sealed, by someone who may
    decide it now. And what's wrong with any other."""
    problems = []
    for row in conn.execute("select * from proposal_decisions where digest = %s order by id",
                            (proposal["digest"],)):
        if not sealed(keys, row):
            problems.append(f"{row['person']}'s decision isn't one the core sealed")
        elif not may_decide(scenario, proposal, row["person"]):
            problems.append(f"{row['person']} may not decide it now")
        else:
            return row, problems
    return None, problems


def effective(person: Person | None, decided_at: datetime) -> datetime:
    """When a decision takes effect: at once, or a day after its decider's authenticator was
    reset, if that was less than a day before."""
    reset = person.reset_at if person else None
    if reset is not None and reset <= decided_at < reset + AFTER_RESET:
        return reset + AFTER_RESET
    return decided_at


# What a5s says about a held change, in its own words

def first(proposal: dict) -> str:
    """The change, in one line, such as for telling whoever it was for."""
    return proposal["said"].split("\n", 1)[0]


def asking(proposal: dict, link: str) -> str:
    """The message asking a decider to decide a held change, for chats without cards."""
    flags = "".join(f"\n- {f}" for f in proposal["flags"])
    return (f"{key(proposal)} waits for your decision.\n{proposal['said']}"
            + (f"\nWhat to know:{flags}" if flags else "")
            + f"\nDecide it on a5s's page, and approve it only if you mean it: {link}")


def card(proposal: dict, link: str) -> dict:
    """The card a decider gets in Teams. It only opens the core's page, where they decide."""
    body = [{"type": "TextBlock", "text": f"{key(proposal)}: a change to decide", "weight": "Bolder",
             "size": "Medium", "wrap": True},
            {"type": "TextBlock", "wrap": True, "text": proposal["said"]}]
    if proposal["flags"]:
        body.append({"type": "TextBlock", "wrap": True, "text": "What to know:\n"
                     + "\n".join(f"- {f}" for f in proposal["flags"])})
    body.append({"type": "TextBlock", "wrap": True, "isSubtle": True, "size": "Small",
                 "text": "You decide on a5s's page, after signing in again. Telling an agent "
                         "decides nothing."})
    return {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4", "body": body,
            "actions": [{"type": "Action.OpenUrl", "title": "Review and decide", "url": link}]}


def told(proposal: dict, became: str, by: str | None = None, extra: str = "") -> str:
    """What a5s tells whoever a held change was for, once something became of it."""
    change = first(proposal)
    return {
        "made": f"{by} approved {key(proposal)}, and a5s has made it: {change}",
        "rejected": f"{by} didn't approve {key(proposal)}, so a5s didn't make it: {change}",
        "lapsed": (f"Nobody decided {key(proposal)} within {LAPSE} working days, so a5s let it "
                   f"go: {change} Ask again if it's still needed."),
        "changed": (f"{by} approved {key(proposal)}, but a5s didn't make it, since {extra} "
                    f"changed after it was asked for: {change} Ask again if it's still needed."),
        "refused": f"{by} approved {key(proposal)}, but a5s couldn't make it, since {extra}: {change}",
        "failed": (f"{by} approved {key(proposal)}, but the records system didn't take it "
                   f"({extra}): {change}"),
    }[became]
