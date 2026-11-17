"""Outgoing text: what a5s lets reach people, from agents and from what they asked for.

Outgoing text keeps only words and the scenario's own record links. Anything that could fetch or
point somewhere else goes: images, HTML, and links in any form, whatever their case, slashes or
scheme, and a host with a path, such as evil.example/collect?d=..., which a chat may show as a link
(round 15, F13). a5s's own notes, such as (a5s: ...), only a5s writes: an agent's copy of one is
dropped, however it's spelled, in fullwidth brackets, with a zero-width space or with a letter from
another script that looks the same (round 15, F8).

The values a held change carries, which its deciders read and a5s's own messages repeat, are kept
to plain words on one line, cleaned as outgoing text is (`plain`, round 15, F2).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_TAG = re.compile(r"</?[A-Za-z][^>]*>")  # HTML, and autolinks such as <https://...>
# A link's target, and an address, end where a page's would end one: at a quote, a backtick or a
# <, as well as at a space or a bracket, so what a5s checks is all a page links (round 11, E-2)
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(\s*([^)\s'\"`<]*)[^)]*\)")
_URL = re.compile(r"(?i)(?:\b[a-z][a-z0-9+.-]*:[/\\]+|(?<![\w:/\\])//|\bwww\.)[^\s)>\]'\"`<]*")
# A host with a path, a query or a fragment after it, though no scheme: as a chat links it
_BARE = re.compile(r"(?i)(?<![\w@./\\:-])(?:[a-z0-9](?:[a-z0-9-]{0,62})\.)+[a-z]{2,63}"
                   r"(?::\d{1,5})?[/?#][^\s)>\]'\"`<]*")
# a5s's own note on values, which only a5s writes, as the skeleton of text reads it
_FORGED_NOTE = re.compile(r"(?is)\(\s*a\s*5\s*s\s*:.*?\)")
# Letters from other scripts that look like those a note is written in, and other brackets and
# colons: what a skeleton reads them as
_LOOKALIKE = {"а": "a", "А": "A", "ɑ": "a", "α": "a", "Α": "A", "ѕ": "s", "Ѕ": "S", "ꜱ": "s",
              "❨": "(", "❪": "(", "⦅": "(", "❩": ")", "❫": ")", "⦆": ")", "∶": ":", "꞉": ":",
              "˸": ":", "ː": ":"}

MOST_PLAIN = 200  # characters of a value a held change carries, as people read it


def _skeleton(text: str) -> tuple[str, list[int]]:
    """Text as a note is checked in, each character mapped to where it came from: its
    compatibility form (NFKC), without format characters such as a zero-width space, and with
    letters that look alike as one."""
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text):
        if unicodedata.category(ch) == "Cf":
            continue
        for c in unicodedata.normalize("NFKC", _LOOKALIKE.get(ch, ch)):
            out.append(_LOOKALIKE.get(c, c))
            where.append(i)
    return "".join(out), where


def forged(text: str) -> tuple[str, int]:
    """Text without the copies of a5s's notes an agent wrote, however spelled, and how many."""
    skeleton, where = _skeleton(text)
    spans = [(where[m.start()], where[m.end() - 1] + 1) for m in _FORGED_NOTE.finditer(skeleton)]
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text, len(spans)


def sanitize(text: str, allowed: tuple[str, ...], notes: bool = True) -> tuple[str, int]:
    """Keep text and the scenario's own record links. Drop images, HTML and other links, and,
    unless `notes` is False, copies of a5s's own notes, which only a5s writes."""
    removed = 0

    def kept(url: str) -> bool:
        return any(url.startswith(prefix) for prefix in allowed)

    def link(match: re.Match) -> str:
        nonlocal removed
        label = _URL.sub(url, match.group(1))  # whose words may hold an address too
        if kept(match.group(2)):  # the link alone: nothing else it carries past its target
            return f"[{label}]({match.group(2)})"
        removed += 1
        return f"{label} [link removed]"

    def url(match: re.Match) -> str:
        nonlocal removed
        if kept(match.group(0)):
            return match.group(0)
        removed += 1
        return "[link removed]"

    def bare(match: re.Match) -> str:
        nonlocal removed
        removed += 1
        return "[link removed]"

    text, copies = forged(text) if notes else (text, 0)
    text, images = _IMAGE.subn("[image removed]", text)
    text, tags = _TAG.subn("[removed]", text)
    text = _MARKDOWN_LINK.sub(link, text)
    parts = re.split(r"(\[[^\]]*\]\([^)]*\))", text)  # record links already kept stay whole
    text = "".join(p if _MARKDOWN_LINK.fullmatch(p) else _BARE.sub(bare, _URL.sub(url, p))
                   for p in parts)
    return text.strip() if copies else text, removed + images + tags + copies


def cleaned(value: Any, allowed: tuple[str, ...], notes: bool = True) -> tuple[Any, int]:
    """Text at any depth of a value, sanitized, and how many things were removed."""
    if isinstance(value, str):
        return sanitize(value, allowed, notes)
    if isinstance(value, list):
        found = [cleaned(item, allowed, notes) for item in value]
        return [v for v, _ in found], sum(n for _, n in found)
    if isinstance(value, dict):
        found = {k: cleaned(v, allowed, notes) for k, v in value.items()}
        return {k: v for k, (v, _) in found.items()}, sum(n for _, n in found.values())
    return value, 0


def plain(value: str, allowed: tuple[str, ...]) -> str:
    """A value a held change carries, as its deciders read it and a5s repeats it: cleaned as
    outgoing text is, on one line, MOST_PLAIN characters at most, so nothing an agent wrote in it
    reads as a5s's words or as a line of its own (round 15, F2)."""
    text, _ = sanitize(value, allowed)
    text = " ".join(text.split())
    return text if len(text) <= MOST_PLAIN else text[:MOST_PLAIN - 1].rstrip() + "…"
