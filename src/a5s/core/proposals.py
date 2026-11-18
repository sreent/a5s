"""Held proposals: a change to a part's data that an agent may not make alone.

Below level 2, policy holds a call to a tool that changes a part's data, rather than allowing
it (core/policy.py). The gateway keeps the exact call: its arguments as the agent wrote them,
the values of any handles in them, and each record it names, as it stood. The agent hears who
decides, and carries on. The same change asked for again, in any run for the same people,
while it waits, is answered with the change that waits.

The owners of each part its records are in decide it, with anyone they name to decide
beside them, or the instance approvers for a record in no part: never anyone the run acts
for, and only people who may see every record it names. A change in two parts needs an
approval for each. Who may decide is worked out afresh whenever it's shown, decided or
chased, so a part's new owner decides what waits there. Each decider is asked where they
work with the agent, as an urgent message, so a flood of changes can't flood them. On the
core's page they see what the change does, in words code works out, with the values it
writes, a link to each record, whether it has changed since, and what they should know, such
as values the agent wrote itself or read in a customer's email. They decide it by signing in
afresh at the organisation's identity provider, with a nonce that commits to their decision
on exactly that change, or on a list of changes none of which is sensitive, so the
provider's signature covers the decision. A rejection may say why. The core seals each
decision it checked, and each sign-in decides once.

Once every part approves it, the gateway makes the call, if the records haven't changed
since, and the instance may still act; whoever the run acted for is told what was decided,
and so is the agent's next run, and so is everyone who decided it. A decider whose
authenticator was reset in the last day has their approval wait until a day has passed. A
change nobody decides reminds each of its deciders once, in their own working hours, after
two working days, then tells their managers, or the instance's owner, after five, and lapses
after ten.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import (
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    Person,
    Record,
    Scenario,
    Tool,
    record_of,
)
from a5s.core import approvals, languages, outgoing, sealing, words
from a5s.core.handles import TOKEN
from a5s.core.identity import Verifier
from a5s.core.ledger import canonical
from a5s.core.obligations import a_working_day_after
from a5s.core.words import kept, say

REMIND, ESCALATE, LAPSE = 2, 5, 10  # working days: remind its deciders, tell their managers, lapse [starting value]
AFTER_RESET = timedelta(days=1)  # how long a decision waits after its decider's authenticator was reset
DECISIONS = ("approve", "reject")
_SEALED = ("scenario", "digest", "decision", "person", "nonce", "salt", "issuer", "subject",
           "reason")
REASON = 300  # characters a rejection may give for itself
MOST_DECIDED = 20  # changes one sign-in decides, at most


class Refused(Exception):
    def __init__(self, status: int, reason: str, second_factor: str | None = None):
        super().__init__(reason)
        self.status, self.reason = status, reason
        self.second_factor = second_factor  # what was refused for want of one, to count it


def key(proposal: dict) -> str:
    """How people name a proposal, such as P-12."""
    return f"P-{proposal['id']}"


def roles(part: str | None) -> list[str]:
    """Who decides the changes in a part: its owners and their delegates. In none, the
    instance approvers."""
    return [f"{PART_OWNER}:{part}", f"{PART_DELEGATE}:{part}"] if part else [INSTANCE_APPROVER]


def deciders(scenario: Scenario, records: list[str],
             acts_for: list[str]) -> dict[str | None, list[Person]]:
    """Who may decide a change to these records, for each part they're in: its owners and
    delegates, or the instance approvers for records in none. Never anyone the run acts for,
    and only people who may see every record the change names. A part nobody may decide for
    has nobody."""
    found: dict[str | None, list[Person]] = {}
    for part in sorted({scenario.part_of(r) for r in records} or {None}, key=str):
        people: dict[str, Person] = {}
        for role in roles(part):
            for person in scenario.holders(role):
                if (person.id not in acts_for and person.id not in people
                        and all(scenario.sees(person.id, r) for r in records)):
                    people[person.id] = person
        found[part] = list(people.values())
    return found


def everyone(by_part: dict[str | None, list[Person]]) -> list[Person]:
    """Each person who may decide for any part, once."""
    return list({p.id: p for people in by_part.values() for p in people}.values())


def undecidable(by_part: dict[str | None, list[Person]]) -> list[str]:
    """The parts nobody may decide a change for, by name."""
    return [part or "no part" for part, people in by_part.items() if not people]


def working_days_after(person: Person, at: datetime, days: int) -> datetime:
    for _ in range(days):
        at = a_working_day_after(person, at)
    return at


# What a held change's deciders, and its sample's graders, are told to know of it, as words a5s
# keeps, so each reads them in the language they read (core/gateway.py's held; round 15, B6)
OWN_VALUE = "{value} came from the {agent} itself, not from the records or from {whom}"
TEAM_VALUE = ("{value} came from what {who} of a team answered them while the conversation was "
              "handed over, not from the records or from {whom}")
SOMEONE_VALUE = ("{value} came from what someone of a team answered them while the conversation "
                 "was handed over, not from the records or from {whom}")
OUTSIDE_VALUE = ("{value} came from a document from outside the organisation ({document}), such "
                 "as a customer's email, not from the records")
READ_OUTSIDE = "the {agent} read content from outside the organisation before it asked for this"
UNASKED = "nobody asked for it: the {agent} asked for it {after}"
UNASKED_ABOUT = "nobody asked for it: the {agent} asked for it {after}, about {whom}"
AFTER_EVENT = "after {source} said {type} happened"
OVER = "it waits because {over}"
# and of a change, and of its words, beside them
CHANGED = "{key} has changed since it was asked for"
SEALED = ("The change and its records are in their system's words, which a5s seals with your "
          "decision.")


def after_kept(trigger: dict | None) -> dict | None:
    """What a run nobody asked for came after, as words a5s keeps, if another system's event
    started it: its system and type, as a5s received it."""
    found = trigger or {}
    if found.get("kind") != "event":
        return None
    return kept(AFTER_EVENT, source=str(found.get("source")), type=str(found.get("type")))


def after(trigger: dict | None) -> str:
    """The same, in words."""
    found = after_kept(trigger)
    return say(languages.ENGLISH, AFTER_EVENT, **found["given"]) if found else ""


def said(scenario: Scenario, tool: Tool, args: dict, records: dict[str, dict | None],
         acts_for: list[str], agent: str, values: dict[str, str] | None = None,
         trigger: dict | None = None) -> str:
    """What a change does, in words code works out from the tool and the call, with the values
    its handles stand for, and each record as it stood when it was asked for, from a snapshot
    (samples.snapshot): never the agent's own account of it. One a run nobody asked for asked
    for, such as an event's, says so, rather than that it was for the person it's about."""
    named = [k for k in records]
    shown = ", ".join(f"{k} {_plain(v, scenario.record_links)}" for k, v in args.items()
                      if k != tool.record_arg)
    lines = [resolved(f"{tool.description.rstrip('.')}: {', '.join(named) or 'no record'}"
                      + (f", with {shown}" if shown else "") + ".", values or {})]
    lines += stood(records)
    people = [p.name if (p := scenario.person(who)) else who for who in acts_for]
    if came := after(trigger):
        lines.append(f"The {agent} asked for it {came}" + (
            f", about {approvals.names_of(people)}" if people else "") + ": nobody asked it to.")
    else:
        lines.append(f"The {agent} asked for it" + (f", for {approvals.names_of(people)}"
                                                     if people else ", for nobody in particular")
                     + ".")
    return "\n".join(lines)


def stood(records: dict[str, dict | None]) -> list[str]:
    """Each record as it stood, from a snapshot, with its link."""
    lines = []
    for k, record in records.items():
        if record is not None:
            facts = ", ".join(f"{name} {value}" for name, value in record["fields"].items())
            lines.append(f"{k}, {record['title']}, as it stood when it was asked for: {facts}."
                         + (f" {record['link']}" if record.get("link") else ""))
    return lines


def _plain(value: Any, allowed: tuple[str, ...] = ()) -> str:
    """A value as a held change shows it: plain words on one line, cleaned as outgoing text is,
    never a link, or a note that reads as a5s's (core/outgoing.py, round 15, F2)."""
    return outgoing.plain(value if isinstance(value, str) else canonical(value), allowed)


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


def waiting(conn: db.Connection, run: dict, change: str) -> dict | None:
    """The same change, for the same people, from the same instance, still waiting: the call
    made again, in its run or another."""
    return conn.execute("select * from proposals where instance_id = %s and change = %s "
                        "and acts_for = %s and status = 'waiting' order by id limit 1",
                        (run["id"], change, list(run["acts_for"]))).fetchone()


def sensitive(conn: db.Connection, run: str, tool: Tool, args: dict,
              classified: dict[str, str]) -> bool:
    """Whether a change is decided on its own: one that can't be undone, sends outside, or
    writes a value of a class of data the settings name, which it carries as a handle."""
    if tool.destructive or tool.sends_outside:
        return True
    found = sorted(handles_in(args))
    return bool(found) and any(r["field"] in classified for r in conn.execute(
        "select field from run_handles where run_id = %s and handle = any(%s)", (run, found)))


def not_deciding(proposal: dict) -> list[str]:
    """Who decides nothing of a held change: whom it's for, and whose answers, from a team that
    took their conversation, its run was given, which may have asked for it."""
    return [*proposal["acts_for"], *(proposal.get("steered_by") or [])]


def hold(conn: db.Connection, scenario: Scenario, run: dict, tool: Tool, args: dict,
         standing: dict[str, dict | None], who: list[Person], seq: int, flags: list[str],
         now: datetime, change: str | None, is_sensitive: bool,
         steered: list[str] | None = None, flagged: list[dict] | None = None) -> dict:
    """Keep a held call for its deciders, in the transaction that decided it, with its records
    as they stood, read before it began, and `steered`, whose answers from a team its run was
    given, who decide nothing of it either."""
    found = sorted(handles_in(args))
    kept = {r["handle"]: r["value"] for r in conn.execute(
        "select handle, value from run_handles where run_id = %s and handle = any(%s)",
        (run["run"], found))} if found else {}
    first = who[0]
    words = said(scenario, tool, args, standing, list(run["acts_for"]), run["definition"], kept,
                 run.get("trigger"))
    body = bound(scenario.name, run["run"], run["id"], tool.name, tool.schema_hash, tool.action,
                 args, {r: fingerprint_of(v) for r, v in standing.items()}, kept,
                 list(run["acts_for"]), words, secrets.token_hex(16))  # its own, even for the
    row = conn.execute(  # same call
        "insert into proposals (scenario, digest, run_id, instance_id, definition, release, tool, "
        "schema_hash, action, args, records, parts, acts_for, deciders, said, flags, sensitive, "
        "read_outside, seq, proposed_at, lapses_at, change, remind_at, escalate_at, standing, "
        "steered_by, nonce, flagged) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (scenario.name, hashlib.sha256(canonical(body).encode()).hexdigest(), run["run"], run["id"],
         run["definition"], run["release"], tool.name, tool.schema_hash, tool.action, Jsonb(args),
         Jsonb(body["records"]), sorted({p for r in standing if (p := scenario.part_of(r))}),
         list(run["acts_for"]), [p.id for p in who], words,
         Jsonb(flags), is_sensitive, bool(run["read_outside"]), seq, now,
         working_days_after(first, now, LAPSE), change,
         working_days_after(first, now, REMIND), working_days_after(first, now, ESCALATE),
         Jsonb(standing), sorted(set(steered or ())), body["nonce"],
         Jsonb(flagged) if flagged is not None else None)).fetchone()
    for handle, value in kept.items():  # the values they stand for, kept until it's decided
        conn.execute("insert into proposal_values (proposal_id, handle, value) values (%s, %s, %s)",
                     (row["id"], handle, value))
    return row


def bound(scenario: str, run: str, instance: str, tool: str, schema_hash: str,
          action: str | None, args: Any, records: dict, values: dict[str, str],
          acts_for: list[str], said: str, nonce: str) -> dict:
    """What a held change's digest covers, which its deciders' sign-ins commit to: the exact
    call, the values its handles stand for, its records as they stood, whom it's for, and the
    words its deciders read (round 15, B1)."""
    return {"scenario": scenario, "run": run, "instance": instance, "tool": tool,
            "schema_hash": schema_hash, "action": action, "args": args, "records": records,
            "values": values, "acts_for": acts_for, "said": said, "nonce": nonce}


def intact(conn: db.Connection, proposal: dict) -> bool:
    """Whether a held change is still what its digest, and so its deciders, signed: made again
    from all a5s holds of it. One the database was changed in, or one kept before a5s kept
    its nonce, isn't: it's never made (round 15, B1)."""
    if not proposal.get("nonce"):
        return False
    body = bound(proposal["scenario"], str(proposal["run_id"]), proposal["instance_id"],
                 proposal["tool"], proposal["schema_hash"], proposal["action"], proposal["args"],
                 proposal["records"], values(conn, proposal), list(proposal["acts_for"]),
                 proposal["said"], proposal["nonce"])
    return hmac.compare_digest(hashlib.sha256(canonical(body).encode()).hexdigest(),
                               proposal["digest"])


ENDINGS = ("decide", "made", "rejected", "lapsed", "changed", "refused", "failed")


def ended_before(conn: db.Connection, proposal: dict) -> bool:
    """Whether the core has decided or ended a held change already, as its own entries in the
    ledger say: so one set waiting again, in the database, is never decided twice (round 15,
    B1)."""
    return conn.execute(
        "select 1 from ledger where run_id = %s and kind = 'proposal' and action = any(%s) and "
        "writer = current_user and (entry::jsonb -> 'args' ->> 'proposal') = %s limit 1",
        (str(proposal["run_id"]), list(ENDINGS), key(proposal))).fetchone() is not None


def snapshot(records: dict[str, Record | None]) -> dict[str, dict | None]:
    """Records as they stand, as a5s keeps them for a held change and for graders."""
    return {k: {"title": r.title, "fields": r.fields, "link": r.link, "person": r.person}
            if r else None for k, r in records.items()}


def fingerprint_of(kept: dict | None) -> str:
    """A digest of a record from its snapshot, to tell whether it's changed since."""
    if kept is None:
        return "none"
    return hashlib.sha256(canonical(kept).encode()).hexdigest()


def changed(scenario: Scenario, proposal: dict) -> list[str]:
    """The records a held change names that have changed since it was asked for."""
    return [r for r, was in proposal["records"].items()
            if fingerprint_of(snapshot({r: record_of(scenario, r)})[r]) != was]


def values(conn: db.Connection, proposal: dict) -> dict[str, str]:
    return {r["handle"]: r["value"] for r in conn.execute(
        "select handle, value from proposal_values where proposal_id = %s", (proposal["id"],))}


# Deciding: signed through the identity provider for that one decision, and sealed by the core

def _hashed(text: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(
        text.encode(errors="replace")).digest()).rstrip(b"=").decode()


def nonce(digests: list[str], decision: str, salt: str, reason: str | None = None) -> str:
    """What a sign-in to decide carries, so the provider's signature covers the decision on
    exactly these changes, and a rejection's reason, as the decider wrote it, by its hash: so
    nothing between the page and the core can put words in their mouth (round 11, E-6). The
    page picks the salt, so each sign-in is different."""
    said = f" said {_hashed(reason)}" if reason else ""
    return _hashed(f"a5s {decision}s proposals {','.join(sorted(digests))} {salt}{said}")


def check(verifier: Verifier, scenario: Scenario, client_id: str, token: str, digests: list[str],
          decision: str, salt: str, now: float,
          reason: str | None = None) -> tuple[Person, dict]:
    """Who signed in to make this decision on these changes, with this reason, and what the
    provider signed, if the sign-in checks out for it. Otherwise, Refused."""
    if decision not in DECISIONS:
        raise Refused(400, "a change is approved or rejected")
    return fresh(verifier, scenario, client_id, token, nonce(digests, decision, salt, reason),
                 salt, now, f"{decision} these changes")


def fresh(verifier: Verifier, scenario: Scenario, client_id: str, token: str, bound: str,
          salt: str, now: float, what: str) -> tuple[Person, dict]:
    """Who signed in afresh to do exactly one thing, which the sign-in's nonce commits to,
    and what the provider signed, if the sign-in checks out for it, as every act that counts
    checks it (approvals.afresh). Otherwise, Refused: a sign-in the browser kept does
    nothing."""
    try:
        return approvals.afresh(verifier, scenario, client_id, token, bound, salt, now, what, what)
    except approvals.Refused as exc:
        raise Refused(exc.status, exc.reason, exc.second_factor) from None


def may_decide(scenario: Scenario, proposal: dict, person: str) -> bool:
    """Whether someone may decide a held change now: they may decide it for one of the parts
    it touches, as the directory stands, never anyone it was for, nor anyone whose answer to
    them may have asked for it, and they may see its records."""
    by_part = deciders(scenario, list(proposal["records"]), not_deciding(proposal))
    return person in {p.id for p in everyone(by_part)}


def record(conn: db.Connection, scenario: str, found: list[dict], decision: str,
           person: str, token: str, salt: str, claims: dict, now: datetime,
           reason: str | None = None) -> list[dict]:
    """Record a decision on each of these changes, with the sign-in that made it, and why, for
    a rejection that says, as the decider wrote it, for the gateway to check against the
    sign-in, clean and seal (seal_pending). Refused if the sign-in was used, or the person has
    decided one of them already."""
    made = []
    for proposal in found:
        entry = {"scenario": scenario, "digest": proposal["digest"], "decision": decision,
                 "person": person, "nonce": claims["nonce"], "salt": salt,
                 "issuer": claims["iss"], "subject": str(claims.get("sub") or ""),
                 "token": approvals.HASHED + hashlib.sha256(token.encode()).hexdigest(),
                 "decided_at": now,  # by the core's clock, as everything that falls due is
                 "reason": reason if decision == "reject" and reason else None, "proof": token}
        row = conn.execute(
            "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, salt, "
            "issuer, subject, decided_at, reason, proof) values (%(scenario)s, %(digest)s, "
            "%(decision)s, %(person)s, %(token)s, %(nonce)s, %(salt)s, %(issuer)s, %(subject)s, "
            "%(decided_at)s, %(reason)s, %(proof)s) on conflict do nothing returning id",
            entry).fetchone()
        if row is None:
            raise Refused(409, f"{key(proposal)} has been decided with that sign-in, or by you, "
                               "already")
        made.append({**entry, **row})
    return made


# what every row of one sign-in's decision shares: else the channels app could record one
# person's decision as another's, an approval as a rejection, or words they never wrote
DECIDED_TOGETHER = ("person", "decision", "salt", "reason", "proof", "nonce", "issuer", "subject")


def together_else(conn: db.Connection, scenario: Scenario, first: dict, together: list[dict],
                  decided: list[str]) -> str | None:
    """Why one sign-in's decision doesn't hold together as the gateway reads it, as the page that
    records it checks it: one person's, one decision, with one reason, on 1 to 20 changes they
    may each decide now, a sensitive one alone (round 13, A1). None if it does."""
    if any(row[f] != first[f] for row in together for f in DECIDED_TOGETHER):
        return "one sign-in's decision is recorded as more than one person's, or more than one decision"
    if not 1 <= len(decided) <= MOST_DECIDED:
        return f"a sign-in decides from one to {MOST_DECIDED} changes"
    rows = conn.execute("select * from proposals where scenario = %s and digest = any(%s)",
                        (scenario.name, decided)).fetchall()
    if len(rows) != len(decided):
        return "a change it names isn't one a5s holds"
    if len(rows) > 1 and any(r["sensitive"] for r in rows):
        return "a sensitive change is decided on its own, with a sign-in of its own"
    return None


def may_decide_all(conn: db.Connection, scenario: Scenario, person: str, decided: list[str]) -> str | None:
    """Why someone whose sign-in checks out may not decide every change it names now, if not."""
    rows = conn.execute("select * from proposals where scenario = %s and digest = any(%s)",
                        (scenario.name, decided)).fetchall()
    if any(not may_decide(scenario, r, person) for r in rows):
        return f"{person} may not decide every change it names"
    return None


def seal_pending(conn: db.Connection, keys: tuple[str, ...], verifier: Verifier | None,
                 scenario: Scenario, client_id: str | None,
                 clean: Callable[[str], str] = lambda said: said) -> list[sealing.Refusal]:
    """Check again each decision the channels app recorded, by its sign-in, which covers every
    change decided with it and a rejection's reason, seal each, with its reason made fit to
    tell whoever asked (`clean`), and let the sign-in go, in the gateway: or refuse them, and
    tell whoever decided, who may decide again. Those whose sign-in can't be checked just now,
    since the identity provider can't be reached, wait. Why each refused one was."""
    if not keys:
        return []  # they wait for a gateway that can seal them
    rows = conn.execute("select * from proposal_decisions where scenario = %s and seal is null "
                        "and refused is null order by id for update skip locked",
                        (scenario.name,)).fetchall()
    signed: dict[str, list[dict]] = {}
    for row in rows:
        signed.setdefault(row["token"], []).append(row)
    refused = []
    for together in signed.values():
        first = together[0]
        decided = sorted(r["digest"] for r in conn.execute(
            "select digest from proposal_decisions where token = %s", (first["token"],)))
        why = together_else(conn, scenario, first, together, decided)
        try:
            why = why or sealing.check(
                verifier, scenario, client_id, first["proof"],
                nonce(decided, first["decision"], first["salt"], first["reason"]), first["person"],
                recorded=(first["token"], first["nonce"]), salt=first["salt"])
        except sealing.Unchecked:
            continue  # checked again at the next sweep
        why = why or may_decide_all(conn, scenario, first["person"], decided)
        if why is not None:
            named = approvals.names_of([key(p) for p in conn.execute(
                "select id from proposals where digest = any(%s) order by id",
                ([r["digest"] for r in together],))]) or "a change"
            refused.append(sealing.Refusal(
                first["person"], f"{first['person']}'s decision: {why}",
                (("Your decision on {named} didn't count: {why}. If it still waits for you, "
                  "decide it again on a5s's own page, signing in afresh."),
                 {"named": named, "why": why})))
        for row in together:
            if why is not None:
                conn.execute("update proposal_decisions set refused = %s, proof = null "
                             "where id = %s", (why, row["id"]))
            else:
                said = clean(row["reason"]) if row["reason"] else None
                conn.execute("update proposal_decisions set seal = %s, reason = %s, proof = null "
                             "where id = %s", (_mac(keys[0], {**row, "reason": said}), said,
                                               row["id"]))
    return refused


def sealed(keys: tuple[str, ...], entry: dict) -> bool:
    return bool(keys) and any(hmac.compare_digest(_mac(k, entry), entry["seal"]) for k in keys)


def seal_of(keys: tuple[str, ...], entry: dict) -> str:
    """The core's seal over a decision, with the first of its keys."""
    return _mac(keys[0], entry)


def _mac(key: str, entry: dict) -> str:
    fields = {k: entry.get(k) for k in _SEALED}
    fields["token"] = entry["token"].removeprefix(approvals.HASHED)
    return hmac.new(key.encode(), canonical(fields).encode(), hashlib.sha256).hexdigest()


def decision(conn: db.Connection, keys: tuple[str, ...], scenario: Scenario,
             proposal: dict) -> tuple[dict | None, list[str]]:
    """What counts of the decisions on a held change, in the order they were made: a rejection
    by anyone who may decide it, or an approval for every part it touches, each the core
    sealed, by someone who may decide for that part now. And what's wrong with any other.
    {"decision", "rows"}, or None while it still waits."""
    by_part = deciders(scenario, list(proposal["records"]), not_deciding(proposal))
    problems: list[str] = []
    approved: dict[str | None, dict] = {}
    for row in conn.execute("select * from proposal_decisions where digest = %s and refused is "
                            "null and (seal is not null or proof is null) order by id",
                            (proposal["digest"],)):
        if not row["seal"] or not sealed(keys, row):
            problems.append(f"{row['person']}'s decision isn't one the core sealed")
            continue
        parts = [part for part, people in by_part.items() if row["person"] in {p.id for p in people}]
        if not parts:
            problems.append(f"{row['person']} may not decide it now")
        elif row["decision"] == "reject":
            return {"decision": "reject", "rows": [row]}, problems
        else:
            for part in parts:
                approved.setdefault(part, row)
            if all(part in approved for part in by_part):
                rows = list({r["id"]: r for r in approved.values()}.values())
                return {"decision": "approve", "rows": rows}, problems
    return None, problems


def settled(conn: db.Connection, scenario: Scenario, proposal: dict) -> list[str]:
    """Who decided a held change already, by name, so that no other decision on it counts:
    whoever rejected it first, or approved it for every part it touches, by the decisions
    recorded on it that a5s hasn't refused, sealed yet or not. Nobody while another decision
    may still count, as a rejection does in a part nobody has approved (round 15, B3)."""
    by_part = deciders(scenario, list(proposal["records"]), not_deciding(proposal))
    approved: dict[str | None, str] = {}
    first: list[str] = []
    for row in conn.execute("select person, decision from proposal_decisions where digest = %s "
                            "and refused is null order by id", (proposal["digest"],)):
        parts = [part for part, people in by_part.items()
                 if row["person"] in {p.id for p in people}]
        if not parts:
            continue
        if row["decision"] == "reject":
            first = [row["person"]]
            break
        for part in parts:
            approved.setdefault(part, row["person"])
        if all(part in approved for part in by_part):
            first = list(dict.fromkeys(approved.values()))
            break
    return [who.name if (who := scenario.person(p)) else p for p in first]


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


def asking(proposal: dict, link: str, again: bool = False,
           language: str = languages.ENGLISH) -> str:
    """The message asking a decider to decide a held change, for chats without cards, or
    reminding them of it, in the language they read: the change itself stays in the words its
    deciders seal, which a reader of another language is told (round 15, B6)."""
    flags = "".join(f"\n- {f}" for f in words.flags(proposal, language))
    opening = (say(language, "Still waiting for your decision: {key}, since {day}.",
                   key=key(proposal), day=languages.day(proposal["proposed_at"], language))
               if again else say(language, "{key} waits for your decision.", key=key(proposal)))
    sealed = f"\n{say(language, SEALED)}" if language != languages.ENGLISH else ""
    return (f"{opening}\n{proposal['said']}{sealed}"
            + (f"\n{say(language, 'What to know:')}{flags}" if flags else "")
            + "\n" + say(language, "Decide it on a5s's page, and approve it only if you mean it: "
                                    "{link}", link=link))


def card(proposal: dict, link: str, again: bool = False,
         language: str = languages.ENGLISH) -> dict:
    """The card a decider gets in Teams or Slack, in the language they read, as `asking`. It
    only opens the core's page, where they decide."""
    title = (say(language, "Still waiting for your decision: {key}", key=key(proposal)) if again
             else say(language, "{key}: a change to decide", key=key(proposal)))
    body = [{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "wrap": True, "text": proposal["said"]}]
    if language != languages.ENGLISH:
        body.append({"type": "TextBlock", "wrap": True, "isSubtle": True,
                     "text": say(language, SEALED)})
    if flags := words.flags(proposal, language):
        body.append({"type": "TextBlock", "wrap": True, "text": say(language, "What to know:")
                     + "\n" + "\n".join(f"- {f}" for f in flags)})
    body.append({"type": "TextBlock", "wrap": True, "isSubtle": True, "size": "Small",
                 "text": say(language, "You decide on a5s's page, after signing in again. "
                                       "Telling an agent decides nothing.")})
    return {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4", "body": body,
            "actions": [{"type": "Action.OpenUrl", "title": say(language, "Review and decide"),
                         "url": link}]}


def told(proposal: dict, became: str, by: str | None = None, extra: str = "",
         reason: str | None = None, language: str = languages.ENGLISH, undo: str = "") -> str:
    """What a5s tells whoever a held change was for, once something became of it, in the
    language they read: `by` whom, with what else there is to say (`extra`), as what changed or
    why it wasn't made, and how to undo it, once it's made, where its tool says how (`undo`).
    The change itself is in its own words, as it was asked for."""
    given = {"by": by, "key": key(proposal), "change": first(proposal)}
    if became == "made":
        return (say(language, "{by} approved {key}, and a5s has made it: {change} {undo}",
                    undo=undo, **given) if undo else
                say(language, "{by} approved {key}, and a5s has made it: {change}", **given))
    if became == "rejected":
        return (say(language, "{by} didn't approve {key}, so a5s didn't make it: {change} They "
                    "said: {reason}", reason=reason, **given) if reason else
                say(language, "{by} didn't approve {key}, so a5s didn't make it: {change}",
                    **given))
    if became == "lapsed":
        return say(language, "Nobody decided {key} within {days} working days, so a5s let it go: "
                   "{change} Ask again if it's still needed.", key=given["key"], days=LAPSE,
                   change=given["change"])
    if became == "changed":
        return say(language, "{by} approved {key}, but a5s didn't make it, since {what} changed "
                   "after it was asked for: {change} Ask again if it's still needed.",
                   what=extra, **given)
    if became == "refused":
        return say(language, "{by} approved {key}, but a5s couldn't make it, since {why}: "
                   "{change}", why=say(language, extra), **given)
    if became == "failed":
        return say(language, "{by} approved {key}, but the records system didn't take it "
                   "({error}): {change}", error=extra, **given)
    return say(language, "a5s stopped part way through making {key}, so it may or may not have "
               "been made, and {by} has ended it, having checked the records system: {change} "
               "Ask again if it's still needed.", **given)


def brief(conn: db.Connection, instance: str, acts_for: list[str],
          records: list[str], conversation: str | None = None) -> tuple[list[str], bool]:
    """The changes waiting for a decision on these records, asked for the same people, for a
    run's brief: so the agent says it waits, rather than asking again. In a group chat, those
    asked for there while everyone now in it was there. And whether one was asked for by a run
    that read content from outside, whose words the run that's given them takes on, as what a
    marked run passed on stays marked (round 15, F1)."""
    if not records:
        return [], False
    if conversation is not None:
        rows = conn.execute(
            "select p.* from proposals p join runs r on r.id = p.run_id where p.instance_id = %s "
            "and r.trigger->>'conversation' = %s and r.acts_for @> %s::text[] "
            "and p.status = 'waiting' and p.records ?| %s order by p.id",
            (instance, conversation, acts_for, records)).fetchall()
    else:
        rows = conn.execute(
            "select * from proposals where instance_id = %s and acts_for = %s "
            "and status = 'waiting' and records ?| %s order by id",
            (instance, acts_for, records)).fetchall()
    return ([f"{key(r)} waits for a decision, asked for on {r['proposed_at']:%d %b}: {first(r)}"
             for r in rows], any(bool(r["read_outside"]) for r in rows))
