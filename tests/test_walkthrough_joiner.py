"""Phase 5's walk-through of the desk's joiner coordinator (docs/phase-5.md, step 3), which the
desk planned and never built: described in plain words in the studio, drafted with the least it
needs, then refined by hand, on a5s as the desk deploys it.

Dev describes joiner-coordinator in his own words; the sandbox's model proposes what it needs, and
a5s gives it the least of that, each with the reason, which he checks. He takes away what it
doesn't need, adds by hand what it does, and plans it in access and hardware, for the sales team,
where Jo joins. Ren and Dev sign the release that adds it; Ola and Hugo put it to work. Jo asks it
about their laptop and accounts before their first day, and Zia reads the run in the audit trail.

    A5S_GUIDE=docs/guides uv run pytest tests/test_walkthrough_joiner.py
"""

from __future__ import annotations

import shutil
from dataclasses import replace

from a5s import db, sandbox
from a5s.config import Config
from a5s.core import drafts
from conftest import (
    PROVIDER_KEY,
    ROOT,
    build_root,
    deciding,
    free_port,
    serve,
)
from fake_github import FakeGitHub
from scenario_stack import running_scenario
from test_studio_authoring import kept
from test_walkthrough_desk import DESK, able, definition
from walkthrough import (
    On,
    Walk,
    answering,
    deployed,
    merged,
    owned,
    released,
    says,
    signed_and_recorded,
    walking_on,
)

AGENT = "joiner-coordinator"
WORDS = ("Tracks each new joiner's starter requests in the ITSM against their start date, their laptop "
         "and their accounts, chases whoever owes one, and answers the joiner's questions about their "
         "requests before day one.")
INSTRUCTIONS = """# Joiner coordinator

You help people who are joining, before their first day, and whoever owes them something. You're
an AI agent, and you say so if anyone asks.

- Find a joiner's starter requests with `search_records`, by their name, and read one with
  `get_record`. Say what each is, who has it, and when it's due, against their start date.
- Use `get_account` to say whether a joiner's account is ready.
- You change nothing, and grant nothing: say who to ask instead.
"""


def described(walk: Walk, stack, url: str, forge: FakeGitHub, on: On) -> tuple[dict, str, dict]:
    """Dev describes joiner-coordinator, checks what it was given, refines it by hand, and
    publishes it: its definition, as a5s keeps it, its draft, and its pull request."""
    page = walk.as_("dev", f"{url}/studio/new")
    with walk.step("Dev starts the joiner coordinator the desk planned and never built, "
                   "joiner-coordinator, by describing it in his own words, on the sandbox's model, "
                   "rather than from a template.", page):
        page.wait_for_selector("#describe", timeout=30000)
        page.fill("#agent-name", AGENT)
        page.fill("#describe", WORDS)
        if on.live:  # at night, the night's model proposes, which thinks, as the stand-in doesn't
            page.select_option("#describe-model", on.alias)
        page.click("#describe-it")
        page.wait_for_selector("#described li", timeout=180000)
    with walk.step("The draft says what it was given, each with the reason, of what the desk offers, "
                   "at the lowest level each needs, never 2: on the stand-in, the tools that only "
                   "read whose words match his, at level 0, which only reads.", page):
        page.locator("#described").scroll_into_view_if_needed()
        given = page.locator("#described li[data-given]").all_inner_texts()
        assert given and not any("level 2" in g for g in given), given
        spec = definition(stack, page)
        if not on.live:  # the stand-in's, which thinks nothing: a model's may ask for more
            assert any("search_records" in g for g in given) and any("get_account" in g for g in given), given
            assert not any(t in " ".join(given) for t in ("reply_on_ticket", "reset_password", "create_draft"))
            assert any("level 0 at most" in g for g in given), given
            assert spec["autonomy"] == {"start": 0, "max": 0}
    with walk.step("He takes away what it doesn't need: what requesters wrote, which the joiner's own "
                   "questions don't call for, and anything that writes, changes or sends.", page):
        for tool in ("get_messages", "reply_on_ticket", "reset_password", "reset_authenticators",
                     "create_draft"):
            if tool in str(spec["tools"]):
                page.click(f".flow-canvas [data-step='tool:{tool}']")
                page.click("#take-away")
                kept(page)
    with walk.step("He adds by hand what it does need: what people owe in the ITSM's tickets, which it "
                   "chases, and reminders; and level 1, since chasing writes.", page):
        for tool in ("search_records", "get_account"):  # what a model's draft may not have given it
            if tool not in str(spec["tools"]):
                page.click(f".fd-palette [data-tool={tool}]")
                kept(page)
        if "records" not in (spec.get("obligations") or []):  # the palette offers what it lacks
            page.click(".fd-palette [data-owed=records]")
            page.wait_for_selector(".flow-canvas [data-step=obligations]", timeout=30000)
            kept(page)
        if not spec.get("reminders"):
            page.click(".fd-palette [data-ability=reminders]")
            kept(page)
        page.click("[data-step=agent]")
        page.fill("#works-for", "New joiners before their first day, and whoever owes them something")
        page.select_option("#level-max", "1")
        page.select_option("#level-start", "1")
        kept(page)
    with walk.step("He plans its first instance in access and hardware, where joiners' requests are, "
                   "serving the sales team, where Jo joins: in force nowhere until both parts' owners "
                   "approve it.", page):
        for part in ("access", "hardware"):
            page.check(f"#plan-title ~ fieldset label:has-text('{part}') input")
            kept(page)
        page.check("#plan-title ~ fieldset label:has-text('team:sales') input")
        kept(page)
    with walk.step("He tells it how to work, in its instructions.", page):
        page.click(".wb-bar .modes button:has-text('Instructions')")
        page.fill("#instructions", INSTRUCTIONS)
        kept(page)
        page.click(".wb-bar .modes button:has-text('Design')")
        page.wait_for_selector("#problem-count >> text=No problems", timeout=30000)
    refined = definition(stack, page)
    with walk.step("Nothing stops its release. Dev publishes its pull request.", page):
        page.click("#to-publish")
        page.click("#publish")
        page.wait_for_selector("#user-code", timeout=30000)
        forge.grant(page.inner_text("#user-code"), "dev-gh")  # at GitHub, as himself
        page.wait_for_selector("#published >> text=its pull request", timeout=30000)
    [pull] = forge.pulls
    return refined, page.evaluate("location.pathname"), pull


def at_work(walk: Walk, stack, url: str, draft: str) -> None:
    """Dev puts it to work from its plan, and the owners of access and hardware approve it."""
    page = walk.as_("dev", f"{url}{draft}")
    with walk.step("Its release signed and deployed, Dev puts it to work from its plan.", page):
        page.click("#put-to-work")
        page.wait_for_selector("#add-instance", timeout=30000)
        assert page.input_value("#add-agent") == AGENT
        page.click("#add-it")
        page.click("#review")
        page.wait_for_selector("#reviewed-changes li", timeout=30000)
        added = page.locator("#reviewed-changes li").first.inner_text()
        assert AGENT in added and "serving everyone in the sales team" in added, added
        assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ola Nowak, Hugo Lind."
        page.click("#send")
        page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    stack.scheduler().apply_approved()
    for person, name in (("ola", "Ola, who owns access,"), ("hugo", "Hugo, who owns hardware,")):
        page = walk.as_(person, f"{url}/studio/")
        with walk.step(f"{name} approves it, signed in afresh for that version alone.", page):
            page.click("#waiting a:has-text('waits for your approval')")
            page.wait_for_selector("#asker >> text=Dev Shah asked for it", timeout=30000)
            page.click("#approve")
            page.wait_for_selector("#status >> text=You approved version", timeout=30000)
        stack.scheduler().apply_approved()


def asked_and_audited(walk: Walk, stack, url: str) -> None:
    """Jo asks it about their requests, and Zia reads the run in the audit trail."""
    stack.model.reply(None, ("search_records", {"query": "Jo Joiner"}))
    stack.model.reply("Your laptop, REQ0000101, is with Hal Moss, due on 23 November, your first day; "
                      "your accounts, REQ0000102, are with Rae Kim, due the same day.")
    page = walk.as_("jo", f"{url}/chat/")
    with walk.step("Jo, who joins sales on 23 November, asks it in the chat whether their laptop and "
                   "accounts will be ready. It finds their own requests in the ITSM, and no one else's.", page):
        says(page, AGENT, "Will my laptop and accounts be ready for my first day?", "REQ0000101")
    with db.transaction(stack.admin) as conn:  # its instance, as the settings named it from its plan
        [instance] = [r["id"] for r in conn.execute("select id from instances where definition = %s", (AGENT,))]
    page = walk.as_("zia", f"{url}/audit/")
    with walk.step("Zia, of assurance, reads what it did in the audit trail.", page):
        page.wait_for_selector("#find:not([hidden])", timeout=30000)
        page.fill("#instance", instance)
        page.click("#search")
        page.wait_for_selector("#entries li", timeout=30000)
        assert "search_records" in page.inner_text("#entries")


def test_the_joiner_coordinator_is_described_drafted_least_privilege_and_refined_by_hand(
        database, sandbox_database, tmp_path, provider, browser, monkeypatch, capsys):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    on = walking_on()
    model, http = on.model, on.http
    root = build_root(tmp_path, on.alias, on.models)
    desk = root / "scenarios" / "service-desk"
    shutil.copytree(ROOT / "scenarios" / "service-desk", desk)
    walk = Walk("joiner", "The joiner coordinator, described and refined in the studio", browser, provider)
    agents = ROOT / "scenarios" / "service-desk" / "agents"
    forge = FakeGitHub({f"scenario-agents/{name}/{path}": text for name in ("desk-assistant",)
                        for path, text in drafts.folder_files(agents / name).items()})
    with serve(forge.app(), free_port()) as forge_url:
        forge.url = forge_url
        with running_scenario(database, root, model, DESK, "service-desk", http=http, alias=on.alias,
                              scenario_folder=desk) as stack:
            deployed(stack, forge)
            said = released(stack, tmp_path / "first", monkeypatch, capsys)
            said = signed_and_recorded(said, capsys, "ren", "zia", "max", "dev")
            assert said.rstrip().endswith("Approved here."), said
            boxed = Config(database_url="postgresql://unused", gateway_url="http://unused",
                           service_token="", root=root, scenario=DESK, scenario_folder=desk,
                           agents_folder=root / "scenario-agents")
            with (sandbox.opened(boxed, sandbox_database, tmp_path / "sandbox",
                                 transport=on.transport) as box,
                  serve(sandbox.create_app(box, "shared-token"), free_port()) as box_url):
                stack.cfg = replace(stack.cfg, sandbox_url=box_url, sandbox_token="shared-token")
                with deciding(stack, provider) as url:
                    refined, draft, pull = described(walk, stack, url, forge, on)
        with walk.step("What it may do is what its description gave it, less what Dev took away, and what "
                       "he added by hand: reads, what people owe, and reminders, at level 1 at most."):
            found = able(refined)
            assert "get_messages" not in found["tools"] and {"search_records", "get_account"} <= set(found["tools"])
            assert found["levels"] == (1, 1) and found["owed"] == ["records"] and found["reminders"]
        with walk.step("The team merges its pull request, and the directory names Dev its owner."):
            merged(stack, forge.files(pull["head"]), AGENT)
            owned(stack.cfg.scenario_dir, "dev", AGENT)
        with running_scenario(database, root, model, DESK, "service-desk", http=http, alias=on.alias,
                              scenario_folder=desk) as stack:
            deployed(stack, forge)
            with walk.step("Deployed again, Ren and Dev sign the release that adds it, and the team "
                           "records it: it's approved, and a5s runs it."):
                said = released(stack, tmp_path / "second", monkeypatch, capsys)
                said = signed_and_recorded(said, capsys, "ren", "dev")
                assert said.rstrip().endswith("Approved here."), said
            with deciding(stack, provider) as url, answering(stack):
                at_work(walk, stack, url, draft)
                asked_and_audited(walk, stack, url)
    walk.guide("The desk's joiner coordinator, which it planned and never built, described in plain words "
               "in the studio, drafted with the least it needs, and refined by hand. "
               "tests/test_walkthrough_joiner.py takes these steps, and made these pictures.")

