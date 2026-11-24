"""a5s's own words, in English: what waits on someone in the studio and why, the roles they
hold and what each lets them do, and a5s's notes to them in chat.

An English sentence is its own key, with {name}s for what changes, so the code that writes it
stays as readable as it is: each module that writes words someone reads passes its sentence,
what changes, and the language they read to `say`, so another language's words could sit beside
these one day. a5s keeps none now: its pages and notes are in English, and agents answer each
person in the language they read (core/languages.py).
"""

from __future__ import annotations

import re

from a5s import levels


def say(language: str, text: str, /, **given: object) -> str:
    """a5s's words for someone, with what changes put in: by any name, {text} and {language}
    among them, as its own two are given only by place."""
    return text.format(**given) if given else text


def level(language: str, value: int | None, /) -> str:
    """What an agent may do, by the name of its level, in someone's language: reads only,
    asks first or acts on its own, or none, where nothing is set (a5s/levels.py)."""
    return say(language, "none" if value is None else levels.name(value))


def doing(language: str, value: int | None, /) -> str:
    """The same, as what an agent is doing: reading only, asking first or acting on its own,
    or none, where nothing is set."""
    return say(language, "none" if value is None else levels.doing(value))


def kept(text: str, /, **given: object) -> dict:
    """Words a5s keeps, to say later in the language whoever reads them then reads: one of its
    sentences, with what changes in it, any of which may be kept words too, or a list of names
    (round 15, B6)."""
    return {"says": text, "given": given}


def said(language: str, found: object, /) -> str:
    """Words a5s kept, in someone's language, with what changes in them put in by name alone:
    a list of names in words, and words kept before a5s kept them so, as they are."""
    says = found.get("says") if isinstance(found, dict) else None
    if not isinstance(found, dict) or not isinstance(says, str):
        return str(found)
    given = {k: said(language, v) if isinstance(v, dict) else _names(language, v)
             if isinstance(v, list) else v for k, v in (found.get("given") or {}).items()}
    return re.sub(r"\{(\w+)\}", lambda m: str(given.get(m.group(1), m.group(0))), says)


def flags(row: dict, language: str, /) -> list[str]:
    """What a held change's deciders, or its sample's graders, are told to know of it, in the
    language they read: as a5s kept them, or, kept before, in English."""
    return [said(language, f) for f in row.get("flagged") or row.get("flags") or []]


def _names(language: str, found: list) -> str:
    names = [str(n) for n in found]
    if not names:
        return say(language, "nobody")
    return names[0] if len(names) == 1 else say(language, "{first} and {last}",
                                                 first=", ".join(names[:-1]), last=names[-1])
