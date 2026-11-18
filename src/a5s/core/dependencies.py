"""What depends on what, for the studio's map: the parts the settings name, the instances at
work in them, the agents they run, the tools each may call and the systems those come from,
the models they call, and the systems whose events start an agent's runs.

Each as far as someone may see it, as the rest of the studio shows it: an agent as far as the
layers they see of it go (core/studio.py's `layers`), its tools, model and events only if they
see what it may do; the instances they may watch, with the parts those work in and whom each
may ask among them. So whoever changes one thing sees what may change with it, before it does:
everything that reaches a tool's system, a model or a part, and everything an instance reaches.

An edge runs from what depends to what it depends on: an instance on the agent it runs, its
model, its parts and the instance it answers beside, if it's a shadow; an agent on its tools,
its model, its judge and the systems that start it; a tool on its system: the scenario's
records, an MCP server or a library of documents, and the system it acts in as the person, with
their own permissions, if it does. A model a release names that this deployment doesn't have is
on it too, said so. What depends on something is everything with a way along the edges to it.

What each edge says is a whole sentence, in the language whoever looks reads, with {from} and
{to} where the page puts their names, so it reads as itself from either end, in any language.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from a5s import db
from a5s.config import ModelConfig
from a5s.contract import Person, Scenario, Tool
from a5s.core import languages, parts, studio, words

# The kinds of things on the map, in the order of its columns, left to right
KINDS = ("part", "instance", "agent", "tool", "system", "model", "team")
STATUS = {"active": "at work", "suspended": "suspended", "proposed": "waiting for approval",
          "shadow": "a shadow: it answers beside another, and sends nothing"}
# Each edge, in words, whole: what depends is {from}, what it depends on {to}, which the page
# names, so each reads as itself in any language, from either end
SAYS = {
    "call": "{from} may call {to}",
    "comes": "{from} comes from {to}",
    "as_person": "{from} acts in {to} as the person it acts for, with their own permissions",
    "events": "{to}'s {type} events start {from}'s runs",
    "release": "{from}'s release names {to}",
    "judge": "{to} judges {from}'s work",
    "runs": "{from} runs {to}'s version {release}",
    "calls": "{from} calls {to}",
    # what it may do there, by name: reads only, asks first or acts on its own (a5s/levels.py)
    "works": "{from} works in {to}, where it {level}",
    "works2": "{from} works in {to}, where it {level}, and acts on its own for {types}",
    # Acting on its own the settings give that doesn't count yet (round 14, C16): a5s holds it
    # to asking first until graded samples show the type's accurate enough, or nobody who
    # approved the settings in force owns the part now
    "capped": ("{from} works in {to}, where it {level}; the settings let it act on its own for "
               "{held}, which a5s holds to asking first until graded samples show it's "
               "accurate enough"),
    "capped2": ("{from} works in {to}, where it {level}, and acts on its own for {types}; the "
                "settings let it act on its own for {held} too, which a5s holds to asking "
                "first until graded samples show it's accurate enough"),
    "unowned": ("{from} works in {to}, where it {level}; the settings let it act on its own for "
                "{held}, which counts only once an owner of {to} approves the settings in force"),
    "asks": "{from} may ask {to}",
    "shadows": "{from} answers beside {to}, and sends nothing",
    "hands": "{from} may hand a conversation to {to}, whose people answer it",
}
ABOUT = {"mcp": "an MCP server", "records": "the scenario's own records",
         "library": "a library of documents", "events": "sends events",
         "as_person": "a system agents act in as the person, with their own permissions",
         "part": "a part of the records, which its owners decide for",
         "team": "people who answer the conversations handed to them",
         "gone": "not in the scenario now", "unknown": "not in models.yaml"}


def drawn(conn: db.Connection, scenario: Scenario, definitions: dict[str, Any],
          tools: dict[str, Tool], models: dict[str, ModelConfig], viewer: Person,
          language: str = languages.ENGLISH, *, approved: Iterable[str],
          caps_of: Callable[[str], dict[tuple[str, str], int]]) -> dict:
    """The map as someone may see it: each thing on it, by its kind and name, and each edge,
    from what depends to what it depends on, saying how, in the language they read. Level 2
    counts where the settings set it only as a5s's caps for an instance's release
    (`caps_of`), and the approvers of the settings in force (`approved`), let it, as policy
    weighs it (core/parts.py): where they don't, the map says so (round 14, C16)."""
    approved = list(approved)
    every = studio.instances(conn)
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], str] = {}

    def node(kind: str, name: str, about: str = "", at: str | None = None,
             tone: str | None = None) -> str:
        key = f"{kind}:{name}"
        nodes.setdefault(key, {"key": key, "kind": kind, "name": name, "about": about,
                               "at": at, "tone": tone})
        return key

    def say(about: str) -> str:
        return words.say(language, ABOUT[about])

    def edge(source: str, target: str, how: str, **args: Any) -> None:
        edges.setdefault((source, target), words.say(
            language, SAYS[how], **{"from": "{from}", "to": "{to}"}, **args))

    def model(alias: str) -> str:
        found = models.get(alias)
        if found is None:  # a release may name one this deployment doesn't have
            return node("model", alias, say("unknown"), tone="warn")
        return node("model", alias, f"{found.provider}, {found.region}" if found.region != (
            "not stated") else found.provider)

    for name, definition in sorted(definitions.items()):
        view = studio.layers(name, definition, every, viewer, scenario)
        if not view:
            continue  # not one they may know exists
        agent = node("agent", name, definition.does or "", f"/studio/agents/{name}")
        if "uses" not in view:
            continue  # what it may do isn't theirs to see
        for listed in definition.tool_names:
            tool = tools.get(listed)
            key = node("tool", listed, tool.description if tool else say("gone"),
                       tone=_tone(tool))
            edge(agent, key, "call")
            if tool is None:
                continue
            server, library = getattr(tool, "server", ""), getattr(tool, "library", "")
            if library:  # a library's documents, read as its declaration says
                edge(key, node("system", getattr(tool, "title", "") or library, say("library")),
                     "comes")
            else:
                edge(key, node("system", server or scenario.name,
                               say("mcp") if server else say("records")), "comes")
            if person_in := getattr(tool, "as_person", ""):  # with the person's own permissions
                edge(key, node("system", person_in, say("as_person")), "as_person")
        for event in definition.events:
            edge(agent, node("system", event.source, say("events")), "events", type=event.type)
        edge(agent, model(definition.model), "release")
        if definition.evaluation is not None:  # its judge, which reads what its runs did
            edge(agent, model(definition.evaluation.judge), "judge")
    watched = [i for i in every if studio.watches(i, viewer) and f"agent:{i['definition']}" in nodes]
    for inst in watched:
        status = str(inst["status"])
        key = node("instance", inst["id"], words.say(language, STATUS[status])
                   if status in STATUS else status, f"/studio/instances/{inst['id']}")
        edge(key, f"agent:{inst['definition']}", "runs", release=inst["release"])
        if inst["model"]:
            edge(key, model(inst["model"]), "calls")
        actions = inst.get("actions") or {}
        for part, level in sorted((inst["parts"] or {}).items()):
            there = actions.get(part) if isinstance(actions, dict) else None
            named = words.level(language, level)  # by name, never by number
            second = sorted(a for a, n in (there or {}).items() if n == 2)  # acting on its own
            target = node("part", part, say("part"), "/studio/settings")
            caps = caps_of(str(inst["release"])) if second else {}
            earned = [a for a in second if caps.get((part, a), 1) >= 2]
            held = ", ".join(a for a in second if a not in earned)
            if second and not parts.owned(scenario, part, approved):  # until an owner approves
                edge(key, target, "unowned", level=named, held=", ".join(second))
            elif held:
                edge(key, target, "capped2" if earned else "capped", level=named,
                     types=", ".join(earned), held=held)
            elif second:
                edge(key, target, "works2", level=named, types=", ".join(second))
            else:
                edge(key, target, "works", level=named)
    shadowing = {r["id"]: r["shadows"] for r in conn.execute(
        "select id, shadows from instances where shadows is not null").fetchall()}
    for inst in watched:  # whom each may ask, and answers beside, of the instances they may see,
        for team in sorted(inst.get("hands_to") or []):  # and the teams it may hand to
            edge(f"instance:{inst['id']}", node("team", team, say("team")), "hands")
        for asked in inst["asks"] or []:
            if f"instance:{asked}" in nodes:
                edge(f"instance:{inst['id']}", f"instance:{asked}", "asks")
        if (beside := shadowing.get(inst["id"])) and f"instance:{beside}" in nodes:
            edge(f"instance:{inst['id']}", f"instance:{beside}", "shadows")
    order = {kind: i for i, kind in enumerate(KINDS)}
    return {"nodes": sorted(nodes.values(), key=lambda n: (order[n["kind"]], n["name"])),
            "edges": [{"from": s, "to": t, "says": says} for (s, t), says in sorted(edges.items())]}


def _tone(tool: Tool | None) -> str | None:
    """What a tool does, as the studio colours it (studio/src/ui.tsx's `risk`): changes
    records, sends outside, writes or reads."""
    if tool is None:
        return None
    if tool.action or tool.destructive:
        return "changes"
    return "outside" if tool.sends_outside else "writes" if tool.writes else "reads"


def reaching(found: dict, key: str) -> dict[str, list[str]]:
    """What something depends on, and what depends on it, along the map's edges, nearest
    first: what changes with it, either way."""
    out: dict[str, list[str]] = {}
    ins: dict[str, list[str]] = {}
    for e in found["edges"]:
        out.setdefault(e["from"], []).append(e["to"])
        ins.setdefault(e["to"], []).append(e["from"])

    def walk(along: dict[str, list[str]]) -> list[str]:
        seen, queue, found_ = {key}, deque([key]), []
        while queue:
            for nxt in along.get(queue.popleft(), []):
                if nxt not in seen:
                    seen.add(nxt)
                    found_.append(nxt)
                    queue.append(nxt)
        return found_

    return {"depends_on": walk(out), "depended_on_by": walk(ins)}
