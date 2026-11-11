"""The studio's first step, read only: which agents there are and where they run, how each
agent and instance is doing, and what each run did (docs/studio.md).

The core's API, for code, the command line and CI, and the studio's pages in the channels app,
for people signed in, both work it out here, so each shows the same. The core's API is for the
team that runs a5s, and shows everything. A person sees an instance if they may watch it: they
run it, as its owner or deputy, own its agent, own or decide for one of its parts, or approve
instances. Of its runs, they see those whose every record they may see, and of the rest, how
many there are. Figures count people and never name them, as the measures do; a run shows
whom it acted for, and what was said only by its hash, as the ledger keeps it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import psycopg

from a5s.config import ModelConfig
from a5s.contract import INSTANCE_APPROVER, PART_DELEGATE, PART_OWNER, Person, Scenario, Tool
from a5s.core import ledger, measures, provenance, registry
from a5s.core.releases import agent_owner
from a5s.definitions import Definition

RUNS = 50  # runs to a page, newest first [TBC]
DENIALS = 10_000  # the newest denials looked through, by the ledger's index of them
COLUMNS = ("id, definition, release, status, level, model, serves, owner, deputy, parts, "
           "actions, asks")


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


def instances(conn: psycopg.Connection, viewer: Person | None = None) -> list[dict]:
    """The instances there are, but retired ones, or those the viewer may watch."""
    rows = conn.execute(f"select {COLUMNS} from instances where status <> 'retired' "
                        "order by id").fetchall()
    return [r for r in rows if viewer is None or watches(r, viewer)]


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


def figures(conn: psycopg.Connection, scenario: Scenario, models: dict[str, ModelConfig],
            insts: list[dict], days: int = 30, now: datetime | None = None) -> dict:
    """How some instances are doing over the last `days` days: the measures, as `a5s
    measures` reports them, of those instances alone, and how their runs ended, what was
    denied and why, and the reports they sent."""
    served: dict[str, set[str]] = {}
    for inst in insts:
        served.setdefault(inst["definition"], set()).update(
            registry.served(scenario, inst["serves"]))
    ids = [i["id"] for i in insts]
    found = measures.report(conn, scenario.name, models, days, now,
                            {a: sorted(p) for a, p in served.items()}, instances=ids)
    at = {"ids": ids, "window": f"{max(1, int(days))} days",
          "now": now or conn.execute("select now() as t").fetchone()["t"]}
    since = "%(now)s::timestamptz - %(window)s::interval"
    found["ended"] = [dict(r) for r in conn.execute(
        "select trigger->>'kind' as kind, coalesce(outcome, 'open') as outcome, "
        f"count(*) as runs from runs where instance_id = any(%(ids)s) and opened_at > {since} "
        "group by 1, 2 order by 1, 2", at)]
    found["denied"] = [{"kind": r["kind"], "action": r["action"],
                        "reasons": json.loads(r["reasons"] or "[]"), "times": r["n"]}
                       for r in conn.execute(
        "select kind, action, reasons, count(*) as n from ("
        "  select kind, action, instance_id, entry::jsonb ->> 'at' as at, "
        "  (entry::jsonb -> 'reasons')::text as reasons from ledger "
        "  where decision = 'deny' order by seq desc limit %(most)s) recent "
        f"where instance_id = any(%(ids)s) and at::timestamptz > {since} "
        "group by 1, 2, 3 order by 4 desc, 1, 2 limit 20", {**at, "most": DENIALS})]
    found["reports"] = [dict(r) for r in conn.execute(
        "select source, outcome, count(*) as reports from report_fires "
        f"where instance_id = any(%(ids)s) and fired_at > {since} group by 1, 2 order by 1, 2",
        at)]
    found["instances"] = ids
    return found


def _read(conn: psycopg.Connection, runs: list[str]) -> dict[str, set[str]]:
    """The records each run read with its tools, by key."""
    found: dict[str, set[str]] = {r: set() for r in runs}
    for row in conn.execute("select run_id::text as run, source from run_reads "
                            "where run_id = any(%s::uuid[]) and source like %s",
                            (runs, f"%{provenance.ABOUT}%")):
        found[row["run"]].add(row["source"].rsplit(provenance.ABOUT, 1)[1])
    return found


def _shown(scenario: Scenario, run: dict) -> dict:
    return {"run": run["run"], "instance": run["instance_id"],
            "trigger": (run["trigger"] or {}).get("kind"),
            "acts_for": [{"id": p, "name": _name(scenario, p)} for p in run["acts_for"]],
            "opened_at": run["opened_at"].isoformat(),
            "closed_at": run["closed_at"].isoformat() if run["closed_at"] else None,
            "outcome": run["outcome"] or "open", "tokens": run["tokens"], "model": run["model"],
            "read_outside": run["read_outside"]}


def runs(conn: psycopg.Connection, scenario: Scenario, inst: dict,
         viewer: Person | None = None, before: datetime | None = None,
         limit: int = RUNS) -> dict:
    """An instance's runs, newest first, a page at a time: for a viewer, those whose every
    record they may see, and how many others there are."""
    rows = conn.execute(
        "select id::text as run, instance_id, trigger, acts_for, read_outside, opened_at, "
        "closed_at, outcome, tokens, model from runs where instance_id = %s "
        "and (%s::timestamptz is null or opened_at < %s) order by opened_at desc limit %s",
        (inst["id"], before, before, max(1, min(int(limit), 200)))).fetchall()
    read = _read(conn, [r["run"] for r in rows])
    shown = [r for r in rows if viewer is None
             or all(scenario.sees(viewer.id, k) for k in read[r["run"]])]
    return {"instance": inst["id"], "runs": [_shown(scenario, r) for r in shown],
            "hidden": len(rows) - len(shown),
            "before": rows[-1]["opened_at"].isoformat() if rows else None}


def _calls(entries: list[dict]) -> list[dict]:
    """Each tool call a run made, with the policy's decision, and how it ended."""
    ended = {e["of"]: e for e in entries if e.get("kind") == "tool" and "of" in e}
    return [{"seq": e["seq"], "at": e["at"], "tool": e["action"], "decision": e["decision"],
             "reasons": e.get("reasons") or [],
             "outcome": (ended.get(e["seq"], {}).get("outcome") or {}).get("status")}
            for e in entries if e.get("kind") == "tool" and "of" not in e]


def run(conn: psycopg.Connection, scenario: Scenario, run_id: str,
        viewer: Person | None = None) -> dict | None:
    """What a run did: what started it, whom it acted for, how it ended, the records it read,
    each tool call with the policy's decision, and its entries in the ledger. None if there's
    no such run, or the viewer may not watch its instance or see every record it read or its
    entries name."""
    try:
        row = conn.execute(
            "select id::text as run, instance_id, trigger, acts_for, read_outside, opened_at, "
            "closed_at, outcome, tokens, tokens_in, tokens_out, tokens_cached, model "
            "from runs where id = %s::uuid", (run_id,)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        return None
    if row is None:
        return None
    inst = conn.execute(f"select {COLUMNS} from instances where id = %s",
                        (row["instance_id"],)).fetchone()
    if viewer is not None and (inst is None or not watches(inst, viewer)):
        return None
    read = _read(conn, [row["run"]])[row["run"]]
    entries = ledger.entries(conn, run=row["run"])
    pattern = getattr(scenario, "record_pattern", None)
    named = set(re.findall(pattern, json.dumps([row["trigger"], entries]))) if pattern else set()
    if viewer is not None and not all(scenario.sees(viewer.id, k) for k in read | named):
        return None
    return {**_shown(scenario, row), "agent": inst["definition"] if inst else None,
            "started_by": row["trigger"],
            "tokens_in": row["tokens_in"], "tokens_out": row["tokens_out"],
            "tokens_cached": row["tokens_cached"], "records": sorted(read),
            "calls": _calls(entries), "entries": entries}


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
        lines += [f"{found['id']} {found['release']}: works for {found['works_for']}",
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
    whom = ", ".join(p["name"] or p["id"] for p in found["acts_for"]) or "nobody"
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
