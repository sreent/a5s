"""Describe it: a new agent's first draft, from what its author says it's for, in their own words,
given the least it needs (docs/studio.md#describe-it).

A model reads the words, and what the scenario offers an agent: its tools, each with what it does
and whether it only reads, writes, sends outside or changes records; the kinds of record people owe
something in, which an agent may chase; and a5s's own abilities. It answers with what the agent
needs of them, and why, in a few words for each. Code then makes the draft, never the model: only
what the scenario offers, each with the reason the model gave, at the lowest level that lets it do
that work, never 2, since level 2 is only ever for a type of action that the settings and graded
samples give. What the model asked for that the draft hasn't got, and why, the draft says too. Its
author checks each, and adds or takes away by hand, on its canvas, as for any draft: describing it
is a start, never the end.

The sandbox asks the model (a5s/sandbox.py), its stand-in or a real one it has. The stand-in
thinks nothing: it gives only the tools that only read whose words match the description's.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from a5s.contract import Tool
from a5s.core import extractor

DESCRIBING = "You draft a new agent for a5s"  # how a description's request starts, as the stand-in knows
WORDS = 2000  # characters of a description, at most
WHY = 200  # characters of each reason kept
DOES = 400  # characters of what it does
WORKS_FOR = 200
INSTRUCTIONS = 4000  # characters of its instructions
# a5s's own abilities a description may give, each as the studio says it: the rest, such as other
# agents or long tasks, need the settings or a budget of their own, so they're added by hand
ABILITIES = {
    "reminders": "offers reminders, and keeps those people confirm",
    "recall": "searches its conversation with the person it acts for",
    "documents": "asks a5s's reader about documents from outside its run has read",
    "digest-time": "lets people set when their daily digest comes",
    "how-i-work": "keeps what people tell it of how they like to work",
}
SYSTEM = (DESCRIBING + " from what its author says it's for. Give it the least it needs: only "
          "tools, kinds of record people owe something in, and abilities from what the scenario "
          "offers, each only if what it's for needs it, with a few words saying why. Never give "
          "it a tool that changes records, writes or sends outside unless what it's for asks it "
          "to do that. Answer with JSON alone: {\"works_for\": \"whom it works for\", \"does\": "
          "\"what it does for them, in a sentence\", \"tools\": [{\"name\": \"...\", \"why\": "
          "\"...\"}], \"owed\": [{\"kind\": \"...\", \"why\": \"...\"}], \"abilities\": "
          "[{\"name\": \"...\", \"why\": \"...\"}], \"instructions\": \"how it should work, as "
          "short points\"}.")
STOP = frozenset({"what", "with", "that", "their", "from", "each", "they", "them", "when", "such",
                  "this", "have", "into", "than", "then", "does", "about", "which", "whom", "only",
                  "also", "there", "these", "those", "your", "will", "would", "could", "should",
                  "some", "more", "most", "other", "make", "just", "like", "want", "need", "needs",
                  "before", "after", "while", "every", "anyone", "someone", "people", "person"})


def kind(tool: Tool) -> str:
    """What a tool does, most consequential first, as the studio's designer groups it."""
    if tool.action or tool.destructive:
        return "changes"
    if tool.sends_outside:
        return "outside"
    if tool.writes:
        return "writes"
    return "reads"


def offer(tools: dict[str, Tool], owed: list[str]) -> dict[str, Any]:
    """What the scenario offers a new agent, as the model is told it."""
    return {"tools": [{"name": name, "does": tool.description, "kind": kind(tool)}
                      for name, tool in sorted(tools.items())],
            "owed": sorted(owed), "abilities": ABILITIES}


def asked(api: str, alias: str, words: str, offered: dict[str, Any]) -> dict[str, Any]:
    """A description's request, in the model's API's style."""
    return extractor.asked(api, alias, SYSTEM, (
        f"What it's for, in its author's words:\n<<<\n{words[:WORDS]}\n>>>\n\n"
        f"What the scenario offers it:\n<<<\n{json.dumps(offered, ensure_ascii=False)}\n>>>"))


def proposal(reply: str) -> dict | None:
    """What the model proposed, from its reply, if it reads as a proposal at all."""
    found = re.search(r"\{.*\}", reply, re.DOTALL)
    try:
        said = json.loads(found.group(0)) if found else None
    except ValueError:
        return None
    return said if isinstance(said, dict) else None


def _stems(text: str) -> dict[str, str]:
    """The words of `text` that say something, by their first five letters, each as said first."""
    found: dict[str, str] = {}
    for word in re.findall(r"[a-z]{4,}", text.lower()):
        if word not in STOP:
            found.setdefault(word[:5], word)
    return found


def stand_in(body: dict[str, Any]) -> dict[str, Any]:
    """The sandbox's stand-in's proposal, which thinks nothing: the tools that only read whose
    words match the description's, and nothing else."""
    said = str((body.get("messages") or [{}])[-1].get("content") or "")
    blocks = re.findall(r"<<<\n(.*?)\n>>>", said, re.DOTALL)
    words = blocks[0] if blocks else ""
    try:
        offered = json.loads(blocks[1]) if len(blocks) > 1 else {}
    except ValueError:
        offered = {}
    wanted = _stems(words)
    tools = []
    for tool in offered.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("kind") != "reads":
            continue
        theirs = _stems(f"{str(tool.get('name')).replace('_', ' ')} {tool.get('does')}")
        if matched := sorted({wanted[stem] for stem in wanted.keys() & theirs.keys()}):
            tools.append({"name": tool.get("name"), "why": f"its words match yours: {', '.join(matched)}"})
    return {"does": " ".join(words.split())[:DOES], "tools": tools}


def _reason(item: Any) -> tuple[str, str]:
    """An item the model named, and why, each in plain words."""
    if not isinstance(item, dict):
        return "", ""
    name = str(item.get("name") or item.get("kind") or "").strip()
    why = " ".join(str(item.get("why") or "").split())[:WHY]
    return name, why


def drafted(files: dict[str, str], name: str, proposed: dict, tools: dict[str, Tool],
            owed: list[str]) -> tuple[dict[str, str], list[dict]]:
    """A new agent's files from the blank start's, `files`, with what the model proposed that
    the scenario offers, each with its reason; and notes for its author on each thing it was
    given and why, what it wasn't given and why, and its levels."""
    spec = yaml.safe_load(files["agent.yaml"]) or {}
    notes: list[dict] = []

    def left(what: str, why: str) -> None:
        notes.append({"what": what or "something unnamed", "given": False, "why": why})

    groups: dict[str, list[str]] = {}
    for item in proposed.get("tools") or []:
        tool, why = _reason(item)
        if tool not in tools:
            left(tool, "the scenario offers no such tool")
        elif not why:
            left(tool, "the model gave no reason it needs it")
        elif not any(tool in names for names in groups.values()):
            groups.setdefault(kind(tools[tool]), []).append(tool)
            notes.append({"what": tool, "given": True, "why": why})
    obligations: list[str] = []
    for item in proposed.get("owed") or []:
        what, why = _reason(item)
        if what not in owed:
            left(what, "people owe nothing in such records here")
        elif not why:
            left(what, "the model gave no reason it needs it")
        elif what not in obligations:
            obligations.append(what)
            notes.append({"what": f"what people owe in {what}", "given": True, "why": why})
    abilities: list[str] = []
    for item in proposed.get("abilities") or []:
        what, why = _reason(item)
        if what not in ABILITIES:
            left(what, "it's no ability a description gives: add it by hand, if it needs it")
        elif not why:
            left(what, "the model gave no reason it needs it")
        elif what not in abilities:
            abilities.append(what)
            notes.append({"what": what, "given": True, "why": why})
    # The least level that work needs: 1 for anything that writes, else 0, which only reads
    acting = sorted(t for group, names in groups.items() if group != "reads" for t in names)
    writes = acting or obligations or any(a in abilities for a in ("reminders", "how-i-work", "digest-time"))
    level = 1 if writes else 0
    notes.append({"what": f"level {level} at most", "given": True, "why": (
        f"{', '.join(acting)} {'writes' if len(acting) == 1 else 'write'} or "
        "change something, which needs level 1, and a change waits for its part's decider there"
        if acting else "it writes what people ask it to keep, which needs level 1" if writes
        else "it only reads, which level 0 allows") + "; never 2, which only the settings and "
        "graded samples give a type of change"})
    spec["autonomy"] = {"start": level, "max": level}
    spec["tools"] = groups
    if obligations:
        spec["obligations"] = obligations
    if "reminders" in abilities:
        spec["reminders"] = True
    context = dict(spec.get("context") or {})
    for flag in ("recall", "documents"):
        if flag in abilities:
            context[flag] = True
    spec["context"] = context
    if chosen := [a for a in ("digest-time", "how-i-work") if a in abilities]:
        spec["preferences"] = chosen
    for key, most in (("works_for", WORKS_FOR), ("does", DOES)):
        if said := " ".join(str(proposed.get(key) or "").split())[:most]:
            spec[key] = said
    made = {**files, "agent.yaml": yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)}
    told = proposed.get("instructions")
    if isinstance(told, list):  # as points, which some models give
        told = "\n".join(f"- {point}" for point in told)
    if told := str(told or "").strip()[:INSTRUCTIONS]:
        made["AGENTS.md"] = f"# {name}\n\n{told}\n"
    return made, notes
