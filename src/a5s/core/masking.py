"""What could say who someone is, masked by code, in words a5s shows people who aren't to learn
whom they're about (docs/studio.md): what someone said to an agent and what it answered, kept as
a test case, or shown to its owners once someone said the answer was wrong. Masked are the
names and ids of everyone a5s knows of, those it serves and those who run its instances, with
whomever the words are about; emails; links; numbers long enough to be a phone's or an
account's; and, where asked, the keys of the records they name. Code can't know every name someone might write, so
whoever reads what's left still reads it with care.

Stricter, for what goes where everyone who reads an agent's repository reads it, such as a test
case kept from a real run (core/run_cases.py; round 15, C6): dates of birth, by what's said
before them or by a year at least FIFTEEN years back, in English, Thai and the Buddhist era;
ids of letters and digits, such as a passport's, an IBAN or a National Insurance number;
numbers of six digits or more, such as a sort code; and street addresses, in English and in
Thai, and postcodes. Dates people work by, such as an invoice's due date, stay.

It reads a text once, from start to end, whatever it holds: an address is looked for only where
one could start, so a long run of letters with no @ in it isn't read again from each of its
letters, and a name is a word looked up, not a pattern tried at every letter for each person.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

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
         "numbers": "[a number]", "records": "[record {n}]", "births": "[a date of birth]",
         "dates": "[a date]", "identifiers": "[an id]", "addresses": "[an address]"}

# What `strict` masks besides (round 15, C6)
FIFTEEN = 15  # years back, at least, a date's year is: a grown-up's birth, not a due date
STRICT_NUMBER = r"(?<![\w£$€.,])\+?\d(?:[\s().-]?\d){5,}(?![\w])"  # from six digits
_MONTHS = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
           r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
_THAI_MONTHS = ("มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|"
                "ตุลาคม|พฤศจิกายน|ธันวาคม|ม\\.ค\\.|ก\\.พ\\.|มี\\.ค\\.|เม\\.ย\\.|พ\\.ค\\.|มิ\\.ย\\.|"
                "ก\\.ค\\.|ส\\.ค\\.|ก\\.ย\\.|ต\\.ค\\.|พ\\.ย\\.|ธ\\.ค\\.")
DATE = (r"(?<![\w/.-])(?:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|"
        rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?,?\s+\d{{2,4}}|"
        rf"(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}}|"
        rf"\d{{1,2}}\s*(?:{_THAI_MONTHS})\s*(?:พ\.ศ\.\s*)?\d{{2,4}})(?![\w/])")
BIRTH = (r"(?:date\s+of\s+birth|birth\s*date|birthday|d\.?o\.?b\.?|born|"
         r"วันเดือนปีเกิด|วันเกิด|เกิดวันที่|เกิด)(?:\s+(?:is|was|on))?[\s:,-]*")
IDENTIFIER = (r"(?<![\w-])(?:[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?"  # IBAN
              r"|[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]"  # a National Insurance number
              r"|(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d{5})[A-Z0-9]{6,})(?![\w-])")  # a passport's
_STREETS = (r"road|rd|street|st|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|close|court|ct|"
            r"place|pl|terrace|square|sq|crescent|cres|soi|moo")
ADDRESS = (rf"(?<![\w/])\d{{1,5}}[A-Z]?(?:/\d{{1,5}})?,?\s+(?:[A-Z][\w'.-]*\s+){{0,4}}?"
           rf"(?:{_STREETS})\b\.?"  # 221B Baker Street, 99/12 Sukhumvit Soi
           r"|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b|\b\d{5}-\d{4}\b"  # NW1 6XE, 90210-1234
           r"|(?:บ้านเลขที่|เลขที่)\s*\d{1,5}(?:/\d{1,5})?"  # and in Thai, its parts
           r"|(?:หมู่ที่|หมู่)\s*\d{1,3}"
           r"|(?:ซอย|ถนน|ตำบล|แขวง|อำเภอ|เขต)\s*[\u0e00-\u0e7f0-9]+"
           # ซ. ถ. ต. อ. only before a place's name, never as in ต.ค., October
           r"|[ซถตอ]\.(?![\u0e00-\u0e7f]\.)[\u0e00-\u0e7f0-9]{2,}"
           # a province, with its postcode, and Bangkok's postcode, never an amount alone
           r"|(?:จังหวัด\s*|จ\.(?![\u0e00-\u0e7f]\.))[\u0e00-\u0e7f]{2,}(?:\s*\d{5}(?!\d))?"
           r"|(?:กรุงเทพ(?:มหานคร|ฯ)?|bangkok)\s*\d{5}(?!\d)")
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


def _year(said: str) -> int | None:
    """The year a date says, in the common era: a Buddhist era's less 543, and two digits as
    the nearest century has them."""
    found = re.findall(r"\d+", said)
    four = [f for f in found if len(f) == 4]  # first in 1985-03-12, last in 12/03/1985
    written = four[0] if four else found[-1] if found and len(found[-1]) == 2 else None
    if written is None:
        return None
    year, now = int(written), datetime.now(UTC).year
    if len(written) == 2:
        year += 2000 if year <= now % 100 + 1 else 1900
    return year - 543 if year >= 2400 else year


def _plausible(said: str) -> bool:
    """Whether what reads as a date has a day and a month that could be a day's and a
    month's: 12-34-56 is a sort code."""
    parts = re.findall(r"\d+", said)
    if len(parts) == 3:
        first, second, third = map(int, parts)
        if len(parts[0]) == 4:  # 1985-03-12
            return 1 <= second <= 12 and 1 <= third <= 31
        return (1 <= first <= 31 and 1 <= second <= 12) or (1 <= first <= 12
                                                           and 1 <= second <= 31)
    return len(parts) == 2 and 1 <= int(parts[0]) <= 31  # 12 March 1985


def mask(text: str, scenario: Scenario, people: Iterable[str], *,
         records: Mapping[str, int] | None = None,
         strict: bool = False) -> tuple[str, dict[str, int]]:
    """Text with what could say who anyone is masked by code: these people's names, each part
    of them, and their ids, emails, links and long numbers, and each record key `records`
    numbers, as [record 1] and so on, and where `strict`, more besides, as this module says. A
    key it doesn't number stays, such as one of the sandbox's made-up records an author puts in
    a real one's place. How many of each it masked. It masks the first MOST characters, which
    are all it gives back."""
    words, short, thai, ids = _names(scenario, people)
    pattern = getattr(scenario, "record_pattern", None) if records else None
    numbers = records or {}
    stricter = [f"(?P<births>{BIRTH}(?:{DATE}))", f"(?P<dates>{DATE})",
                f"(?P<addresses>{ADDRESS})", f"(?P<identifiers>{IDENTIFIER})"] if strict else []
    ways = [*([f"(?P<records>(?:{pattern}))"] if pattern else []),
            f"(?P<emails>{EMAIL})", f"(?P<links>{LINK})", *stricter,
            f"(?P<numbers>{STRICT_NUMBER if strict else NUMBER})",
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
        if kind == "dates":
            year = _year(said)
            if year is None or not _plausible(said):
                if len(re.sub(r"\D", "", said)) < 6:
                    return said
                kind = "numbers"  # a sort code, say, which only reads as a date
            elif year > datetime.now(UTC).year - FIFTEEN:
                return said  # a date people work by, not a grown-up's birth
        masked[kind] = masked.get(kind, 0) + 1
        if kind == "records":
            return MASKS["records"].format(n=numbers[said])
        return MASKS[kind]

    return re.compile("|".join(ways), re.IGNORECASE).sub(swap, text[:MOST]), masked

