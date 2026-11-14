"""An agent's test cases: in its folder's tests/*.yaml, what's said to it, as whom, and at each
step what must follow, such as the tools it uses and avoids, and what it says or never says.
Its suite runs them on its model before each release is approved (tests/test_agents.py), and
the sandbox runs a draft's, on the scenario's made-up records (a5s/sandbox.py), each checked
here, the same way.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import PurePosixPath

import yaml

NOTE = "(a5s: "  # how a5s starts its note on values the agent wrote itself
# What a case, and each of its steps, may hold that the sandbox runs. The rest, such as a time
# to be at, records changed first, earlier turns, or what a5s keeps afterwards, the agent's
# suite alone runs, on a stack of its own.
CASE = {"name", "as", "steps", "own_values"}
STEP = {"say", "uses", "uses_any", "avoids", "says", "says_any", "never_says"}


class Unreadable(ValueError):
    """A file of test cases that doesn't read as a list of them."""


def dated(text: str, today: date | None = None) -> str:
    """A case's words, with each {in N days} the working day that many days from today, so a
    case about a date ahead stays ahead."""
    def day(found: re.Match) -> str:
        when = (today or date.today()) + timedelta(days=int(found.group(1)))
        while when.isoweekday() > 5:
            when += timedelta(days=1)
        return when.isoformat()

    return re.sub(r"\{in (\d+) days\}", day, text)


def check(step: dict, reply: str, called: list[str], allow_own: bool) -> list[str]:
    """What's wrong with a step's outcome, if anything: `called` is each tool the agent used
    and a5s let it, or held for someone to decide."""
    said, wrong = reply.lower(), []
    wrong += [f"didn't use {t}" for t in step.get("uses", []) if t not in called]
    if (any_of := step.get("uses_any")) and not set(any_of) & set(called):
        wrong.append(f"used none of {', '.join(any_of)}")
    wrong += [f"used {t}" for t in step.get("avoids", []) if t in called]
    wrong += [f"didn't say {s!r}" for s in step.get("says", []) if s.lower() not in said]
    if (any_of := step.get("says_any")) and not any(s.lower() in said for s in any_of):
        wrong.append(f"said none of {any_of}")
    wrong += [f"said {s!r}" for s in step.get("never_says", []) if s.lower() in said]
    if not allow_own and NOTE in reply:
        wrong.append("wrote a key, an amount or a date it didn't read, and a5s noted it")
    return wrong


def found(files: dict[str, str]) -> list[dict]:
    """The test cases in an agent's folder, as its files' text by path: each with the file
    it's in, in the order the suite runs them."""
    cases = []
    for path in sorted(files):
        pure = PurePosixPath(path)
        if pure.parent.as_posix() != "tests" or pure.suffix not in (".yaml", ".yml"):
            continue
        try:
            listed = yaml.safe_load(files[path]) or []
        except yaml.YAMLError:
            raise Unreadable(f"{path} doesn't read as YAML") from None
        if not isinstance(listed, list) or not all(isinstance(c, dict) and isinstance(c.get("name"), str)
                                                   and isinstance(c.get("steps"), list) for c in listed):
            raise Unreadable(f"{path} isn't a list of test cases, each with a name and its steps")
        cases += [{**case, "file": path} for case in listed]
    return cases


def suite_alone(case: dict) -> list[str]:
    """What of a case the agent's suite alone runs, if anything: none, if the sandbox may."""
    extra = set(case) - CASE - {"file"}
    for step in case.get("steps") or []:
        extra |= set(step) - STEP if isinstance(step, dict) else {"a step that isn't one"}
        if isinstance(step, dict) and "say" not in step:
            extra.add("a step where what falls due runs")
    return sorted(extra)
