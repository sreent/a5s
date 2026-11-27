"""The first draft of an MCP server's declaration (docs/connectors.md#mcp-servers), from what the
server lists of its tools, for its author to put in a5s's words before any of it goes in a
scenario's mcp.yaml: `a5s mcp declare <url> --server <name>`.

What a server says of its tools is taken as a start, never as a5s's word: its descriptions are
the server's, marked for rewording; its annotations, which are hints, set the flags a5s reads
from them, never fewer than they say, and a tool that says nothing of itself is drafted as one
that writes; and what only its author can say is left for them, saying why. The draft names no
fields a5s passes on, so a5s refuses it until someone has chosen them: what an agent may see of
an answer is a judgement, never a server's to make."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import yaml

AGENTS_NAME = re.compile(r"[^a-z0-9]+")

TOP = """\
# A first draft of {server}'s MCP declaration, from the tools {url} listed on {day}, by
# `a5s mcp declare`. Nothing here reaches an agent until it's in the scenario's mcp.yaml and a
# release approves it (docs/manual/connecting.md). For each tool you keep:
# - say what it's for in a5s's words: each description is the server's own, which the model
#   would read
# - name the fields of its answer a5s passes on, in returns: a5s refuses a tool without them
# - name the argument a call's record is in (record_arg), and the field each record it returns
#   is named by (record_field), for need-to-know
# - for a change, the action it is, which a5s holds for the record's part to decide, and how
#   it's undone, if it can be (undo)
# - the fields that hold sensitive values (handles), outgoing text (text_fields), or content
#   from outside the organisation (outside, with extract)
"""


def agents_name(calls: str) -> str:
    """A server's name for a tool as a5s names one: lower case, digits and _, such as
    get_ticket for getTicket or get-ticket."""
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", calls).lower()
    return AGENTS_NAME.sub("_", split).strip("_") or "tool"


def _dumped(key: str, value: Any, indent: int) -> list[str]:
    text = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, width=96,
                          default_flow_style=False)
    return [" " * indent + line for line in text.splitlines()]


def _mapping(value: Any) -> dict:
    """A part of what a server lists, if it's a mapping, as JSON Schema's parts are."""
    return value if isinstance(value, dict) else {}


def _flags(hints: Any) -> tuple[dict[str, bool], list[str]]:
    """The flags a tool's annotations set, never fewer than they say, and why each."""
    said = hints if isinstance(hints, dict) else {}
    flags: dict[str, bool] = {}
    why: list[str] = []
    if said.get("readOnlyHint") is True:
        why.append("it says it only reads (readOnlyHint)")
    elif said.get("readOnlyHint") is False or said.get("destructiveHint") is True:
        flags["writes"] = True
        why.append("it says it changes things (readOnlyHint: false): for a change to a record, "
                   "say the action it is, with record_arg, and how it's undone, if it can be")
    else:
        flags["writes"] = True
        why.append("it says nothing of what it changes: until you know it only reads, it's "
                   "drafted as writing")
    if said.get("destructiveHint") is True and said.get("readOnlyHint") is not True:
        flags["destructive"] = True
        why.append("it says it may destroy what it changes (destructiveHint)")
    if said.get("idempotentHint") is True:
        flags["idempotent"] = True
        why.append("it says asking again does it once (idempotentHint)")
    if said.get("openWorldHint") is True:
        flags["sends_outside"] = True
        why.append("it says it reaches outside the organisation (openWorldHint): if it reads "
                   "content from there rather than sending, declare outside, with extract, "
                   "instead")
    return flags, why


def draft(server: str, url: str, listed: dict[str, dict], token_env: str | None,
          only: list[str] | None = None, day: date | None = None) -> str:
    """The draft, as YAML with its author's work said in comments: `listed` is the server's
    tools as it lists them, by their names; `only`, those of them to draft, if not all."""
    wanted = [name for name in listed if not only or name in only]
    if missing := [name for name in only or [] if name not in listed]:
        raise ValueError(f"{server} lists no tool {', '.join(missing)}: it lists "
                         + (", ".join(sorted(listed)) or "none"))
    lines = TOP.format(server=server, url=url, day=(day or date.today()).isoformat()).splitlines()
    lines += ["servers:", f"  {server}:", *_dumped("url", url, 4)]
    lines += ([f"    token_env: {token_env}"] if token_env else
              [f"    # token_env: A5S_MCP_{server.upper()}_TOKEN  # if it takes a5s's token, or",
               "    # as_person: <system>  # to call it as each person, as A5S_DELEGATION names it"])
    lines += ["    # sandbox: <url>  # its stand-in, which answers in the studio's sandbox instead",
              "tools:"]
    taken: set[str] = set()
    for calls in wanted:
        tool = listed[calls]
        name = agents_name(calls)
        while name in taken:
            name += "_"
        taken.add(name)
        flags, why = _flags(tool.get("annotations"))
        schema = _mapping(tool.get("inputSchema"))
        fields = sorted(_mapping(_mapping(tool.get("outputSchema")).get("properties")))
        lines += [f"  {name}:", f"    server: {server}", *_dumped("calls", calls, 4),
                  "    # the server's own words: say what it's for in a5s's",
                  *_dumped("description", " ".join(str(tool.get("description") or "").split())
                           or "<what it's for>", 4),
                  *_dumped("arguments", schema or {"type": "object", "properties": {}}, 4),
                  "    # returns: [<each field an agent may see of its answer>]"
                  + (f"  # it says it returns {', '.join(fields)}" if fields else
                     "  # it says nothing of what it returns")]
        lines += [f"    # {reason}" for reason in why]
        lines += [f"    {flag}: true" for flag in flags]
    return "\n".join(lines) + "\n"
