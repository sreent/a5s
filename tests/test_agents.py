"""Each agent's own regression suite, from agents/<agent>/tests/ and each scenario's
scenarios/<scenario>/agents/<agent>/tests/, where the studio keeps the cases its authors write,
run against the model its release names, each in its own scenario, with an instance of it if
the settings name none, as each release is before its people approve it. A step counts only
once a run of the agent opened for it and ended in its own answer, never a5s's, such as that
nothing serves someone, or that the model isn't answering.

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

import importlib
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.cases import (  # the checks the sandbox makes of a draft's cases too
    JUDGING,
    check,
    dated,
    for_real,
    judging,
    read,
    real,
    sent_with,
    unanswered,
)
from a5s.config import load_models
from a5s.core import extractor, models, registry
from a5s.core.identity import IdentityConfig, Verifier
from a5s.core.judging import verdict
from a5s.services import context
from conftest import ROOT, SEAL_KEY, FakeModel, build_root, live_image, running, signed
from scenario_stack import running_scenario

FILLER = "We went through the open invoices, the refunds and the next payment run. " * 12
SCENARIOS = {  # each scenario whose folder brings agents of its own, and its code
    "master-data": "a5s.master_data:MasterDataScenario",
    "software-delivery": "a5s.software_delivery:SoftwareDeliveryScenario",
    "service-desk": "a5s.service_desk:ServiceDeskScenario",
}


def folders() -> list[tuple[str | None, Path]]:
    """Every agent folder a release holds: the sample's, and each scenario's own."""
    return [*((None, f) for f in sorted((ROOT / "agents").iterdir()) if f.is_dir()),
            *((f.parent.parent.name, f) for f in sorted((ROOT / "scenarios").glob("*/agents/*"))
              if f.is_dir())]


def cases() -> list:
    """Each case of every agent folder's tests, .yaml and .yml, as the studio and the sandbox
    read them: a file a5s can't read as cases fails the suite as it's collected."""
    found = []
    for scenario, folder in folders():
        tests = folder / "tests"
        paths = sorted([*tests.glob("*.yaml"), *tests.glob("*.yml")]) if tests.is_dir() else []
        for path in paths:
            for case in read(path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix()):
                where = f"{scenario}/" if scenario else ""
                case = {**case, "file": path.relative_to(folder).as_posix()}  # as the studio's
                found.append(pytest.param(scenario, folder.name, case,
                                          id=f"{where}{folder.name}/{path.stem}/{case['name']}"))
    return found


def serving(folder: Path, scenario: Any, agent: str, person: str) -> None:
    """The settings in `folder` with an instance of `agent` serving `person`, if they name none:
    in every part the scenario's instances work in, at level 1, signed by everyone there who
    approves settings, as its owners would sign one."""
    settings = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    instances = settings.setdefault("instances", {})
    if any(i.get("definition") == agent for i in instances.values()):
        return
    parts = sorted({p for i in instances.values() for p in (i.get("parts") or [])})
    instances[f"{agent}-suite"] = {"definition": agent, "serves": [person], "parts": parts, "level": 1}
    people = (yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8")) or {}).get("people") or []
    signers = tuple(p["id"] for p in people if (folder / "keys" / f"{p['id']}.key").exists()
                    and (found := scenario.person(p["id"])) is not None and registry.approves(found))
    signed(folder, settings, signers)


def answered(stack, agent: str, since: Any) -> str | None:
    """How the agent's latest run since `since` ended, if one opened."""
    with db.transaction(stack.admin) as conn:
        found = conn.execute(
            "select r.outcome from runs r join instances i on i.id = r.instance_id where "
            "i.definition = %s and r.opened_at >= %s order by r.opened_at desc limit 1",
            (agent, since)).fetchone()
    return found["outcome"] if found else None


def now(stack) -> Any:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select now() as at").fetchone()["at"]


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
           called: list[str], quiet: bool = False) -> list[str]:
    """What the release's judge finds wrong with a step whose case says what a right answer is,
    as the sandbox asks it: nothing, if it says right. `quiet` for a case kept from a real run,
    whose why may quote what was really said, which no log keeps."""
    if release.evaluation is None:
        return ["its case asks a judge, and it names none"]
    judge = load_models(ROOT / "config" / "models.yaml")[release.evaluation.judge]
    body = extractor.asked(judge.api, judge.alias, JUDGING, judging(criterion, said, reply, called))
    status, data = models.forward(judge, models.screen(judge.api, body)[0], httpx.Client(timeout=120))
    found = verdict(extractor.reply_text(judge.api, data)) if status < 400 else None
    if found is None:
        return [f"what its judge, {judge.alias}, answered doesn't read as a grade"]
    if found[0] == "right":
        return []
    return [f"its judge found it {found[0]}" + ("" if quiet else f": {found[1]}")]


def stack_for(database: str, root: Path, tmp_path: Path, scenario: str | None, agent: str,
              person: str, alias: str):
    """a5s running the agent's own scenario, with an instance of it serving `person`."""
    if scenario is None:
        from a5s.sample import SampleScenario
        folder = root / "scenarios" / "sample"
        serving(folder, SampleScenario(folder, None), agent, person)
        return running(database, root, httpx.Client(), FakeModel(), worker_image=live_image())
    if scenario not in SCENARIOS:
        pytest.fail(f"the suite doesn't know the {scenario} scenario's code: add it to SCENARIOS")
    folder = tmp_path / scenario
    shutil.copytree(ROOT / "scenarios" / scenario, folder, ignore=shutil.ignore_patterns("agents"))
    module, name = SCENARIOS[scenario].split(":")
    serving(folder, getattr(importlib.import_module(module), name)(folder, None), agent, person)
    return running_scenario(database, root, FakeModel(), SCENARIOS[scenario], scenario,
                            http=httpx.Client(), alias=alias, worker_image=live_image(),
                            scenario_folder=folder)


@pytest.mark.live
@pytest.mark.parametrize("scenario, agent, case", cases())
def test_each_agents_regression_suite(database: str, tmp_path: Path, monkeypatch,
                                      scenario: str | None, agent: str, case: dict) -> None:
    home = ROOT / "agents" if scenario is None else ROOT / "scenarios" / scenario / "agents"
    release = definitions.load(home / agent)
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    if scenario is not None and any("records" in step for step in case["steps"]):
        pytest.fail("a step that changes records first is for the sample's agents alone")
    if real(case):  # what someone really said: never to a model for made-up data alone
        approved = load_models(ROOT / "config" / "models.yaml")
        needed = set(filter(None, os.environ.get("A5S_DATA_CLASSES", "").split(",")))
        if not needed:
            pytest.fail("it was kept from a real run, and A5S_DATA_CLASSES doesn't say the "
                        "classes of the deployment's data, which a model it goes to must be "
                        "approved for")
        judge = release.evaluation.judge if release.evaluation else None
        given = [release.model, *([judge] if judge and any(
            "judged" in step for step in case["steps"]) else [])]
        if barred := [m for m in given if m not in approved
                      or not for_real(approved[m].data_classes, needed)]:
            pytest.fail(f"it was kept from a real run, and {', '.join(barred)} isn't approved "
                        f"for {', '.join(sorted(needed))} data, the deployment's "
                        "(A5S_DATA_CLASSES): a real run's case goes only to models that are")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
    with stack_for(database, root, tmp_path, scenario, agent, case.get("as", "ana"),
                   release.model) as stack:
        if scenario is None and (agent == "watcher" or case.get("with_watcher")):
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
            after, since = len(stack.ledger()), now(stack)
            if "say" in step:
                reply = stack.say(dated(step["say"]), person=person, agent=agent,
                                  files=sent_with(case))  # as the run it was kept from read
            else:  # what's due runs, and what people are told waits in their inbox
                stack.scheduler().work_due()
                reply = "\n\n".join(m["text"] for m in stack.inbox(person))
            if real(case):  # what someone really said, and its answer: never in a log
                print(f"[{n}] (a real run's words, and what it answered, aren't printed)\n")
            else:
                print(f"[{n}] {step.get('say', 'what falls due')}\n--> {reply}\n")
            called = turns_called(stack, after)
            wrong = check(step, reply, called, case.get("own_values") == "allowed")
            if why := unanswered(answered(stack, agent, since)):
                wrong.insert(0, why)  # a5s's own words pass no case's checks
            if (criterion := step.get("judged")) and why is None:  # none of its own: nothing to judge
                wrong += judged(release, str(criterion), dated(step.get("say", "what falls due")),
                                reply, called, quiet=real(case))
            problems += [f"step {n}: {w}" for w in wrong]
        for what, expected in (case.get("then") or {}).items():
            if (found := kept(stack, what)) != expected:
                problems.append(f"{what}: {found}, not {expected}")
        assert not problems, "; ".join(problems)
        assert stack.verify().ok
