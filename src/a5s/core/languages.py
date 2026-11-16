"""The language each person reads: the one they chose on their own page in the studio, or else the
one the directory gives them (`language`, such as th), or else English.

The studio's pages and the web chat speak it where a5s has their words in it, English and Thai
for now (SPOKEN), and each agent that acts for someone is told to answer them in it, whatever the
language, unless they write in another. Their choice is one of their preferences, so it's in
their export, and goes when they leave or ask a5s to erase what it keeps of them.
"""

from __future__ import annotations

from datetime import datetime

from a5s import db
from a5s.contract import Person

PREFERENCE = "language"  # its name among someone's preferences
ENGLISH = "en"
# The languages a5s's own pages have words in, each named in its own words, as people choose it
SPOKEN = {"en": "English", "th": "ไทย"}
# Languages as an agent is told them, by their BCP 47 code, in English, which every model reads
NAMES = {"en": "English", "th": "Thai", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
         "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "my": "Burmese", "km": "Khmer",
         "lo": "Lao", "tl": "Filipino", "hi": "Hindi", "fr": "French", "de": "German",
         "es": "Spanish", "pt": "Portuguese", "it": "Italian", "nl": "Dutch"}


class Refused(ValueError):
    """Why a language can't be chosen, in words."""


def primary(code: str | None) -> str:
    """A language's own code, such as th for th-TH, in lower case: English for none."""
    found = (code or "").strip().split("-")[0].split("_")[0].lower()
    return found if found.isalpha() and 2 <= len(found) <= 3 else ENGLISH


def of(conn: db.Connection, person: Person) -> str:
    """The language someone reads: the one they chose, or the directory's, or English."""
    row = conn.execute("select value from preferences where person = %s and name = %s",
                       (person.id, PREFERENCE)).fetchone()
    return primary(row["value"] if row else person.language)


def choose(conn: db.Connection, person: Person, language: str, now: datetime) -> str:
    """Someone's choice of the language a5s's pages speak to them in, and its agents answer in,
    of those a5s has its own words in, as they make it, signed in as themselves."""
    if language not in SPOKEN:
        raise Refused(f"a5s's pages speak {' and '.join(SPOKEN.values())}, not {language[:20]!r}")
    conn.execute(
        "insert into preferences (person, name, value, set_at) values (%s, %s, %s, %s) "
        "on conflict (person, name) do update set value = excluded.value, "
        "set_at = excluded.set_at, set_run = null", (person.id, PREFERENCE, language, now))
    return language


def told(language: str) -> str | None:
    """What an agent is told of the language someone reads, for a run that acts for them: nothing
    for English, which it answers in anyway, unless they write in another."""
    if language == ENGLISH:
        return None
    name = NAMES.get(language, f"the language whose code is {language}")
    return (f"They read {name}: write to them in {name}, unless they write to you in another "
            "language, and keep record keys, names, amounts and dates exactly as the records "
            "give them.")
