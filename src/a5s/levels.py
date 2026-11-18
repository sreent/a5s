"""What an agent may do in a part, as people read it: it reads only, it asks first, or it acts
on its own.

- **Reads only:** it reads, reports, reminds and chases, and changes nothing.
- **Asks first:** it drafts, raises requests and proposes changes, and a person decides each.
- **Acts on its own:** it makes a type of change itself, within the scenario's limits, tells
  someone, and the change can be undone. Only the settings give it, for a type of change in a
  part, and only once graded samples show the agent is accurate enough there.

Inside, a5s keeps them as 0, 1 and 2, the order it compares them in, as the ledger and the
API do. Everything people read says their names, and settings and agent definitions take a
name, such as `asks first`, or the number, as they did before.
"""

from __future__ import annotations

from typing import Any

READS_ONLY, ASKS_FIRST, ACTS = 0, 1, 2
NAMES = {READS_ONLY: "reads only", ASKS_FIRST: "asks first", ACTS: "acts on its own"}
DOING = {READS_ONLY: "reading only", ASKS_FIRST: "asking first", ACTS: "acting on its own"}
_BY_NAME = {name: level for level, name in NAMES.items()}


def parse(value: Any) -> Any:
    """A level as settings and agent definitions give it: its name, in any case, with spaces,
    hyphens or underscores, such as `asks first` or `acts-on-its-own`, or its number. Anything
    else is given back as it was, for the field's own check to refuse."""
    if isinstance(value, str):
        said = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
        if said in _BY_NAME:
            return _BY_NAME[said]
        raise ValueError(f"a level is reads only, asks first or acts on its own, not {value!r}")
    return value


def numbered(settings: Any) -> Any:
    """Settings as YAML gives them, each instance's level, and its parts' and their types of
    change's, as its number, as the studio's forms work with them, whichever the version says:
    anything that isn't a level is left as it was."""
    if not isinstance(settings, dict) or not isinstance(settings.get("instances"), dict):
        return settings

    def one(value: Any) -> Any:
        try:
            return parse(value)
        except ValueError:
            return value

    instances = {}
    for iid, inst in settings["instances"].items():
        if isinstance(inst, dict):
            inst = {**inst, **({"level": one(inst["level"])} if "level" in inst else {})}
            parts = inst.get("parts")
            if isinstance(parts, dict):
                inst["parts"] = {part: one(entry) if not isinstance(entry, dict) else {
                    **entry, **({"level": one(entry["level"])} if "level" in entry else {}),
                    **({"actions": {a: one(v) for a, v in entry["actions"].items()}}
                       if isinstance(entry.get("actions"), dict) else {})}
                    for part, entry in parts.items()}
        instances[iid] = inst
    return {**settings, "instances": instances}


def name(level: int) -> str:
    """A level's name, in English: words.say() says it in the reader's language."""
    return NAMES[level]


def doing(level: int) -> str:
    """The same, as what an agent is doing, such as "asking first in billing"."""
    return DOING[level]
