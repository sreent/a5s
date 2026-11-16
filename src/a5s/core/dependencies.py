"""What depends on what, for the studio's map: the parts the settings name, the instances at
work in them, the agents they run, the tools each may call and the systems those come from,
the models they call, and the systems whose events start an agent's runs.

Each as far as someone may see it, as the rest of the studio shows it: an agent as far as the
layers they see of it go (core/studio.py's `layers`), its tools, model and events only if they
see what it may do; the instances they may watch, with the parts those work in and whom each
may ask among them. So whoever changes one thing sees what may change with it, before it does:
everything that reaches a tool's system, a model or a part, and everything an instance reaches.

An edge runs from what depends to what it depends on: an instance on the agent it runs, its
model and its parts; an agent on its tools, its model and the systems that start it; a tool on
its system. What depends on something is everything with a way along the edges to it.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from a5s import db
from a5s.config import ModelConfig
from a5s.contract import Person, Scenario, Tool
from a5s.core import studio

# The kinds of things on the map, in the order of its columns, left to right
KINDS = ("part", "instance", "agent", "tool", "system", "model")
STATUS = {"active": "at work", "suspended": "suspended", "proposed": "waiting for approval"}


def drawn(conn: db.Connection, scenario: Scenario, definitions: dict[str, Any],
          tools: dict[str, Tool], models: dict[str, ModelConfig], viewer: Person) -> dict:
    """The map as someone may see it: each thing on it, by its kind and name, and each edge,
    from what depends to what it depends on, saying how."""
    every = studio.instances(conn)
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], str] = {}

    def node(kind: str, name: str, about: str = "", at: str | None = None,
             tone: str | None = None) -> str:
        key = f"{kind}:{name}"
        nodes.setdefault(key, {"key": key, "kind": kind, "name": name, "about": about,
                               "at": at, "tone": tone})
        return key

    def edge(source: str, target: str, says: str) -> None:
        edges.setdefault((source, target), says)

    def model(alias: str) -> str | None:
        found = models.get(alias)
        if found is None:
            return None
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
            key = node("tool", listed, tool.description if tool else "not in the scenario now",
                       tone=_tone(tool))
            edge(agent, key, "may call it")
            server = getattr(tool, "server", "") if tool else ""
            if tool is not None:
                edge(key, node("system", server or scenario.name,
                               "an MCP server" if server else "the scenario's own records"),
                     "comes from it")
        for event in definition.events:
            edge(agent, node("system", event.source, "sends events"),
                 f"its {event.type} events start runs")
        if (chosen := model(definition.model)) is not None:
            edge(agent, chosen, "its release names it")
    watched = [i for i in every if studio.watches(i, viewer) and f"agent:{i['definition']}" in nodes]
    for inst in watched:
        status = str(inst["status"])
        key = node("instance", inst["id"], STATUS.get(status, status), f"/studio/instances/{inst['id']}")
        edge(key, f"agent:{inst['definition']}", f"runs its version {inst['release']}")
        if inst["model"] and (chosen := model(inst["model"])) is not None:
            edge(key, chosen, "calls it")
        for part, level in sorted((inst["parts"] or {}).items()):
            edge(key, node("part", part, "a part of the records, which its owners decide for",
                           "/studio/settings"), f"works in it, at level {level}")
    for inst in watched:  # whom each may ask, of the instances they may see
        for asked in inst["asks"] or []:
            if f"instance:{asked}" in nodes:
                edge(f"instance:{inst['id']}", f"instance:{asked}", "may ask it")
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
