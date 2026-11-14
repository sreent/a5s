"""The settings app's own work, apart from its pages (docs/administration.md): what someone who
approves versions of the settings writes is checked, then recorded as a request, for the core to
propose to everyone the version needs (core/gateway.py). The settings app's page asks for one,
and so does the studio, for someone asking for an agent (core/asks.py). Asking changes nothing by
itself: the version takes effect only once its approvers approve it.
"""

from __future__ import annotations

from typing import Any

import yaml

from a5s import db
from a5s.contract import Person, Settings, parse_settings
from a5s.core import approvals, ledger

REQUESTS_A_DAY = 5  # versions one person may ask for in the settings app [starting value]
MAX_SETTINGS = 64 * 1024  # characters of settings, as written


class Refused(ValueError):
    """Why a version can't be asked for: the status to answer with, and each problem."""

    def __init__(self, status: int, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.status, self.problems = status, problems


def drafted(gw: Any, text: str, last: dict | None) -> tuple[Settings | None, bytes, list[str]]:
    """The version someone wrote, with the next serial, and why it can't be proposed. It's
    checked strictly before a5s works with it: no YAML anchors or aliases, which can make a
    few bytes into gigabytes, and only what a5s's format allows."""
    if len(text) > MAX_SETTINGS:
        return None, b"", [f"settings are at most {MAX_SETTINGS // 1024} KB"]
    try:
        parse_settings(text.encode())
        data = yaml.safe_load(text)
        data["serial"] = (last["serial"] if last else 0) + 1
        raw = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode()
        settings = parse_settings(raw)
    except (yaml.YAMLError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, b"", [f"a5s can't read it as settings: {exc}"]
    return settings, raw, gw.unusable(settings, last)


def request(conn: db.Connection, gw: Any, person: Person, text: str, **why: str) -> dict:
    """Record a request for the version someone wrote, in the caller's transaction, for the
    core to propose within a minute: refused if they asked for one it's still proposing, have
    asked for as many as a day allows, or it can't be proposed. `why` goes in the ledger, such
    as the ask it answers."""
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"settings {person.id}",))
    asked = conn.execute(
        "select count(*) filter (where outcome is null) as waiting, count(*) filter "
        "(where asked_at > now() - interval '1 day') as today from settings_requests "
        "where scenario = %s and person = %s", (gw.scenario.name, person.id)).fetchone() or {
        "waiting": 0, "today": 0}  # a count has its row, always
    if asked["waiting"]:
        raise Refused(409, ["a5s is still proposing what you asked for last: try again in a minute"])
    if asked["today"] >= REQUESTS_A_DAY:
        raise Refused(429, [(f"you've asked for {REQUESTS_A_DAY} versions today, which is as many "
                             "as a day allows: try again tomorrow")])
    last = approvals.latest(conn, gw.scenario.name)
    settings, raw, problems = drafted(gw, text, last)
    if settings is None or problems:
        raise Refused(409, problems)
    row = conn.execute("insert into settings_requests (scenario, person, raw) values (%s, %s, %s) "
                       "returning id", (gw.scenario.name, person.id, raw)).fetchone()
    if row is None:  # an insert returns the row it made
        raise Refused(409, ["a5s couldn't record what you asked for: try again"])
    ledger.append(conn, {"kind": "admin", "action": "request", "run": None, "instance": None,
                         "acts_for": [], "decision": "record",
                         "args": {"settings": settings.version, "serial": settings.serial,
                                  "by": person.id, "identity": "verified", **why}})
    return {"request": row["id"], "serial": settings.serial}


def serving(conn: db.Connection, gw: Any, instance: str, person: str) -> str:
    """The version in force, as written, with someone added to whom an instance serves."""
    last = approvals.latest(conn, gw.scenario.name)
    data = yaml.safe_load(bytes(last["raw"])) if last else None
    found = (data or {}).get("instances", {}).get(instance)
    if not isinstance(found, dict):
        raise Refused(404, [f"there's no instance {instance} in the settings in force"])
    found["serves"] = [*found.get("serves", []), person]
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
