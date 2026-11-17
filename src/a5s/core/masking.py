"""What could say who someone is, masked by code, in words a5s shows people who aren't to learn
whom they're about (docs/studio.md): what someone said to an agent and what it answered, kept as
a test case, or shown to its owners once someone said the answer was wrong. Masked are the
names and ids of everyone a5s knows of, those it serves and those who run its instances, with
whomever the words are about; emails; links; numbers long enough to be a phone's or an
account's; and, where asked, the keys of the records they name. Code can't know every name someone might write, so
whoever reads what's left still reads it with care.

It reads a text once, from start to end, whatever it holds: an address is looked for only where
one could start, so a long run of letters with no @ in it isn't read again from each of its
letters, and a name is a word looked up, not a pattern tried at every letter for each person.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from a5s import db
from a5s.contract import Scenario
from a5s.core import registry

MOST = 20_000  # characters of a text a5s masks, and so shows, at most
EMAIL = r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
LINK = r"\bhttps?://\S+|\bwww\.\S+"
# 8 digits or more, as a phone's or an account's are, but never a date, such as 2026-11-06
NUMBER = r"(?<![\w£$€.,])(?!\d{4}-\d{2}-\d{2}(?!\d))\+?\d(?:[\s().-]?\d){7,}(?![\w])"
# A word, in a script that puts spaces between its words: never Thai, which writes a
# sentence's words together, so a Thai name is looked for at each of its letters instead
WORD = r"[^\W\d_\u0e00-\u0e7f]+"
THAI = re.compile(r"[\u0e00-\u0e7f]")
PLAIN = re.compile(WORD)
MASKS = {"names": "[someone]", "emails": "[an email]", "links": "[a link]",
         "numbers": "[a number]", "records": "[record {n}]"}
SHORTEST = 3  # letters of a name's part that's masked however it's written; shorter, as written


def known(conn: db.Connection, scenario: Scenario) -> set[str]:
    """Everyone a5s knows of, by id: whom its instances serve, as the directory says now, and
    who runs each, whoever's words a5s masks may name."""
    found: set[str] = set()
    for row in conn.execute("select serves, owner, deputy from instances "
                            "where status <> 'retired'").fetchall():
        found |= set(registry.served(scenario, row["serves"] or []))
        found |= {p for p in (row["owner"], row["deputy"]) if isinstance(p, str) and p}
    return found


def _names(scenario: Scenario, people: Iterable[str]) -> tuple[set[str], set[str], list[str],
                                                              list[str]]:
    """What masks these people: words of their names masked however they're written, short
    ones as written, those in Thai, and ids that aren't words."""
    words: set[str] = set()
    short: set[str] = set()
    thai: set[str] = set()
    ids: set[str] = set()
    for who in {p for p in people if isinstance(p, str) and p}:
        (words if PLAIN.fullmatch(who) else ids).add(who.casefold() if PLAIN.fullmatch(who)
                                                     else who)
        person = scenario.person(who)
        for part in (person.name.split() if person else []):
            if THAI.search(part):
                thai.add(part.strip(".,;:()'\"“”"))  # a Thai name is found inside a sentence
                continue
            for word in PLAIN.findall(part):
                if len(word) >= SHORTEST:
                    words.add(word.casefold())
                elif len(word) > 1:
                    short.add(word)  # such as Li or Bo, masked only as the directory writes it
    return words, short, sorted(thai - {""}, key=len, reverse=True), sorted(ids, key=len,
                                                                            reverse=True)


def numbered(scenario: Scenario, *texts: str | None) -> dict[str, int]:
    """Each record key these texts name, numbered in the order they first name it, for mask's
    `records`, so the same record reads the same in each."""
    pattern = getattr(scenario, "record_pattern", None)
    found: dict[str, int] = {}
    if not pattern:
        return found
    for text in texts:
        for m in re.finditer(pattern, (text or "")[:MOST]):
            found.setdefault(m.group(0), len(found) + 1)
    return found


def mask(text: str, scenario: Scenario, people: Iterable[str], *,
         records: Mapping[str, int] | None = None) -> tuple[str, dict[str, int]]:
    """Text with what could say who anyone is masked by code: these people's names, each part
    of them, and their ids, emails, links and long numbers, and each record key `records`
    numbers, as [record 1] and so on. A key it doesn't number stays, such as one of the
    sandbox's made-up records an author puts in a real one's place. How many of each it masked.
    It masks the first MOST characters, which are all it gives back."""
    words, short, thai, ids = _names(scenario, people)
    pattern = getattr(scenario, "record_pattern", None) if records else None
    numbers = records or {}
    ways = [*([f"(?P<records>(?:{pattern}))"] if pattern else []),
            f"(?P<emails>{EMAIL})", f"(?P<links>{LINK})", f"(?P<numbers>{NUMBER})",
            *([r"(?=[\u0e00-\u0e7f])(?P<thai>" + "|".join(map(re.escape, thai)) + ")"]
              if thai else []),
            *([r"(?<![\w.@+-])(?P<ids>" + "|".join(map(re.escape, ids)) + r")(?![\w@+-])"]
              if ids else []),
            f"(?P<word>{WORD})"]
    masked: dict[str, int] = {}

    def swap(m: re.Match) -> str:
        kind = m.lastgroup or "word"
        said = m.group(0)
        if kind == "word":
            if said.casefold() not in words and said not in short:
                return said
            kind = "names"
        elif kind in ("thai", "ids"):
            kind = "names"
        if kind == "records" and said not in numbers:
            return said
        masked[kind] = masked.get(kind, 0) + 1
        if kind == "records":
            return MASKS["records"].format(n=numbers[said])
        return MASKS[kind]

    return re.compile("|".join(ways), re.IGNORECASE).sub(swap, text[:MOST]), masked

