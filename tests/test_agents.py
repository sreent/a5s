"""Each agent's own regression suite, from agents/<agent>/tests/, run against the model its
release names, as each release is before its people approve it.

Run with `uv run pytest -m live tests/test_agents.py`, with the providers' keys set. With
A5S_TEST_WORKER_IMAGE naming a5s's image, such as a5s:dev, each run goes to a worker from it,
in a container of its own, as a pool's pods run, with no secrets and the model reached only
through the core (conftest.py's `contained`), as a release runs every live suite. A case
says what people say to the agent, or that what's due runs, and what must follow: the tools
it uses and avoids, what it says, and what a5s keeps afterwards, and, where it can be right in
more than one way, what a right answer is, which the agent's judge grades. Every reply is also checked
for keys, amounts and dates the agent made up, which a5s notes (core/provenance.py), unless
the case allows them. A release sets A5S_REGRESSION=required, so a missing key fails rather
than skips.
"""

import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.cases import (  # the checks the sandbox makes of a draft's cases too
    JUDGING,
    check,
    dated,
    judging,
)
from a5s.config import load_models
from a5s.core import extractor, models
from a5s.core.identity import IdentityConfig, Verifier
from a5s.core.judging import verdict
from a5s.services import context
from conftest import ROOT, SEAL_KEY, FakeModel, build_root, live_image, running

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
    """The tools the agent's runs called, and a5s let them, or held them for a person to
    decide, since the ledger's entry `after`."""
    return [e["action"] for e in stack.ledger()[after:]
            if e["kind"] == "tool" and (e["decision"] == "hold" or (
                e["decision"] == "record" and (e.get("outcome") or {}).get("status") == "ok"))]


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
        if what == "held":
            return conn.execute("select count(*) from proposals where status = 'waiting'"
                                ).fetchone()["count"]
    raise ValueError(f"a case can't check {what}")


def judged(release: definitions.Definition, criterion: str, said: str, reply: str,
           called: list[str]) -> list[str]:
    """What the release's judge finds wrong with a step whose case says what a right answer is,
    as the sandbox asks it: nothing, if it says right."""
    if release.evaluation is None:
        return ["its case asks a judge, and it names none"]
    judge = load_models(ROOT / "config" / "models.yaml")[release.evaluation.judge]
    body = extractor.asked(judge.api, judge.alias, JUDGING, judging(criterion, said, reply, called))
    status, data = models.forward(judge, models.screen(judge.api, body)[0], httpx.Client(timeout=120))
    found = verdict(extractor.reply_text(judge.api, data)) if status < 400 else None
    if found is None:
        return [f"what its judge, {judge.alias}, answered doesn't read as a grade"]
    return [] if found[0] == "right" else [f"its judge found it {found[0]}: {found[1]}"]


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
    with running(database, root, httpx.Client(), FakeModel(), worker_image=live_image()) as stack:
        if agent == "watcher" or case.get("with_watcher"):
            stack.with_watcher()
        if case.get("deciding"):  # a held change needs the page where its deciders decide
            stack.gateway.identity = Verifier(IdentityConfig(issuer="https://id.a5s.test",
                                                             audience="a5s-web"))
            stack.gateway.cfg = replace(stack.gateway.cfg, webchat_client_id="a5s-web",
                                        seal_keys=(SEAL_KEY,), public_url="https://a5s.test")
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
                reply = stack.say(dated(step["say"]), person=person, agent=agent)
            else:  # what's due runs, and what people are told waits in their inbox
                stack.scheduler().work_due()
                reply = "\n\n".join(m["text"] for m in stack.inbox(person))
            print(f"[{n}] {step.get('say', 'what falls due')}\n--> {reply}\n")
            called = turns_called(stack, after)
            wrong = check(step, reply, called, case.get("own_values") == "allowed")
            if criterion := step.get("judged"):
                wrong += judged(release, str(criterion), dated(step.get("say", "what falls due")),
                                reply, called)
            problems += [f"step {n}: {w}" for w in wrong]
        for what, expected in (case.get("then") or {}).items():
            if (found := kept(stack, what)) != expected:
                problems.append(f"{what}: {found}, not {expected}")
        assert not problems, "; ".join(problems)
        assert stack.verify().ok
