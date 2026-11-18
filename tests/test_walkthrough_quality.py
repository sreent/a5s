"""Phase 5's walk-through of master data's data quality watcher (docs/phase-5.md, step 5): built again
in the studio, from nothing, by the owner of the data team's agents, with what it may do held to the
hand-written watcher's, on a5s as the data team deploys it, SAP behind its MCP server.

Ines builds quality-helper: it reads only, and tells each person it serves, every
working morning, how their data object stands against its target, and what changed in the change
requests that wait on them, from what code works out. Rhea and Ines sign the release that adds it.
The owners of the data objects put it to work in material data, serving Mo, who owns it. On a
working morning, Mo reads its report in the chat. Ken, of assurance, reads the run.

    A5S_GUIDE=docs/guides uv run pytest tests/test_walkthrough_quality.py
"""

from __future__ import annotations

import shutil

import yaml
from playwright.sync_api import TimeoutError as NotYet

from a5s import db
from a5s.core import drafts
from conftest import PROVIDER_KEY, ROOT, build_root, deciding, free_port, serve
from fake_github import FakeGitHub
from scenario_stack import running_scenario
from test_studio_authoring import kept
from test_walkthrough_desk import able, definition
from test_walkthrough_master_data import APPROVERS, MASTER, approve
from walkthrough import (
    On,
    Walk,
    answering,
    deployed,
    merged,
    owned,
    released,
    signed_and_recorded,
    walking_on,
)

AGENT = "quality-helper"
TOOLS = ("search_records", "get_record", "check_quality")
REPORTS = ("quality", "records")
MORNING = "2026-11-04T09:30:00+00:00"  # a working morning, at Mo's digest time
TOLD = ("Mo, material data has 2 of 3 records passing, 66.6%, below its target of 95%, and owes "
        "a fix by Fri 20 Nov. Nothing waits on you in the requests.")
INSTRUCTIONS = (ROOT / "scenarios" / "master-data" / "agents" / "mdg-watcher" / "AGENTS.md"
                ).read_text().replace("# Data quality watcher", "# Quality helper", 1)


def reported(body: dict) -> str | None:
    """What it says, scripted here, when a5s gives it the facts of someone's records for their
    digest: Mo's report, and a line for anyone else's, whenever the morning's runs come."""
    last = str((body.get("messages") or [{}])[-1].get("content") or "")
    if "from a5s" not in last:
        return None
    return TOLD if "Tell Mo Hassan" in last else "Nothing new in your records today."


def built(walk: Walk, stack, url: str, forge: FakeGitHub) -> tuple[dict, str, dict]:
    """Ines builds quality-helper in the studio from nothing, and publishes it: its definition, as
    a5s keeps it, its draft, and its pull request."""
    page = walk.as_("ines", f"{url}/studio/new")
    with walk.step("Ines, who owns the data team's agents, starts another, quality-helper, from the "
                   "blank start.", page):
        page.wait_for_selector(".template >> text=blank", timeout=30000)
        page.fill("#agent-name", AGENT)
        page.click(".template:has-text('blank')")
        page.click("#make")
        page.wait_for_selector(".flow-canvas [data-step=agent]", timeout=30000)
        kept(page)
    with walk.step("From the palette, she gives it the tools that read: SAP's change requests and "
                   "master records, and code's measure of a data object's quality.", page):
        for tool in TOOLS:
            page.click(f".fd-palette [data-tool={tool}]")
            page.wait_for_selector(f".flow-canvas [data-step='tool:{tool}']", timeout=30000)
            kept(page)
    with walk.step("What starts its runs: messages, on Matrix too, and a daily report on each data "
                   "object's quality, and on the change requests, which tells each person it serves "
                   "what changed in their own.", page):
        for key in ("recall", "digest-time"):
            page.click(f".fd-palette [data-ability={key}]")
            kept(page)
        page.click("[data-step=messages]")
        page.check(".wb-inspector label.choice:has-text('Matrix') input")
        kept(page)
        for n, kind in enumerate(REPORTS):
            page.click(f".fd-palette [data-report={kind}]")
            page.wait_for_selector(f".flow-canvas [data-step='report:{n}']", timeout=30000)
            kept(page)
    with walk.step("On the agent itself: whom it works for, what it does, and how far it may act: it "
                   "reads only, and a5s refuses anything else it asks for.", page):
        page.click("[data-step=agent]")
        page.fill("#works-for", "The owners of each data object, and the data stewards")
        page.fill("#does", "Tells each data object's owner, in their daily digest, how its quality stands "
                           "against their target and what changed in it, and each person what changed in "
                           "the change requests that wait on them. It reads, and changes nothing.")
        page.select_option("#level-start", "0")
        page.select_option("#level-max", "0")
        kept(page)
    with walk.step("Its budgets, in a5s's checks: less than an assistant's, since each report only "
                   "puts what code worked out into words.", page):
        page.click("[data-step=checks]")
        page.fill("#budget-run", "150000")
        kept(page)
        page.fill("#budget-person", "700000")
        kept(page)
        page.fill("#budget-context", "16000")
        kept(page)
    with walk.step("She plans its first instance in material data, serving Mo, who owns it.", page):
        page.click("[data-step=agent]")
        page.check("#plan-title ~ fieldset label:has-text('material') input")
        kept(page)
        page.check("#plan-title ~ fieldset label:has-text('Mo Hassan') input")
        kept(page)
    with walk.step("She tells it how to work, in its instructions, as the team's own watcher's.", page):
        page.click(".wb-bar .modes button:has-text('Instructions')")
        page.fill("#instructions", INSTRUCTIONS)
        kept(page)
        page.click(".wb-bar .modes button:has-text('Design')")
        page.wait_for_selector("#problem-count >> text=No problems", timeout=30000)
    rebuilt = definition(stack, page)
    with walk.step("Nothing stops its release. Ines publishes its pull request.", page):
        page.click("#to-publish")
        page.click("#publish")
        page.wait_for_selector("#user-code", timeout=30000)
        forge.grant(page.inner_text("#user-code"), "ines-gh")
        page.wait_for_selector("#published >> text=its pull request", timeout=30000)
    [pull] = forge.pulls
    return rebuilt, page.evaluate("location.pathname"), pull


def at_work(walk: Walk, stack, url: str, draft: str) -> str:
    """Ines puts it to work from its plan, and the owners of the data objects approve it: its
    instance's id."""
    page = walk.as_("ines", f"{url}{draft}")
    with walk.step("Its release signed and deployed, Ines puts it to work from its plan.", page):
        page.click("#put-to-work")
        page.wait_for_selector("#add-instance", timeout=30000)
        assert page.input_value("#add-agent") == AGENT
        page.click("#add-it")
        page.click("#review")
        page.wait_for_selector("#reviewed-changes li", timeout=30000)
        assert page.inner_text("#reviewed-approvers") == (
            f"It needs the approval of {', '.join(name for _, name in APPROVERS)}.")
        page.click("#send")
        page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    stack.scheduler().apply_approved()
    for n, (person, _) in enumerate(APPROVERS):
        page = walk.as_(person, f"{url}/studio/")
        if n == 0:
            with walk.step("The owners of the four data objects approve it, each signed in afresh for "
                           "that version alone.", page):
                approve(page, "Ines Duarte")
        else:
            approve(page, "Ines Duarte")
        stack.scheduler().apply_approved()
    with db.transaction(stack.admin) as conn:
        [instance] = [r["id"] for r in conn.execute("select id from instances where definition = %s",
                                                    (AGENT,))]
    return instance


def reported_to_mo(walk: Walk, stack, url: str, on: On) -> str:
    """On a working morning, Mo reads its report in the chat: the run's id."""
    stack.at(MORNING)
    stack.scheduler().work_due()
    page = walk.as_("mo", f"{url}/chat/")
    with walk.step("On a working morning, Mo reads its report in his day from a5s, in the chat: how "
                   "material data stands against its target, from what code measured, and that nothing "
                   "waits on him.", page):
        for _ in range(3 if on.live else 0):  # a real model's run can fail, and is due again at the
            try:  # scheduler's next sweep, a minute on, as here: his day waits for all of it
                page.wait_for_selector("li >> text=From the quality-helper", timeout=30000)
                break
            except NotYet:
                stack.scheduler().work_due()
                page.reload()
        page.wait_for_selector("li >> text=From the quality-helper", timeout=30000)
        digest = page.inner_text("li:has-text('From the quality-helper')")
        own = digest.partition("From the quality-helper")[2].split("\nFrom the ")[0]  # its alone
        assert own.strip() and (on.live or TOLD in own), digest
    asked = [r["body"]["messages"][-1]["content"] for r in stack.model.requests
             if "Tell Mo Hassan" in str(r["body"]["messages"][-1].get("content"))
             and "# Quality helper" in str(r["body"]["messages"][0].get("content"))]  # its own run's
    # code's facts, in its own run's request: a real model's requests, the walk-through never sees
    assert on.live or any("DQ-material" in a for a in asked), asked
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select r.id::text as id from runs r join instances i on i.id = r.instance_id "
                             "where i.definition = %s", (AGENT,)).fetchall()
    return run["id"]


def read_run(walk: Walk, url: str, instance: str) -> None:
    page = walk.as_("ken", f"{url}/audit/")
    with walk.step("Ken, of assurance, reads the run in the audit trail: a report, by an agent that "
                   "reads only, which called no tool that changes anything.", page):
        page.wait_for_selector("#find:not([hidden])", timeout=30000)
        page.fill("#instance", instance)
        page.click("#search")
        page.wait_for_selector("#entries li", timeout=30000)


def test_the_data_quality_watcher_is_built_again_and_reports_to_its_owner(
        database, tmp_path, provider, browser, monkeypatch, capsys):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    on = walking_on(reported)
    model, http = on.model, on.http
    root = build_root(tmp_path, on.alias, on.models)
    team = root / "scenarios" / "master-data"
    shutil.copytree(ROOT / "scenarios" / "master-data", team)
    walk = Walk("data-quality", "The data quality watcher, built again in the studio", browser, provider)
    agents = ROOT / "scenarios" / "master-data" / "agents"
    forge = FakeGitHub({f"scenario-agents/{name}/{path}": text for name in ("mdg-assistant", "mdg-watcher")
                        for path, text in drafts.folder_files(agents / name).items()})
    with serve(forge.app(), free_port()) as forge_url:
        forge.url = forge_url
        with running_scenario(database, root, model, MASTER, "master-data", http=http,
                              alias=on.alias, scenario_folder=team) as stack:
            deployed(stack, forge)
            said = released(stack, tmp_path / "first", monkeypatch, capsys)
            said = signed_and_recorded(said, capsys, "rhea", "ken", "tao", "ines")
            assert said.rstrip().endswith("Approved here."), said
            with deciding(stack, provider) as url:
                rebuilt, draft, pull = built(walk, stack, url, forge)
        hand_written = yaml.safe_load((agents / "mdg-watcher" / "agent.yaml").read_text())
        with walk.step("What quality-helper may do, what starts it and what it reports on is what the "
                       "hand-written watcher's definition gives it, in the studio's words: nothing "
                       "more, and nothing missing."):
            assert able(rebuilt) == {**able(hand_written), "starts": able(rebuilt)["starts"]}, (
                able(rebuilt), able(hand_written))
            assert rebuilt["reports"] == hand_written["reports"]
        with walk.step("The team merges its pull request, and the directory names Ines its owner."):
            merged(stack, forge.files(pull["head"]), AGENT)
            owned(stack.cfg.scenario_dir, "ines", AGENT)
        with running_scenario(database, root, model, MASTER, "master-data", http=http,
                              alias=on.alias, scenario_folder=team) as stack:
            deployed(stack, forge)
            with walk.step("Deployed again, Rhea and Ines sign the release that adds it, and the team "
                           "records it: it's approved, and a5s runs it."):
                said = released(stack, tmp_path / "second", monkeypatch, capsys)
                said = signed_and_recorded(said, capsys, "rhea", "ines")
                assert said.rstrip().endswith("Approved here."), said
            with deciding(stack, provider) as url, answering(stack):
                instance = at_work(walk, stack, url, draft)
                reported_to_mo(walk, stack, url, on)
                read_run(walk, url, instance)
    walk.guide("Master data's data quality watcher, built again from nothing in the studio, as "
               "quality-helper, by the data team's own people: it only reads, and each working morning "
               "tells the people it serves how their data object stands and what changed, from what "
               "code works out. tests/test_walkthrough_quality.py takes these steps, and made these "
               "pictures.")
