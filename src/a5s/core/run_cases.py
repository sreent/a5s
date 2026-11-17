"""A run of an agent's kept as one of its test cases (docs/studio.md), so drafts are judged
against real work, not only what their authors thought of: what someone said to it, the tools
it used, and what a right answer is, in its author's words.

Only once the data protection officer agrees (`cases_from_runs` in the signed settings), since
what someone said goes into the agent's folder, which its drafts are published from; only for
someone who may author the agent and may see the run, every record it handled, as the studio
shows runs; and only for a run that answered someone's message. Code masks what could say who
anyone is: the names and ids of the people the run acted for, emails, links, and numbers long
enough to be a phone's or an account's. It can't know every name someone might write, so the
author reads what's left, and keeps it only once they say it says nothing about anyone. Record
keys stay as they were, for the author to put the sandbox's made-up records in their place.
What's left is real, never made up, so the case says it's from a run, and only the sandbox's
stand-in, or a model and judge approved for every class of the deployment's data, are ever
given it: never one approved for made-up data alone (a5s/cases.py's `for_real`).
The case goes in their draft of the agent, started from it as released if they have none, in
tests/from-runs.yaml, which its suite runs as it runs its other cases; the ledger records that
they kept it, of which run, never the words.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from a5s import cases, db
from a5s.contract import DataProtection, Person, Scenario
from a5s.core import drafts, ledger, registry, studio

FILE = cases.FROM_RUNS  # in the agent's folder, beside its other cases
ABOUT = ("# Test cases kept from real runs, in the studio: what was said, masked by code and\n"
         "# checked by whoever kept it, and the tools the agent used. Put the sandbox's made-up\n"
         "# records in place of the real ones a case names, and add what it must say.\n")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINK = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.IGNORECASE)
# 8 digits or more, as a phone's or an account's are, but never a date, such as 2026-11-06
NUMBER = re.compile(r"(?<![\w£$€.,])(?!\d{4}-\d{2}-\d{2}(?!\d))\+?\d(?:[\s().-]?\d){7,}(?![\w])")
MASKS = {"names": "[someone]", "emails": "[an email]", "links": "[a link]",
         "numbers": "[a number]"}
NAME = re.compile(r"[^\W\d_]{3,}")  # a part of a name long enough to say who


class Refused(Exception):
    """Why a run can't be kept as a test case."""


def mask(text: str, scenario: Scenario, people: list[str]) -> tuple[str, dict[str, int]]:
    """Text with what could say who anyone is masked by code: the names, each part of them,
    and the ids of these people, emails, links and long numbers. How many of each it masked."""
    masked: dict[str, int] = {}

    def swap(kind: str, pattern: re.Pattern, said: str) -> str:
        said, n = pattern.subn(MASKS[kind], said)
        if n:
            masked[kind] = masked.get(kind, 0) + n
        return said

    said = swap("emails", EMAIL, text)  # before names, which an address may hold
    said = swap("links", LINK, said)
    words: set[str] = set()
    for who in people:
        person = scenario.person(who)
        words |= {who, *(NAME.findall(person.name) if person else [])}
    if words:
        said = swap("names", re.compile(r"\b(?:" + "|".join(
            re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b",
            re.IGNORECASE), said)
    return swap("numbers", NUMBER, said), masked


def _run(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
         definitions: dict[str, Any], choices: DataProtection) -> tuple[dict, dict, str]:
    """A run someone may keep as a test case: what the studio shows them of it, its row, and
    what started it, in words. Refused, saying why, if they may not: as the run's page is, for
    one of an instance serving too few people to show its runs one by one."""
    shown = studio.run(conn, scenario, run_id, viewer, names=False)
    if shown is not None and not choices.studio_names:
        inst = conn.execute("select serves from instances where id = %s",
                            (shown["instance"],)).fetchone()
        if inst is None or len(registry.served(scenario, inst["serves"])) < choices.fewest_people:
            shown = None
    if shown is None:
        raise Refused("there's no such run that you may see")
    agent = str(shown["agent"] or "")
    if agent not in definitions or not drafts.may_author(viewer, agent):
        raise Refused(f"test cases of the {agent} are for its owners and authors")
    if not choices.cases_from_runs:
        raise Refused("the data protection officer hasn't agreed to test cases from real runs")
    row = conn.execute("select trigger, acts_for from runs where id = %s::uuid",
                       (run_id,)).fetchone()
    trigger = (row["trigger"] if row else None) or {}
    if trigger.get("kind") != "message" or not trigger.get("inbound"):
        raise Refused("only a run that answered someone's message makes a test case")
    said = conn.execute("select text from inbound where id = %s::uuid",
                        (trigger["inbound"],)).fetchone()
    if said is None:
        raise Refused("what was said in it is no longer kept")
    return shown, dict(row) if row else {}, str(said["text"])


def proposed(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
             definitions: dict[str, Any], choices: DataProtection) -> dict:
    """A run as a test case, for its author to check and keep: what was said and what the
    agent answered, masked; what code masked; and the tools it used, which a5s let it, or held
    for someone to decide."""
    shown, row, said = _run(conn, scenario, viewer, run_id, definitions, choices)
    people = list(row.get("acts_for") or [])
    say, masked = mask(said, scenario, people)
    answered = conn.execute("select text from outbox where run_id = %s::uuid order by id",
                            (run_id,)).fetchall()
    answer, _ = mask("\n".join(r["text"] for r in answered), scenario, people)
    uses = sorted({c["tool"] for c in shown["calls"] if c["decision"] in ("allow", "hold")})
    return {"run": run_id, "agent": shown["agent"], "say": say[:cases.SAY],
            "answer": answer, "masked": masked, "uses": uses}


def keep(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
         definitions: dict[str, Any], choices: DataProtection, agents_dir: Any, *, name: str,
         as_: str,
         say: str, judged: str | None, checked: bool) -> dict:
    """Keep a run as a test case in someone's draft of its agent, started from it as released
    if they have none, in the caller's transaction, with the ledger's word on it: what they
    say is masked again, as it was offered. The draft, and the case as kept."""
    shown, row, _ = _run(conn, scenario, viewer, run_id, definitions, choices)
    if not checked:
        raise Refused("say first that you've read it, and it says nothing about anyone")
    name = " ".join(name.split())[:80]
    if not name or not as_.strip():
        raise Refused("name the case, and the made-up person who says it")
    said, _ = mask(say.strip(), scenario, list(row.get("acts_for") or []))
    if not said:
        raise Refused("say what's said to it")
    step: dict[str, Any] = {"say": said[:cases.SAY]}
    if uses := sorted({c["tool"] for c in shown["calls"] if c["decision"] in ("allow", "hold")}):
        step["uses"] = uses
    if judged and judged.strip():
        step["judged"] = " ".join(judged.split())[:1000]
    case = {"name": name, "as": as_.strip()[:80], "from_run": True, "steps": [step]}
    agent = str(shown["agent"])
    mine = next((d for d in drafts.mine(conn, viewer) if d["agent"] == agent), None)
    draft = drafts.get(conn, viewer, str(mine["id"])) if mine else None
    if draft is None:
        files = drafts.folder_files(agents_dir / agent)
        draft = drafts.start(conn, viewer, agent, f"{agent} {definitions[agent].release_id}",
                             files, base=dict(files))
    files = dict(draft["files"])
    kept = yaml.safe_load(files.get(FILE) or "[]") or []
    if not isinstance(kept, list):
        raise Refused(f"{FILE} in your draft isn't a list of test cases: put it right first")
    if any(isinstance(c, dict) and c.get("name") == name for c in kept):
        raise Refused(f"your draft has a test case called {name} already")
    files[FILE] = ABOUT + yaml.safe_dump([*kept, case], sort_keys=False, allow_unicode=True)
    saved = drafts.save(conn, viewer, str(draft["id"]), files)
    if saved is None:
        raise Refused("a5s couldn't keep it in your draft: try again")
    ledger.append(conn, {"kind": "admin", "action": "case from run", "run": run_id,
                         "instance": shown["instance"], "acts_for": [], "decision": "record",
                         "args": {"agent": agent, "draft": str(saved["id"]), "by": viewer.id,
                                  "case_sha256": ledger.digest(case)}})
    return {"draft": str(saved["id"]), "file": FILE, "case": case}
