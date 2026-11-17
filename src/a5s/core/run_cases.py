"""A run of an agent's kept as one of its test cases (docs/studio.md), so drafts are judged
against real work, not only what their authors thought of: what someone said to it, the tools
it used, and what a right answer is, in its author's words.

Only once the data protection officer agrees (`cases_from_runs` in the signed settings), since
what someone said goes into the agent's folder, which its drafts are published from; only for
someone who may author the agent and may see the run, every record it handled and every record
what was said and answered names, as the studio shows runs; and only for a run that answered
someone's message. Code masks what could say who anyone is (core/masking.py): the names and ids
of the people the run acted for and of everyone a5s serves, emails, links, numbers long enough
to be a phone's or an account's, and the keys of the records the run's words name, each
numbered, [record 1] and so on, for the author to put the sandbox's made-up records in their
place. It can't know every name someone might write, so the author reads what's left, and keeps
it only once they say it says nothing about anyone; what they write is masked again, as are the
case's name and what a right answer is. What's left is real, never made up, so the case says
it's from a run, and only the sandbox's stand-in, or a model and judge approved for every class
of the deployment's data, are ever given it: never one approved for made-up data alone
(a5s/cases.py's `for_real`). A run that read content from outside says so too, and the sandbox
and the suite mark the case's runs as it was marked.

The case goes in their draft of the agent, started from it as released if they have none, in
tests/from-runs.yaml, which its suite runs as it runs its other cases; the ledger records that
they kept it, of which run, never the words. a5s records whose words each case holds
(kept_cases), by a token the case carries in its from_run, which says nothing of whom: their
export lists it, erasure takes it out of every draft that holds it, and when they leave it's
archived with what else a5s kept for them. Once a draft is released, the case is in that
release's folder until a release without it.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import yaml
from psycopg.types.json import Jsonb

from a5s import cases, db
from a5s.contract import DataProtection, Person, Scenario
from a5s.core import drafts, ledger, masking, registry, studio

FILE = cases.FROM_RUNS  # in the agent's folder, beside its other cases
ABOUT = ("# Test cases kept from real runs, in the studio: what was said, masked by code and\n"
         "# checked by whoever kept it, and the tools the agent used. Put the sandbox's made-up\n"
         "# records in place of the real ones a case names, and add what it must say.\n")
TOKEN = re.compile(r"k-[0-9a-f]{12}")  # what a kept case carries in its from_run


class Refused(Exception):
    """Why a run can't be kept as a test case."""


def mask(conn: db.Connection, scenario: Scenario, run: dict, *texts: str) -> Any:
    """How a run's words are masked, for each of these texts and what the author writes: whose
    names, everyone a5s serves among them, and its records' keys, numbered the same in each."""
    people = [*(run.get("acts_for") or []), run.get("sender"), *masking.known(conn, scenario)]
    numbers = masking.numbered(scenario, *texts)
    return lambda text: masking.mask(text, scenario, people, records=numbers)


def _run(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
         definitions: dict[str, Any], choices: DataProtection) -> tuple[dict, dict, str, str]:
    """A run someone may keep as a test case: what the studio shows them of it, its row, with
    who said what started it, what they said, and what the agent answered. Refused, saying why,
    if they may not: as the run's page is, for one of an instance serving too few people to show
    its runs one by one, or one whose words name a record they may not see."""
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
    row = conn.execute("select trigger, acts_for, read_outside from runs where id = %s::uuid",
                       (run_id,)).fetchone()
    trigger = (row["trigger"] if row else None) or {}
    if trigger.get("kind") != "message" or not trigger.get("inbound"):
        raise Refused("only a run that answered someone's message makes a test case")
    said = conn.execute("select person, text from inbound where id = %s::uuid",
                        (trigger["inbound"],)).fetchone()
    if said is None:
        raise Refused("what was said in it is no longer kept")
    answered = "\n".join(r["text"] for r in conn.execute(
        "select text from outbox where run_id = %s::uuid order by id", (run_id,)).fetchall())
    if not all(scenario.sees(viewer.id, k) for k in studio.named(
            scenario, f"{said['text']}\n{answered}")):  # one the agent drew from what it was told
        raise Refused("there's no such run that you may see")
    return shown, {**(dict(row) if row else {}), "sender": said["person"]}, str(said["text"]), \
        answered


def proposed(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
             definitions: dict[str, Any], choices: DataProtection) -> dict:
    """A run as a test case, for its author to check and keep: what was said and what the
    agent answered, masked; what code masked; and the tools it used, which a5s let it, or held
    for someone to decide."""
    shown, row, said, answered = _run(conn, scenario, viewer, run_id, definitions, choices)
    masked_by = mask(conn, scenario, row, said, answered)
    say, masked = masked_by(said)
    answer, _ = masked_by(answered)
    uses = sorted({c["tool"] for c in shown["calls"] if c["decision"] in ("allow", "hold")})
    return {"run": run_id, "agent": shown["agent"], "say": say[:cases.SAY],
            "answer": answer, "masked": masked, "uses": uses,
            "read_outside": bool(row.get("read_outside"))}


def keep(conn: db.Connection, scenario: Scenario, viewer: Person, run_id: str,
         definitions: dict[str, Any], choices: DataProtection, agents_dir: Any, *, name: str,
         as_: str,
         say: str, judged: str | None, checked: bool) -> dict:
    """Keep a run as a test case in someone's draft of its agent, started from it as released
    if they have none, in the caller's transaction, with the ledger's word on it: what they
    say is masked again, as it was offered. The draft, and the case as kept."""
    shown, row, said_then, answered = _run(conn, scenario, viewer, run_id, definitions, choices)
    if not checked:
        raise Refused("say first that you've read it, and it says nothing about anyone")
    masked_by = mask(conn, scenario, row, said_then, answered)  # as it was offered
    name = masked_by(" ".join(name.split())[:80])[0]
    if not name or not as_.strip():
        raise Refused("name the case, and the made-up person who says it")
    said, _ = masked_by(say.strip())
    if not said:
        raise Refused("say what's said to it")
    step: dict[str, Any] = {"say": said[:cases.SAY]}
    if uses := sorted({c["tool"] for c in shown["calls"] if c["decision"] in ("allow", "hold")}):
        step["uses"] = uses
    if judged and judged.strip():
        step["judged"] = masked_by(" ".join(judged.split())[:1000])[0]
    token = f"k-{secrets.token_hex(6)}"  # whose words it holds, which only a5s links back
    case = {"name": name, "as": as_.strip()[:80], "from_run": token,
            **({"read_outside": True} if row.get("read_outside") else {}), "steps": [step]}
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
    conn.execute("insert into kept_cases (token, agent, name, run_id, person, acts_for, kept_by) "
                 "values (%s, %s, %s, %s::uuid, %s, %s, %s)",
                 (token, agent, name, run_id, row.get("sender") or "", list(row.get("acts_for") or []),
                  viewer.id))
    ledger.append(conn, {"kind": "admin", "action": "case from run", "run": run_id,
                         "instance": shown["instance"], "acts_for": [], "decision": "record",
                         "args": {"agent": agent, "draft": str(saved["id"]), "by": viewer.id,
                                  "case_sha256": ledger.digest(case)}})
    return {"draft": str(saved["id"]), "file": FILE, "case": case}


def _in(files: dict) -> list:
    try:
        kept = yaml.safe_load(files.get(FILE) or "[]") or []
    except yaml.YAMLError:
        return []
    return kept if isinstance(kept, list) else []


def _holding(conn: db.Connection, tokens: list[str]) -> list[dict]:
    """The drafts that hold any of these cases, by their tokens: whoever's they are now, and
    copies of them too."""
    return conn.execute("select id, agent, files from agent_drafts where files ->> %s is not null "
                        "and files ->> %s ~ %s", (FILE, FILE, "|".join(map(re.escape, tokens)))
                        ).fetchall() if tokens else []


def held(conn: db.Connection, people: list[str]) -> list[dict]:
    """The cases kept from runs that hold these people's words, for their export: each one's
    agent and name, when it was kept, and what it says in each draft that holds it still."""
    rows = conn.execute("select * from kept_cases where person = any(%s) or acts_for && %s::text[] "
                        "order by kept_at, token", (people, people)).fetchall()
    drafts_now = _holding(conn, [r["token"] for r in rows])
    return [{"agent": r["agent"], "case": r["name"], "kept_at": r["kept_at"].isoformat(),
             "says": [s.get("say") for d in drafts_now for c in _in(d["files"])
                      if isinstance(c, dict) and c.get("from_run") == r["token"]
                      for s in c.get("steps") or [] if isinstance(s, dict) and s.get("say")]}
            for r in rows]


def forget(conn: db.Connection, people: list[str]) -> int:
    """Take the cases that hold these people's words out of every draft that holds them, in the
    caller's transaction, and what a5s kept of whose they were: how many cases went."""
    rows = conn.execute("delete from kept_cases where person = any(%s) or acts_for && %s::text[] "
                        "returning token", (people, people)).fetchall()
    tokens = {r["token"] for r in rows}
    for draft in _holding(conn, sorted(tokens)):
        kept = _in(draft["files"])
        left = [c for c in kept if not (isinstance(c, dict) and c.get("from_run") in tokens)]
        if len(left) != len(kept):
            files = {**draft["files"], FILE: ABOUT + yaml.safe_dump(left, sort_keys=False,
                                                                    allow_unicode=True)}
            conn.execute("update agent_drafts set files = %s, updated_at = now() where id = %s",
                         (Jsonb(files), draft["id"]))
    return len(tokens)
