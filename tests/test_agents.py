"""Each agent's own regression suite, from agents/<agent>/tests/, run against the model its
release names, as each release is before its people approve it.

Run with `uv run pytest -m live tests/test_agents.py`, with the providers' keys set. A case
says what people say to the agent, or that what's due runs, and what must follow: the tools
it uses and avoids, what it says, and what a5s keeps afterwards. Every reply is also checked
for keys, amounts and dates the agent made up, which a5s notes (core/provenance.py), unless
the case allows them. A release sets A5S_REGRESSION=required, so a missing key fails rather
than skips.
"""

import os
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.config import load_models
from a5s.services import context
from conftest import ROOT, FakeModel, build_root, running

NOTE = "(a5s: "  # how a5s starts its note on values the agent wrote itself
FILLER = "We went through the open invoices, the refunds and the next payment run. " * 12


def cases() -> list:
    found = []
    for folder in sorted((ROOT / "agents").iterdir()):
        for path in sorted((folder / "tests").glob("*.yaml")) if (folder / "tests").is_dir() else []:
            for case in yaml.safe_load(path.read_text()) or []:
                found.append(pytest.param(folder.name, case,
                                          id=f"{folder.name}/{path.stem}/{case['name']}"))
    return found


def turns_called(stack, after: int) -> list[str]:
    """The tools the agent's runs called, and a5s let them, since the ledger's entry `after`."""
    return [e["action"] for e in stack.ledger()[after:]
            if e["kind"] == "tool" and e["decision"] == "record"
            and (e.get("outcome") or {}).get("status") == "ok"]


def kept(stack, what: str):
    with db.transaction(stack.admin) as conn:
        if what == "confirmed_reminders":
            return conn.execute("select count(*) from reminders where confirmed_at is not null"
                                ).fetchone()["count"]
        if what == "kept_notes":
            return conn.execute("select count(*) from profile_notes where confirmed_at is not null "
                                "and ended_at is null").fetchone()["count"]
        if what == "drafts":
            return conn.execute("select count(*) from sample.drafts").fetchone()["count"]
        if what == "waiting_on":
            return [r["record"] for r in conn.execute(
                "select record from obligations where waiting_on is not null order by record")]
        if what == "reminders_for_others":
            return conn.execute("select count(*) from reminders where person <> 'ana'"
                                ).fetchone()["count"]
    raise ValueError(f"a case can't check {what}")


def check(step: dict, reply: str, called: list[str], allow_own: bool) -> list[str]:
    """What's wrong with a step's outcome, if anything."""
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


@pytest.mark.live
@pytest.mark.parametrize("agent, case", cases())
def test_each_agents_regression_suite(database: str, tmp_path: Path, monkeypatch, agent: str,
                                      case: dict) -> None:
    release = definitions.load(ROOT / "agents" / agent)
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        if agent == "watcher" or case.get("with_watcher"):
            stack.with_watcher()
        person, records = case.get("as", "ana"), stack.gateway.scenario._records
        stack.scheduler().due()  # the core works out what the records owe
        if budget := case.get("budget_tokens"):
            stack.gateway.definitions[agent].context.budget_tokens = budget
        with db.transaction(stack.admin) as conn:
            for turn in case.get("before") or []:
                for role, text in turn.items():
                    for said in [FILLER] * text if role == "filler" else [text]:
                        context.add_turn(conn, person=person, agent=agent,
                                         role="person" if role == "filler" else role, content=said)
        problems = []
        for n, step in enumerate(case["steps"], 1):
            if "at" in step:
                stack.at(step["at"])
            for key, fields in (step.get("records") or {}).items():
                monkeypatch.setitem(records, key, {**records[key], **fields})
            after = len(stack.ledger())
            if "say" in step:
                reply = stack.say(step["say"], person=person, agent=agent)
            else:  # what's due runs, and what people are told waits in their inbox
                stack.scheduler().work_due()
                reply = "\n\n".join(m["text"] for m in stack.inbox(person))
            print(f"[{n}] {step.get('say', 'what falls due')}\n--> {reply}\n")
            problems += [f"step {n}: {w}" for w in check(step, reply, turns_called(stack, after),
                                                          case.get("own_values") == "allowed")]
        for what, expected in (case.get("then") or {}).items():
            if (found := kept(stack, what)) != expected:
                problems.append(f"{what}: {found}, not {expected}")
        assert not problems, "; ".join(problems)
        assert stack.verify().ok
