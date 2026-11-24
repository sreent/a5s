"""The language each person reads, as the directory gives it (`language`, such as ja), or else
English. a5s's own words, on its pages and in chat, are in English, and each agent that acts for
someone is told to answer them in the language they read, whatever it is, unless they write to
it in another (`told`).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a5s.contract import Person

ENGLISH = "en"
# Languages as an agent is told them, by their BCP 47 code, in English, which every model reads
NAMES = {"en": "English", "th": "Thai", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
         "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "my": "Burmese", "km": "Khmer",
         "lo": "Lao", "tl": "Filipino", "hi": "Hindi", "fr": "French", "de": "German",
         "es": "Spanish", "pt": "Portuguese", "it": "Italian", "nl": "Dutch"}


def primary(code: str | None) -> str:
    """A language's own code, such as ja for ja-JP, in lower case: English for none."""
    found = (code or "").strip().split("-")[0].split("_")[0].lower()
    return found if found.isalpha() and 2 <= len(found) <= 3 else ENGLISH


def of(person: Person) -> str:
    """The language someone reads: the directory's, or English."""
    return primary(person.language)


def told(language: str) -> str | None:
    """What an agent is told of the language someone reads, for a run that acts for them: nothing
    for English, which it answers in anyway, unless they write in another."""
    if language == ENGLISH:
        return None
    name = NAMES.get(language, f"the language whose code is {language}")
    return (f"They read {name}: write to them in {name}, unless they write to you in another "
            "language, and keep record keys, names, amounts and dates exactly as the records "
            "give them.")


def day(at: datetime) -> str:
    """A day by its date in UTC, as 03 Nov."""
    return f"{at.astimezone(ZoneInfo('UTC')):%d %b}"


def when(at: datetime, timezone: str = "UTC") -> str:
    """A moment in someone's own time zone, which it names, as 18 Nov 2026, 14:08 UTC
    (round 14)."""
    try:
        local = at.astimezone(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        local = at.astimezone(ZoneInfo("UTC"))
    zone = local.tzname() or "UTC"
    if not zone[0].isalpha():  # such as +07, as the time zone database names Bangkok's
        zone = f"UTC{zone}"
    return f"{local:%d %b %Y, %H:%M} {zone}"


def shared(people: list[Person | None]) -> str:
    """The language everyone in a group reads, if they all read one: else English, as a5s
    writes to a group chat."""
    found = {of(p) for p in people if p is not None}
    return found.pop() if len(found) == 1 and None not in people else ENGLISH
