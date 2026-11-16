"""Phase 5's walk-through of master data (docs/phase-5.md, step 5): its assistant built again in the
studio, from nothing, by its owner, with what it may do held to the hand-written one's, on a5s as
the data team deploys it, SAP behind its MCP server; a test case its judge grades; and one type of
correction, in one part, taken to level 2 from graded samples, as its owners' settings give it.

Ines owns the team's agents and builds mdg-helper. She tries it in the sandbox as Raf, and keeps
what he said as a test case, with what a right answer is, which its judge grades. Rhea approves
releases from outside the team that runs a5s, and signs the release that adds it, with Ines. The
owners of the data objects put it to work in material data, which then needs 95% accuracy
before level 2. Raf gives it the base unit his new material lacks:
the correction waits for Mo, who owns material data, who approves it, and SAP makes it. Over the
quarter, Mel, who grades the agents' work in material data, grades its corrections there, and the
evidence raises a5s's cap; the owners give it level 2 for corrections in material, as a version of
the settings; and Raf's next correction is made alone, and Mo hears of it. Ken, of assurance,
follows it all in the audit trail.

    A5S_GUIDE=docs/guides uv run pytest tests/test_walkthrough_master_data.py
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace

import yaml

from a5s import cases, db, sandbox
from a5s.config import Config
from a5s.core import drafts, judging
from conftest import PROVIDER_KEY, ROOT, build_root, deciding, free_port, serve
from fake_github import FakeGitHub
from scenario_stack import running_scenario
from test_studio_authoring import kept
from test_walkthrough_desk import able, definition
from test_walkthrough_resolver import files_of
from walkthrough import (
    On,
    Walk,
    answering,
    decided_in_trail,
    deployed,
    merged,
    owned,
    released,
    says,
    signed_and_recorded,
    walking_on,
)

AGENT = "mdg-helper"
MASTER = "a5s.master_data:MasterDataScenario"
TOOLS = ("search_records", "get_record", "get_letters", "check_request", "check_quality",
         "search_knowledge", "read_knowledge", "create_draft", "correct_value")
ABILITIES = ("reminders", "recall", "tasks", "digest-time", "how-i-work")
SAID = "CR0000104's base unit is EA: we keep nuts in each."
PROPOSED = "I've proposed EA as CR0000104's base unit: it waits for Mo Hassan, who owns material data."
CASE = "a base unit Raf gives is proposed, for Mo to decide"
RIGHT = ('It proposes "EA" as CR0000104\'s base unit, with correct_value, and says "Mo Hassan" decides '
         "it, never that it's made.")
RUBRIC = "A correction proposes only what the requester or a steward gave, for a field that isn't sensitive."
APPROVERS = (("carl", "Carl Dunn"), ("mo", "Mo Hassan"), ("una", "Una Novak"), ("pia", "Pia Weber"))
GRADED = 88  # what a 95% threshold needs, with no errors (core/samples.py)
INSTRUCTIONS = (ROOT / "scenarios" / "master-data" / "agents" / "mdg-assistant" / "AGENTS.md"
                ).read_text().replace("# Master data assistant", "# Master data helper", 1)


def judged(body: dict) -> str | None:
    """The team's model as a judge, which the walk-through scripts apart from what the agent
    says, since a5s asks it whenever a sweep comes round: right, of the case's step and of each
    sample of its corrections, as people found them."""
    first = str((body.get("messages") or [{}])[0].get("content") or "")
    if first == cases.JUDGING:
        return json.dumps({"grade": "right", "why": "It proposes the base unit Raf gave, for Mo "
                                                    "Hassan to decide, and doesn't say it's made."})
    if first == judging.SYSTEM:
        return json.dumps({"grade": "right", "why": "A base unit the requester gave, which isn't "
                                                    "a sensitive field."})
    return None


def built(walk: Walk, stack, url: str, forge: FakeGitHub, on: On) -> tuple[dict, str, dict]:
    """Ines builds mdg-helper in the studio from nothing, tries it in the sandbox, keeps a test case
    its judge grades, and publishes it: its definition, as a5s keeps it, its draft, and its pull
    request."""
    page = walk.as_("ines", f"{url}/studio/new")
    with walk.step("Ines, who owns the data team's agents, starts a new one, mdg-helper, from the "
                   "blank start.", page):
        page.wait_for_selector(".template >> text=blank", timeout=30000)
        page.fill("#agent-name", AGENT)
        page.click(".template:has-text('blank')")
        page.click("#make")
        page.wait_for_selector(".flow-canvas [data-step=agent]", timeout=30000)
        kept(page)
    with walk.step("From the palette, she gives it SAP's tools, which read change requests, master "
                   "records and what suppliers sent, code's checks of a request and of a data "
                   "object's quality, the handbook's, the one that saves a draft, and the one change "
                   "it may ask for: a correction to what a request proposes.", page):
        for tool in TOOLS:
            page.click(f".fd-palette [data-tool={tool}]")
            page.wait_for_selector(f".flow-canvas [data-step='tool:{tool}']", timeout=30000)
            kept(page)
    with walk.step("She gives it a5s's abilities the team needs, long tasks among them, and what starts "
                   "its runs: messages, on Matrix too, and the next steps and quality fixes people owe.",
                   page):
        for key in ABILITIES:
            page.click(f".fd-palette [data-ability={key}]")
            kept(page)
        page.click("[data-step=messages]")
        page.check(".wb-inspector label.choice:has-text('Matrix') input")
        kept(page)
        for kind in ("records", "quality"):
            page.click(f".fd-palette [data-owed={kind}]")
            page.wait_for_selector(".flow-canvas [data-step=obligations]", timeout=30000)
            kept(page)
    with walk.step("On the agent itself: whom it works for, what it does, and its levels. It starts at "
                   "level 1, and its release allows level 2, which only its owners' settings and "
                   "graded samples give, a type of change in a part at a time.", page):
        page.click("[data-step=agent]")
        page.fill("#works-for", "Requesters, data stewards and data object owners, within SAP master "
                                "data governance")
        page.fill("#does", "Checks change requests and data quality by code, answers from SAP's master "
                           "data and the governance handbook, proposes corrections for each data "
                           "object's owner to decide, saves drafts such as a note to a requester or a "
                           "quality report, and chases the next step of each request, and each owner's "
                           "quality fixes, as they fall due.")
        page.select_option("#level-max", "2")
        page.select_option("#level-start", "1")
        kept(page)
    with walk.step("Its judge, beside people's grades: the team's approved model, with what a right "
                   "correction is, in her words. A judge never moves a level: people's grades do.", page):
        page.click("[data-step=model]")
        page.select_option("#design-judge", on.alias)
        kept(page)
        page.fill("#design-rubric", RUBRIC)
        kept(page)
    with walk.step("She plans its first instance in material data, serving the plant: each correction "
                   "it asks for there waits for Mo, who owns material data.", page):
        page.click("[data-step=agent]")
        page.check("#plan-title ~ fieldset label:has-text('material') input")
        kept(page)
        page.check("#plan-title ~ fieldset label:has-text('team:plant') input")
        kept(page)
        page.click(".wb-inspector button:has-text('The draft as a whole')")
        assert "Mo Hassan" in page.inner_text("#decides li:has-text('material')")
    with walk.step("She tells it how to work, in its instructions, as the team's own assistant's.", page):
        page.click(".wb-bar .modes button:has-text('Instructions')")
        page.fill("#instructions", INSTRUCTIONS)
        kept(page)
        page.click(".wb-bar .modes button:has-text('Design')")
        page.wait_for_selector("#problem-count >> text=No problems", timeout=30000)
    stack.model.reply(None, ("correct_value", {"key": "CR0000104", "base_unit": "EA"}))
    stack.model.reply(PROPOSED)
    with walk.step("She tries it in the sandbox as Raf, on SAP's made-up requests and the team's "
                   "model: it proposes the base unit he gives, which waits there, as it would, for "
                   "Mo, who owns material data.", page):
        page.click("#try-it")
        page.wait_for_selector("#try-as option[value=raf]", state="attached", timeout=30000)
        page.select_option("#try-as", "raf")
        page.select_option("#try-model", on.alias)
        page.fill("#try-text", SAID)
        page.click(".try-say button[type=submit]")
        page.wait_for_selector(".try-answer .try-reply", timeout=180000)
        assert on.live or "it waits for Mo Hassan" in page.inner_text(".try-answer .try-reply")
        assert "hold" in page.inner_text(".try-answer .run-calls")
    with walk.step("She keeps what he said as a test case, with what a right answer is, in her words, "
                   "for its judge to grade beside the case's checks, since a correction can be right "
                   "in more than one way.", page):
        page.fill("#case-name", CASE)
        page.fill("#judged", RIGHT)
        page.click("#keep-case")
        page.wait_for_selector("#case-kept", timeout=30000)
        kept(page)
    stack.model.reply(None, ("correct_value", {"key": "CR0000104", "base_unit": "EA"}))
    stack.model.reply(PROPOSED)
    with walk.step("She runs its cases there: it asks for the correction again, its judge finds the "
                   "answer right, and the case passes.", page):
        page.click("#run-cases")
        page.wait_for_selector("#cases-summary >> text=1 of 1 passed", timeout=300000)
        page.click("#cases details.sent summary")
        assert f"Its judge, {on.alias}, found it right" in page.inner_text("#cases .case-judged")
    [case] = yaml.safe_load(files_of(stack, page)["tests/tried.yaml"])
    assert (case["name"], case["as"]) == (CASE, "raf"), case
    [step] = case["steps"]  # a real model may look the request up first
    assert (step["say"], step["judged"]) == (SAID, RIGHT) and "correct_value" in step["uses"], case
    rebuilt = definition(stack, page)
    page.click(".wb-bar .modes button:has-text('Design')")
    with walk.step("Nothing stops its release. Ines publishes its pull request.", page):
        page.click("#to-publish")
        page.click("#publish")
        page.wait_for_selector("#user-code", timeout=30000)
        forge.grant(page.inner_text("#user-code"), "ines-gh")
        page.wait_for_selector("#published >> text=its pull request", timeout=30000)
    [pull] = forge.pulls
    return rebuilt, page.evaluate("location.pathname"), pull


def approved_by_all(walk: Walk, stack, url: str, asker: str) -> None:
    """A version of the settings, approved by the owner of each data object, each signed in
    afresh for that version alone."""
    for n, (person, name) in enumerate(APPROVERS):
        page = walk.as_(person, f"{url}/studio/")
        if n == 0:
            with walk.step(f"{name}, who owns customer data, approves it, signed in afresh for that "
                           "version alone, and so do Mo, Una and Pia, who own the other data objects: "
                           "a version counts once the owner of each part its instances work in has.",
                           page):
                approve(page, asker)
        else:
            approve(page, asker)
        stack.scheduler().apply_approved()


def approve(page, asker: str) -> None:
    page.click("#waiting a:has-text('waits for your approval')")
    page.wait_for_selector(f"#asker >> text={asker} asked for it", timeout=30000)
    page.click("#approve")
    page.wait_for_selector("#status >> text=You approved version", timeout=30000)


def at_work(walk: Walk, stack, url: str, draft: str) -> str:
    """Ines puts it to work from its plan, asking for 95% accuracy in material data before level
    2, and the owners approve it: its instance's id."""
    page = walk.as_("ines", f"{url}{draft}")
    with walk.step("Its release signed and deployed, Ines puts it to work from its plan, in material "
                   "data. She asks there for 95% accuracy before a5s would ever raise its cap on a "
                   "type of change: a part with none never earns level 2.", page):
        page.click("#put-to-work")
        page.wait_for_selector("#add-instance", timeout=30000)
        assert page.input_value("#add-agent") == AGENT
        page.click("#add-it")
        page.fill("[aria-label='The accuracy material needs, in percent']", "95")
        page.click("#review")
        page.wait_for_selector("#reviewed-changes li", timeout=30000)
        assert page.inner_text("#reviewed-approvers") == (
            f"It needs the approval of {', '.join(name for _, name in APPROVERS)}.")
        page.click("#send")
        page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    stack.scheduler().apply_approved()
    approved_by_all(walk, stack, url, "Ines Duarte")
    with db.transaction(stack.admin) as conn:
        [instance] = [r["id"] for r in conn.execute("select id from instances where definition = %s",
                                                    (AGENT,))]
    return instance


def corrected(walk: Walk, stack, url: str) -> None:
    """Raf gives it a base unit; the correction waits for Mo, who approves it; SAP makes it."""
    stack.model.reply(None, ("correct_value", {"key": "CR0000104", "base_unit": "EA"}))
    stack.model.reply(PROPOSED)
    page = walk.as_("raf", f"{url}/chat/")
    with walk.step("Raf, at the plant, gives it the base unit his new material lacks. The correction "
                   "waits for Mo, who owns material data.", page):
        says(page, AGENT, SAID, "it waits for Mo Hassan")
    page = walk.as_("mo", f"{url}/studio/")
    with walk.step("Mo finds it waiting for his decision, reads it in a5s's own words, with CR0000104 "
                   "as it stood, and approves it, signed in afresh for that alone. a5s asks SAP to "
                   "make it, and the request, which needed only that, goes back to its steward.", page):
        page.click("#waiting a:has-text('waits for your decision')")
        page.wait_for_selector(".approval >> text=CR0000104", timeout=30000)
        assert page.inner_text(".approval h2").startswith(
            "Propose a correction to what a change request proposes")
        page.click(".approval button >> text=Approve")
        page.wait_for_selector("#status >> text=You approved P-1", timeout=30000)
    stack.scheduler().decided()
    now = stack.gateway.scenario.request("CR0000104")  # as SAP holds it
    assert (now["values"]["base_unit"], now["status"]) == ("EA", "in review"), now


def quarter(stack) -> None:
    """The quarter's other corrections in material data, like Raf's, which Mo decided, each drawn
    as a sample as his was: made up here, as a quarter's work would come."""
    with db.transaction(stack.admin) as conn:
        [real] = conn.execute("select id from samples where action = 'correct-value'").fetchall()
        for _ in range(GRADED - 1):
            conn.execute(
                "insert into samples (scenario, kind, proposal_id, run_id, instance_id, release, "
                "definition, part, action, said, records, acts_for, decided, decided_by, drawn_at, flags) "
                "select scenario, kind, proposal_id, run_id, instance_id, release, definition, part, "
                "action, said, records, acts_for, decided, decided_by, drawn_at, flags from samples "
                "where id = %s", (real["id"],))


def graded(walk: Walk, stack, url: str) -> None:
    """Mel grades the quarter's corrections, twenty at a time, and the evidence raises a5s's cap
    on them in material data to level 2."""
    quarter(stack)
    rounds = 0
    while True:
        page = walk.as_("mel", f"{url}/grade/")
        page.wait_for_selector("#status:not(:empty), [data-sample]", timeout=30000)
        cards = page.locator("[data-sample]").all()
        if not cards:
            break
        for card in cards:
            card.get_by_role("button", name="Right").click()
        if rounds == 0:
            with walk.step(f"Over the quarter, each correction Mo decided is drawn as a sample, {GRADED} "
                           "of them here, made up like Raf's. Mel, who grades the agents' work in "
                           "material data, from outside the team that built it, grades them on a5s's "
                           "own page, twenty at a time: each is right.", page):
                pass
        page.click("#send")
        page.wait_for_selector("#status >> text=Graded", timeout=30000)
        rounds += 1
        page.close()
    assert rounds == 5
    stack.scheduler().decided()  # the core seals them, and weighs the evidence
    with db.transaction(stack.admin) as conn:
        caps = [(r["part"], r["action"], r["cap"]) for r in conn.execute("select * from caps")]
    assert ("material", "correct-value", 2) in caps, caps


def raised(walk: Walk, stack, url: str, instance: str) -> None:
    """Ines asks for level 2 for corrections in material data, and the owners approve it."""
    page = walk.as_("ines", f"{url}/studio/instances/{instance}")
    with walk.step("The evidence holds: a5s has raised its cap on corrections in material data to "
                   "level 2. From its instance's page, Ines changes its settings to ask for it "
                   "there, as a version of the settings: mdg-helper makes them on its own, within "
                   "their limits.", page):
        page.click("#its-settings")
        page.wait_for_selector(f"fieldset[data-instance='{instance}']", timeout=30000)
        own = page.locator(f"fieldset[data-instance='{instance}'] "
                           "label:has-text('correct-value in material') input")
        own.check()
        own.scroll_into_view_if_needed()
    page.click("#review")
    page.wait_for_selector("#reviewed-changes li", timeout=30000)
    page.click("#send")
    page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    stack.scheduler().apply_approved()
    approved_by_all(walk, stack, url, "Ines Duarte")


def alone(walk: Walk, stack, url: str) -> None:
    """Raf's next correction is made alone, at level 2, and Mo hears of it."""
    stack.model.reply(None, ("correct_value", {"key": "CR0000111", "base_unit": "EA",
                                               "material_type": "ROH"}))
    stack.model.reply("Done: CR0000111's base unit is EA and its type ROH now, which a5s made at "
                      "level 2. It goes back to Tess Moran, its steward.")
    page = walk.as_("raf", f"{url}/chat/")
    with walk.step("Raf gives it what his next request lacks. At level 2, a5s makes the correction "
                   "itself, through SAP, and tells him; Mo hears of it in his daily digest.", page):
        says(page, AGENT, "CR0000111's bolts are counted in each, EA, and it's a raw material, ROH.",
             "which a5s made at level 2")
    now = stack.gateway.scenario.request("CR0000111")
    asked = [(e["action"], e["decision"], e.get("reasons"), e.get("level"), e.get("outcome"))
             for e in stack.ledger() if e["kind"] == "tool"][-6:]
    assert (now["values"]["base_unit"], now["values"]["material_type"], now["status"]) == (
        "EA", "ROH", "in review"), (now, page.locator("li.agent").last.inner_text(), asked)
    made = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "correct_value"
            and e["decision"] == "record" and e.get("level") == 2]  # what came of it, at its level
    assert [e["outcome"]["status"] for e in made] == ["ok"], made
    with db.transaction(stack.admin) as conn:  # the notice of this change, not an earlier item
        told = [r["text"] for r in conn.execute("select text from digest_items where person = 'mo' "
                                                "and text like '%%made a change itself, at level 2%%'")]
    assert len(told) == 1 and "CR0000111" in told[0], told


def audited(walk: Walk, url: str, instance: str) -> None:
    page = walk.as_("ken", f"{url}/audit/")
    with walk.step("Ken, of assurance, follows it in the audit trail: the correction it asked for, "
                   "held, decided by Mo and made through SAP, and the one it made alone at level 2.",
                   page):
        page.wait_for_selector("#find:not([hidden])", timeout=30000)
        page.fill("#instance", instance)
        page.click("#search")
        page.wait_for_selector("#entries li", timeout=30000)
        assert "correct_value" in page.inner_text("#entries")
        decided_in_trail(page, "mo")


def test_the_master_data_assistant_is_built_again_and_takes_one_correction_to_level_2(
        database, sandbox_database, tmp_path, provider, browser, monkeypatch, capsys):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    on = walking_on(judged)
    model, http = on.model, on.http
    root = build_root(tmp_path, on.alias, on.models)
    team = root / "scenarios" / "master-data"
    shutil.copytree(ROOT / "scenarios" / "master-data", team)
    walk = Walk("master-data", "The master data assistant, built again in the studio", browser, provider)
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
            boxed = Config(database_url="postgresql://unused", gateway_url="http://unused",
                           service_token="", root=root, scenario=MASTER, scenario_folder=team,
                           agents_folder=root / "scenario-agents")
            with (sandbox.opened(boxed, sandbox_database, tmp_path / "sandbox",
                                 transport=on.transport) as box,
                  serve(sandbox.create_app(box, "shared-token"), free_port()) as box_url):
                stack.cfg = replace(stack.cfg, sandbox_url=box_url, sandbox_token="shared-token")
                with deciding(stack, provider) as url:
                    rebuilt, draft, pull = built(walk, stack, url, forge, on)
        hand_written = yaml.safe_load((agents / "mdg-assistant" / "agent.yaml").read_text())
        with walk.step("What mdg-helper may do, and what starts it, is what the hand-written master data "
                       "assistant's definition gives it, in the studio's words: nothing more, and "
                       "nothing missing."):
            assert able(rebuilt) == {**able(hand_written), "starts": able(rebuilt)["starts"]}, (
                able(rebuilt), able(hand_written))
            assert rebuilt["evaluation"] == {"judge": on.alias, "rubric": RUBRIC}
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
                corrected(walk, stack, url)
                graded(walk, stack, url)
                raised(walk, stack, url, instance)
                alone(walk, stack, url)
                audited(walk, url, instance)
    walk.guide("Master data's assistant, built again from nothing in the studio, as mdg-helper, by the "
               "data team's own people, SAP behind its MCP server: a test case its judge grades, a "
               "correction waiting for its data object's owner, and then, once graded samples showed "
               "the accuracy the owners asked for, corrections in material data made at level 2, as "
               "their settings gave it. tests/test_walkthrough_master_data.py takes these steps, and "
               "made these pictures.")
