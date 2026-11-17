"""Events: other systems telling a5s something happened, such as a ticket opened, so an agent
whose release takes it starts work at once, rather than at its next schedule
(definitions.Event).

A system signs each event it sends with the secret the deployment gave it, over the request's
time and its body: the channels' endpoint checks the signature before it reads a word, and
refuses a request more than five minutes from now, so none can be sent again later. An event
names its own id, its type, the records it's about and the person it's about, if anyone:
nothing else, since what a run reads of a record it reads itself, through its tools and a5s's
checks, as any run does, so nothing a system was told can reach a run as words.

It's kept once by its id, and the core opens a run for it at its next sweep, within a minute:
in the instance at work of an agent whose release takes it, which works in every record's part.
The run acts for the person it names, where the directory knows them and the instance serves
them, and writes to them; else it acts for nobody, as a schedule's does, and works through its
tools alone.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from a5s import config, db
from a5s.core import ledger, registry

KIND = "event"  # the trigger of a run that works on one
WINDOW = 300  # seconds: a request further than this from now is refused
MOST_RECORDS = 5  # the records one event names at most, as one change names few
MOST_WAITING = 1000  # one system's events waiting at once: past them, it's told to wait
FIELDS = frozenset({"id", "type", "records", "person"})
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_TYPE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}")
_PERSON = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@:/-]{0,199}")


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class Source:
    """A system that may tell a5s something happened, and the secret it signs with."""

    name: str
    secret: str = field(repr=False)


@dataclass(frozen=True)
class EventsConfig:
    sources: tuple[Source, ...]

    @classmethod
    def from_env(cls) -> EventsConfig | None:
        """Each system from A5S_EVENT_SOURCES, a JSON list of {"source", "secret_env"}, its
        signing secret in the variable it names; None where events aren't turned on."""
        listed = config.EVENT_SOURCES.read()
        if not listed:
            return None
        return cls(sources=tuple(Source(s["source"], os.environ[s["secret_env"]])
                                 for s in listed))


def signature(secret: str, body: bytes, at: int) -> str:
    """What a system sends as X-A5S-Signature: v1=, then the HMAC-SHA256 of v1:, the time it
    sends as X-A5S-Timestamp, a colon and the body, under its secret, in hex."""
    return "v1=" + hmac.new(secret.encode(), b"v1:" + str(at).encode() + b":" + body,
                            hashlib.sha256).hexdigest()


def check(cfg: EventsConfig, source: str, body: bytes, timestamp: str | None,
          signature_given: str | None, now: float | None = None) -> dict[str, Any]:
    """The event a system sent, once its signature checks out and it says only what an event
    may: its id, its type, the records it's about, at most a few, and the person it's about.
    Otherwise, Refused, saying why."""
    found = next((s for s in cfg.sources if s.name == source), None)
    if found is None:
        raise Refused(404, f"a5s takes no events from {source}")
    if not timestamp or not signature_given or not signature_given.startswith("v1="):
        raise Refused(401, f"{source} signs what it sends")
    try:
        at = int(timestamp)
    except ValueError:
        raise Refused(401, "the request's time isn't one") from None
    if abs((time.time() if now is None else now) - at) > WINDOW:
        raise Refused(401, "the request was signed more than five minutes from now")
    if not hmac.compare_digest(signature(found.secret, body, at), signature_given):
        raise Refused(401, f"the signature isn't {source}'s")
    try:
        event = json.loads(body)
    except ValueError:
        raise Refused(400, "an event is JSON") from None
    if not isinstance(event, dict):
        raise Refused(400, "an event is a JSON object")
    if extra := sorted(set(event) - FIELDS):
        raise Refused(400, f"an event says its id, type, records and person, and nothing else, "
                           f"such as {extra[0]}: an agent reads what it needs of a record itself")
    given, kind = event.get("id"), event.get("type")
    records, person = event.get("records") or [], event.get("person")
    if not isinstance(given, str) or not _ID.fullmatch(given):
        raise Refused(400, "an event's id is its own, such as INC0012345-opened")
    if not isinstance(kind, str) or not _TYPE.fullmatch(kind):
        raise Refused(400, "an event's type is a name such as ticket-opened")
    if not isinstance(records, list) or len(records) > MOST_RECORDS or not all(
            isinstance(r, str) and _KEY.fullmatch(r) for r in records):
        raise Refused(400, f"an event names at most {MOST_RECORDS} records, each by its key")
    if person is not None and (not isinstance(person, str) or not _PERSON.fullmatch(person)):
        raise Refused(400, "an event names the person it's about as the directory knows them, "
                           "such as entra:<object id>, or names nobody")
    return {"id": given, "type": kind, "records": sorted(set(records)), "person": person}


def takers(definitions: dict[str, Any], source: str, kind: str) -> list[str]:
    """The agents whose release takes this system's events of this type."""
    return sorted(d.id for d in definitions.values()
                  if any(e.source == source and e.type == kind for e in d.events))


def taken(definition: Any, source: str, kind: str) -> Any | None:
    """What an agent's release says to do with an event of this type from this system."""
    return next((e for e in (definition.events if definition else ())
                 if e.source == source and e.type == kind), None)


def whose(scenario: Any, given: str | None) -> str | None:
    """Whom an event names, as the directory knows them: by one of their identities, such
    as entra:<object id>, or by their id; None for nobody, or someone it doesn't know."""
    if not given:
        return None
    found = scenario.find(given) if ":" in given else scenario.person(given)
    return found.id if found else None


def waiting(conn: db.Connection, source: str) -> int:
    """How many of a system's events wait for a run."""
    row = conn.execute("select count(*) as n from events where source = %s and taken_at is "
                       "null", (source,)).fetchone()
    return int(row["n"]) if row else 0


def record(conn: db.Connection, scenario: Any, source: str, event: dict[str, Any]) -> bool:
    """Keep an event once, by its system and its own id, with the ledger's word on it: whether
    this is the first time a5s heard of it."""
    person = whose(scenario, event["person"])
    row = conn.execute(
        "insert into events (source, event_id, type, records, person) values (%s, %s, %s, %s, "
        "%s) on conflict (source, event_id) do nothing returning id",
        (source, event["id"], event["type"], event["records"], person)).fetchone()
    if row is None:
        return False
    ledger.append(conn, {"kind": "event", "action": "receive", "run": None, "instance": None,
                         "acts_for": [person] if person else [], "decision": "record",
                         "args": {"source": source, "type": event["type"],
                                  "event": str(row["id"]), "records": event["records"],
                                  **({"named": "someone the directory doesn't know"}
                                     if event["person"] and person is None else {})}})
    return True


def task(said: Any, row: dict[str, Any]) -> str:
    """What a run for an event is asked to do: what its release says, and the event as a5s
    received it, in a5s's own words: its system, its type and the records it names."""
    named = ", ".join(row["records"]) or "no record"
    return (f"{said.task}\n\n{row['source']} says {row['type']} happened, about {named}. "
            "Read what you need of it with your tools.")


def due(conn: db.Connection, gw: Any, now: datetime) -> list[dict[str, Any]]:
    """The events waiting for a run, oldest first, each with the instance at work that takes
    it: of an agent whose release takes it, working in every record's part it names. One no
    instance at work takes, or whose instance is suspended, is recorded so, once."""
    insts = conn.execute("select * from instances where status in ('active', 'suspended') "
                         "order by id").fetchall()
    found = []
    for row in conn.execute("select * from events where taken_at is null order by received_at "
                            "limit 100").fetchall():
        takes = [i for i in insts
                 if (d := gw.definitions.get(i["definition"])) is not None
                 and d.release_id == i["release"] and taken(d, row["source"], row["type"])
                 and all(gw.scenario.part_of(k) in (i["parts"] or {}) for k in row["records"])]
        why = (None if takes and takes[0]["status"] == "active" else
               f"{takes[0]['id']} is suspended" if takes else
               "no instance at work takes it, in its records' parts")
        if why:
            conn.execute("update events set taken_at = %s, instance_id = %s, outcome = %s where "
                         "id = %s", (now, takes[0]["id"] if takes else None, why, row["id"]))
            ledger.append(conn, {"kind": "event", "action": "turn away", "run": None,
                                 "instance": takes[0]["id"] if takes else None,
                                 "acts_for": [row["person"]] if row["person"] else [],
                                 "decision": "deny", "reasons": [why],
                                 "args": {"source": row["source"], "type": row["type"],
                                          "event": str(row["id"])}})
            continue
        inst = takes[0]
        person = row["person"] if row["person"] and registry.serving(
            gw.scenario, inst["serves"], row["person"]) else None
        found.append({"kind": "event", "event": str(row["id"]), "instance": inst["id"],
                      "agent": inst["definition"], **({"person": person} if person else {})})
    return found
