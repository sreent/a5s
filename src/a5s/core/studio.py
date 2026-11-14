"""The studio's first step, read only: which agents there are and where they run, how each
agent and instance is doing, and what each run did (docs/studio.md).

The core's API, for code, the command line and CI, and the studio's pages in the channels app,
for people signed in, both work it out here, so each shows the same. The core's API is for the
team that runs a5s, and shows everything. A person sees an instance if they may watch it: they
run it, as its owner or deputy, own its agent, own or decide for one of its parts, or approve
instances. Of its runs, they see those whose every record they may see, by the records each
run handled, which a5s keeps as long as the run: those its tools gave it or it named, and those
a5s gave it, such as a report's or a case's brief. Of the rest, they see how many there are.
They never see the ledger's entries, whose digests of short texts can be guessed, and whom a
run acted for is named to them only once the data protection officer agrees
(A5S_STUDIO_NAMES): until then, a run says how many people it acted for. The figures count
people and never name them, nor carry anyone's words: outcomes from a fixed set, and the
reasons for denials by the policy's own ids.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg

from a5s.config import ModelConfig
from a5s.contract import INSTANCE_APPROVER, PART_DELEGATE, PART_OWNER, Person, Scenario, Tool
from a5s.core import ledger, measures, registry, values
from a5s.core.releases import agent_owner
from a5s.core.status import outcome
from a5s.definitions import Definition

RUNS = 50  # runs to a page, newest first [TBC]
MOST_RUNS = 200  # the most to a page
DENIALS = 10_000  # each set of instances' newest denials looked through, by their own index
COLUMNS = ("id, definition, release, status, level, model, serves, owner, deputy, parts, "
           "actions, asks")
SERVING = ("active", "suspended")  # the instances whom an agent serves through
REASON = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # a policy's own id: never words
LAST = "ffffffff-ffff-ffff-ffff-ffffffffffff"  # after every run opened at the same moment


def parts_of(inst: dict) -> list[str]:
    return sorted(inst.get("parts") or {})


def watches(inst: dict, person: Person) -> bool:
    """Whether someone may watch an instance: they run it, as its owner or deputy, own its
    agent, own or decide for one of its parts, or approve instances."""
    roles = set(person.roles)
    return (person.id in (inst.get("owner"), inst.get("deputy"))
            or agent_owner(inst["definition"]) in roles or INSTANCE_APPROVER in roles
            or any(f"{PART_OWNER}:{p}" in roles or f"{PART_DELEGATE}:{p}" in roles
                   for p in parts_of(inst)))


def instances(conn: psycopg.Connection, viewer: Person | None = None, *,
              retired: bool = False) -> list[dict]:
    """The instances there are, or those the viewer may watch: with the retired ones, whose
    runs are still within an agent's figures, if `retired`."""
    rows = conn.execute(f"select {COLUMNS} from instances"
                        + ("" if retired else " where status <> 'retired'")
                        + " order by id").fetchall()
    return [r for r in rows if viewer is None or watches(r, viewer)]


def served(scenario: Scenario, insts: list[dict]) -> dict[str, list[str]]:
    """Whom each agent serves through these instances, as the directory says now: through
    each that's active or suspended, the same for `a5s measures` and for the studio."""
    found: dict[str, set[str]] = {}
    for inst in insts:
        if inst["status"] in SERVING:
            found.setdefault(inst["definition"], set()).update(
                registry.served(scenario, inst["serves"]))
    return {agent: sorted(people) for agent, people in found.items()}


def reasons(found: Any) -> list[str]:
    """A denial's reasons by the policy's own ids: any in words, which may name someone,
    count as other."""
    said = found if isinstance(found, list) else []
    return list(dict.fromkeys(r if isinstance(r, str) and REASON.match(r) else "other"
                              for r in said))


def _name(scenario: Scenario, who: str | None) -> str | None:
    if not who:
        return None
    person = scenario.person(who)
    return person.name if person else who


def _tools(definition: Definition, tools: dict[str, Tool]) -> list[dict]:
    """The scenario's tools the agent may use, each with what it reads, writes or changes."""
    found = []
    for group, names in definition.tools.items():
        for name in names:
            tool = tools.get(name)
            found.append({"name": name, "group": group,
                          "description": tool.description if tool else None,
                          **(tool.risk if tool else {}),
                          "changes": tool.action if tool else None,
                          "handles": list(tool.handles) if tool else [],
                          "outside": list(tool.outside) if tool else [],
                          "pinned": definition.pins.get(name),
                          "missing": tool is None})
    return found


def offered(tools: dict[str, Tool]) -> list[dict]:
    """Each of the scenario's tools an agent may be given, with what it reads, writes or
    changes, as an agent's page shows its own."""
    return [{"name": name, "description": tool.description, **tool.risk, "changes": tool.action,
             "handles": list(tool.handles), "outside": list(tool.outside)}
            for name, tool in sorted(tools.items())]


def _instance(scenario: Scenario, definition: Definition | None, inst: dict) -> dict:
    return {"id": inst["id"], "agent": inst["definition"], "status": inst["status"],
            "release": inst["release"],
            "current": definition is not None and inst["release"] == definition.release_id,
            "level": inst["level"], "parts": inst["parts"] or {},
            "actions": inst["actions"] or {}, "model": inst["model"],
            "serves": list(inst["serves"]),
            "people": len(registry.served(scenario, inst["serves"])),
            "owner": _name(scenario, inst["owner"]), "deputy": _name(scenario, inst["deputy"]),
            "asks": list(inst["asks"] or [])}


def agent(scenario: Scenario, definition: Definition, tools: dict[str, Tool],
          insts: list[dict], whole: bool = False) -> dict:
    """An agent as its release defines it, where it runs, and, `whole`, its instructions."""
    own = set(definition.tool_names)
    found = {
        "id": definition.id, "release": definition.release_id,
        "works_for": definition.works_for, "does": definition.does,
        "owners": [p.name for p in scenario.holders(agent_owner(definition.id))],
        "model": definition.model,
        "autonomy": definition.autonomy.model_dump(),
        "tools": _tools(definition, tools),
        "a5s_tools": [t for t in definition.grants if t not in own],
        "skills": sorted(definition.skills),
        "triggers": definition.triggers,
        "schedules": [s.model_dump() for s in definition.schedules],
        "reports": [r.source for r in definition.reports],
        "obligations": list(definition.obligations),
        "reminders": definition.reminders, "preferences": list(definition.preferences),
        "channels": list(definition.channels),
        "context": definition.context.model_dump(), "budget": definition.budget.model_dump(),
        "instances": [_instance(scenario, definition, i) for i in insts
                      if i["definition"] == definition.id],
    }
    if whole:
        found["instructions"] = definition.instructions
    return found


def catalogue(conn: psycopg.Connection, scenario: Scenario, definitions: dict[str, Definition],
              tools: dict[str, Tool], viewer: Person | None = None) -> list[dict]:
    """Each agent of the release, and where it runs: for a viewer, the agents they own and
    those with an instance they may watch, with those instances alone."""
    insts = instances(conn, viewer)
    watched = {i["definition"] for i in insts}
    return [agent(scenario, d, tools, insts) for name, d in sorted(definitions.items())
            if viewer is None or name in watched
            or agent_owner(name) in viewer.roles]


class UnknownZone(ValueError):
    """A time zone a5s doesn't know."""


def time_zone(name: str) -> ZoneInfo:
    """A time zone by its name in the IANA database, such as Asia/Singapore."""
    try:
        if len(name) <= 64:
            return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        pass
    raise UnknownZone(f"there's no time zone {name[:64]!r}")


def figures(conn: psycopg.Connection, scenario: Scenario, models: dict[str, ModelConfig],
            insts: list[dict], days: int = 30, now: datetime | None = None,
            zone: str = "UTC") -> dict:
    """How some instances are doing over the last `days` days: the measures, as `a5s
    measures` reports them, of those instances alone; how their runs ended, and how many
    ended each way on each day of the period, in `zone`, such as the viewer's own; what was
    denied and why; and the reports they sent."""
    ids = [i["id"] for i in insts]
    here = time_zone(zone)
    now = now or conn.execute("select now() as t").fetchone()["t"]
    found = measures.report(conn, scenario.name, models, days, now, served(scenario, insts),
                            instances=ids)
    at = {"ids": ids, "window": f"{max(1, int(days))} days", "now": now, "zone": zone}
    since = "%(now)s::timestamptz - %(window)s::interval"
    ended: Counter = Counter()
    daily: dict[date, Counter] = defaultdict(Counter)
    try:
        opened = conn.execute(
            "select trigger->>'kind' as kind, outcome, (opened_at at time zone %(zone)s)::date "
            f"as day, count(*) as n from runs where instance_id = any(%(ids)s) and opened_at > "
            f"{since} group by 1, 2, 3", at).fetchall()
    except psycopg.errors.InvalidParameterValue as e:  # one Python knows and Postgres doesn't
        raise UnknownZone(f"there's no time zone {zone!r} here") from e
    for r in opened:
        ended[(r["kind"], outcome(r["outcome"]))] += r["n"]
        daily[r["day"]][outcome(r["outcome"])] += r["n"]
    found["ended"] = [{"kind": k, "outcome": o, "runs": n}
                      for (k, o), n in sorted(ended.items(), key=lambda i: (str(i[0][0]), i[0][1]))]
    first = (now - _interval(days)).astimezone(here).date()
    last = max([now.astimezone(here).date(), *daily])  # and a run the clock hasn't reached
    found["daily"] = [{"day": d.isoformat(), "runs": sum(daily[d].values()),
                       "ended": dict(sorted(daily[d].items()))}
                      for d in (first + timedelta(days=i) for i in range((last - first).days + 1))]
    found["zone"] = zone
    newest = conn.execute(  # these instances' own denials, by their own index, newest first
        "select kind, action, entry::jsonb -> 'reasons' as reasons, "
        "(entry::jsonb ->> 'at')::timestamptz as at from ledger "
        "where decision = 'deny' and instance_id = any(%(ids)s) order by seq desc "
        "limit %(most)s", {**at, "most": DENIALS}).fetchall()
    within = [r for r in newest if r["at"] > now - _interval(days)]
    denied = Counter((r["kind"], r["action"], tuple(reasons(r["reasons"]))) for r in within)
    found["denied"] = [{"kind": k, "action": a, "reasons": list(why), "times": n}
                       for (k, a, why), n in sorted(denied.items(),
                                                    key=lambda i: (-i[1], str(i[0][0]),
                                                                   str(i[0][1])))[:20]]
    found["denied_partial"] = len(newest) == DENIALS and len(within) == len(newest)
    found["reports"] = [dict(r) for r in conn.execute(
        "select source, outcome, count(*) as reports from report_fires "
        f"where instance_id = any(%(ids)s) and fired_at > {since} group by 1, 2 order by 1, 2",
        at)]
    found["instances"] = ids
    return found


def _interval(days: int) -> timedelta:
    return timedelta(days=max(1, int(days)))


# The records each run handled, which the studio shows a run by


def keys_in(value: Any, field: str | None) -> set[str]:
    """The records a tool's result holds, by the field that names each, at any depth."""
    found: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            if isinstance(v.get(field), str) and v[field]:
                found.add(v[field])
            for inner in v.values():
                walk(inner)
        elif isinstance(v, list):
            for inner in v:
                walk(inner)

    if field:
        walk(value)
    return found


def _trigger_records(trigger: dict | None) -> set[str]:
    named = (trigger or {}).get("record")
    return {named} if isinstance(named, str) and named else set()


def named(scenario: Scenario, said: Any) -> set[str]:
    """The records a text names, by the scenario's pattern for its keys: in what a5s tells a
    run, or one of a5s's own tools gives it."""
    pattern = getattr(scenario, "record_pattern", None)
    text = said if isinstance(said, str) else json.dumps(said, ensure_ascii=False, default=str)
    return {v.text for v in values.found(text or "", pattern) if v.kind == "key"}


def given(scenario: Scenario, trigger: dict, seen: dict | None, texts: Iterable[str]) -> set[str]:
    """The records a5s gives a run as it opens: what its trigger is about, what a report tells
    of, and those a case's brief or a task names."""
    found = set(seen or {}) | _trigger_records(trigger)
    for text in texts:
        found |= named(scenario, text)
    return found


def handled(conn: psycopg.Connection, run: str, keys: Iterable[str]) -> None:
    """Keep, as long as the run, the records it handled, by key."""
    found = sorted({k for k in keys if isinstance(k, str) and k})
    if found:
        conn.execute("insert into run_records (run_id, record) "
                     "select %s::uuid, unnest(%s::text[]) on conflict do nothing", (run, found))


def _handled(conn: psycopg.Connection, runs: list[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {r: set() for r in runs}
    for row in conn.execute("select run_id::text as run, record from run_records "
                            "where run_id = any(%s::uuid[])", (runs,)):
        found[row["run"]].add(row["record"])
    return found


def _sees(scenario: Scenario, viewer: Person, run: dict, keys: set[str]) -> bool:
    """Whether someone may see a run: a5s kept its records, and they may see every one."""
    return bool(run["records_kept"]) and all(
        scenario.sees(viewer.id, k) for k in keys | _trigger_records(run["trigger"]))


def _shown(scenario: Scenario, run: dict, names: bool) -> dict:
    return {"run": run["run"], "instance": run["instance_id"],
            "trigger": (run["trigger"] or {}).get("kind"),
            "acts_for": [{"id": p, "name": _name(scenario, p)} for p in run["acts_for"]]
            if names else [],
            "people": len(run["acts_for"]),
            "opened_at": run["opened_at"].isoformat(),
            "closed_at": run["closed_at"].isoformat() if run["closed_at"] else None,
            "outcome": outcome(run["outcome"]), "tokens": run["tokens"], "model": run["model"],
            "read_outside": run["read_outside"]}


def _cursor(before: str | None) -> tuple[datetime, str] | None:
    """Where a page of runs starts: after the run the page before ended at."""
    if not before:
        return None
    at, _, run = before.partition("|")  # a bad time or id is a ValueError, for a 400
    return datetime.fromisoformat(at), str(uuid.UUID(run)) if run else LAST


def runs(conn: psycopg.Connection, scenario: Scenario, inst: dict,
         viewer: Person | None = None, before: str | None = None, limit: int = RUNS,
         names: bool = True) -> dict:
    """An instance's runs, newest first, a page at a time, each page after the run the one
    before ended at: for a viewer, those whose every record they may see, and how many others
    there are, with whom each acted for named only if `names`."""
    page = max(1, min(int(limit), MOST_RUNS))
    after = _cursor(before)
    rows = conn.execute(
        "select id::text as run, instance_id, trigger, acts_for, read_outside, opened_at, "
        "closed_at, outcome, tokens, model, records_kept from runs where instance_id = %s "
        "and (%s::timestamptz is null or (opened_at, id) < (%s::timestamptz, %s::uuid)) "
        "order by opened_at desc, id desc limit %s",
        (inst["id"], after and after[0], after and after[0], after and after[1], page)).fetchall()
    keys = _handled(conn, [r["run"] for r in rows])
    shown = [r for r in rows if viewer is None or _sees(scenario, viewer, r, keys[r["run"]])]
    last = rows[-1] if len(rows) == page else None
    return {"instance": inst["id"],
            "runs": [_shown(scenario, r, viewer is None or names) for r in shown],
            "hidden": len(rows) - len(shown),
            "before": f"{last['opened_at'].isoformat()}|{last['run']}" if last else None}


def _calls(entries: list[dict]) -> list[dict]:
    """Each tool call a run made, with the policy's decision, and how it ended."""
    ended = {e["of"]: e for e in entries if e.get("kind") == "tool" and "of" in e}
    return [{"seq": e["seq"], "at": e["at"], "tool": e["action"], "decision": e["decision"],
             "reasons": reasons(e.get("reasons")),
             "outcome": (ended.get(e["seq"], {}).get("outcome") or {}).get("status")}
            for e in entries if e.get("kind") == "tool" and "of" not in e]


def run(conn: psycopg.Connection, scenario: Scenario, run_id: str,
        viewer: Person | None = None, names: bool = True) -> dict | None:
    """What a run did: what started it, whom it acted for, how it ended, the records it
    handled, and each tool call with the policy's decision; and, for the team that runs a5s,
    its entries in the ledger. None if there's no such run, or the viewer may not watch its
    instance or see every record it handled. Whom it acted for, and what started it beyond
    its kind, only if `names`."""
    try:
        row = conn.execute(
            "select id::text as run, instance_id, trigger, acts_for, read_outside, opened_at, "
            "closed_at, outcome, tokens, tokens_in, tokens_out, tokens_cached, model, "
            "records_kept from runs where id = %s::uuid", (run_id,)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        return None
    if row is None:
        return None
    inst = conn.execute(f"select {COLUMNS} from instances where id = %s",
                        (row["instance_id"],)).fetchone()
    if viewer is not None and (inst is None or not watches(inst, viewer)):
        return None
    keys = _handled(conn, [row["run"]])[row["run"]]
    if viewer is not None and not _sees(scenario, viewer, row, keys):
        return None
    entries = ledger.entries(conn, run=row["run"])
    named = viewer is None or names
    found = {**_shown(scenario, row, named), "agent": inst["definition"] if inst else None,
             "started_by": row["trigger"] if named else {"kind": (row["trigger"] or {}).get("kind")},
             "tokens_in": row["tokens_in"], "tokens_out": row["tokens_out"],
             "tokens_cached": row["tokens_cached"],
             "records": sorted(keys | _trigger_records(row["trigger"])),
             "calls": _calls(entries)}
    if viewer is None:  # the team's: every entry, what was said by hash
        found["entries"] = entries
    return found


# In words, for the command line


def _levels(found: dict) -> str:
    start, most = found["autonomy"]["start"], found["autonomy"]["max"]
    return f"level {start}" if start == most else f"levels {start} to {most}"


def _instance_line(inst: dict) -> str:
    parts = ", ".join(inst["parts"]) or "no part"
    return (f"{inst['id']}: {inst['status']}, level {inst['level']}, in {parts}, serving "
            f"{inst['people']} {'person' if inst['people'] == 1 else 'people'}, run by "
            f"{inst['owner'] or 'nobody'}" + (f" and {inst['deputy']}" if inst["deputy"] else "")
            + ("" if inst["current"] else f", still on release {inst['release']}"))


def told_agents(agents: list[dict]) -> str:
    """The catalogue in words: each agent, and where it runs."""
    lines = []
    for found in agents:
        owners = ", ".join(found["owners"]) or "nobody the directory names"
        lines += [f"{found['id']} {found['release']}. Works for: {found['works_for']}",
                  (f"  {found['model']}, {_levels(found)}, {len(found['tools'])} of the "
                   f"scenario's tools, owned by {owners}")]
        lines += [f"  - {_instance_line(i)}" for i in found["instances"]] or [
            "  - no instance runs it"]
    return "\n".join(lines) or "There are no agents in this release."


def told_agent(found: dict) -> str:
    """One agent in words, as its release defines it, and where it runs."""
    lines = [f"{found['id']}, release {found['release']}",
             f"Works for: {found['works_for']}", f"Does: {found['does']}",
             f"Owners: {', '.join(found['owners']) or 'nobody the directory names'}",
             f"Model: {found['model']}, at {_levels(found)}", "Tools:"]
    for tool in found["tools"]:
        does = [k.replace("_", " ") for k in ("reads", "writes", "destructive", "sends_outside")
                if tool.get(k)]
        more = ([f"changes {tool['changes']}"] if tool["changes"] else []) + (
            [f"hands over {', '.join(tool['handles'])} as handles"] if tool["handles"] else []) + (
            ["reads outside content through a5s's reader"] if tool["outside"] else [])
        lines.append(f"  - {tool['group']}: {tool['name']} ({', '.join(does + more) or 'reads nothing'})"
                     + (", which the scenario doesn't have" if tool["missing"] else ""))
    lines.append(f"a5s's own tools: {', '.join(found['a5s_tools']) or 'none'}")
    if found["skills"]:
        lines.append(f"Skills: {', '.join(found['skills'])}")
    lines.append(f"Reports on: {', '.join(found['reports']) or 'nothing'}; chases: "
                 f"{', '.join(found['obligations']) or 'nothing'}; schedules: "
                 f"{', '.join(s['name'] for s in found['schedules']) or 'none'}")
    lines.append(f"Channels: {', '.join(found['channels'])}; budget: "
                 f"{found['budget']['per_run']:,} tokens a run, "
                 f"{found['budget']['per_person_per_day']:,} a person a day")
    lines.append("Instances:")
    lines += [f"  - {_instance_line(i)}" for i in found["instances"]] or ["  - none"]
    if found.get("instructions"):
        lines += ["Instructions:", found["instructions"]]
    return "\n".join(lines)


def _run_line(found: dict) -> str:
    named = ", ".join(p["name"] or p["id"] for p in found["acts_for"])
    count = found.get("people", 0)
    whom = named or (f"{count} {'person' if count == 1 else 'people'}" if count else "nobody")
    return (f"{found['opened_at']} {found['run']} {found['trigger']} for {whom}: "
            f"{found['outcome']}, {found['tokens']:,} tokens"
            + (", read outside content" if found["read_outside"] else ""))


def told_runs(page: dict) -> str:
    """An instance's runs in words, newest first."""
    lines = [_run_line(r) for r in page["runs"]] or [f"{page['instance']} has no runs here."]
    if page["hidden"]:
        lines.append(f"{page['hidden']} more read records you may not see.")
    return "\n".join(lines)


def told_run(found: dict) -> str:
    """What one run did, in words."""
    lines = [_run_line(found), (f"Agent {found['agent']}, instance {found['instance']}, "
                                f"model {found['model'] or 'none'}; closed "
                                f"{found['closed_at'] or 'not yet'}"),
             f"Records read: {', '.join(found['records']) or 'none'}", "Tool calls:"]
    lines += [f"  - {c['at']} {c['tool']}: {c['decision']}"
              + (f" ({', '.join(c['reasons'])})" if c["reasons"] else "")
              + (f", {c['outcome']}" if c["outcome"] else "") for c in found["calls"]] or [
        "  - none"]
    return "\n".join(lines)
