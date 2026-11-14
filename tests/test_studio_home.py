"""The studio's home (core/home.py, docs/studio.md#people-roles-and-spaces): what waits for
whoever signed in, each where they do it, and each role they hold, what gave it them, the
directory or a group, and what it lets them do. Anyone the directory knows sees their own,
with a role or without one, and nobody else's."""

from __future__ import annotations

import uuid

import httpx
import yaml

from a5s import db
from a5s.contract import ASSURANCE
from a5s.core import releases
from conftest import ROOT
from test_group_roles import OWNERS, mapped, version
from test_proposals import asked, held
from test_samples import release


def api(url: str, provider, person: str, path: str, *groups: str) -> httpx.Response:
    token = provider.id_token(person=person, groups=list(groups))
    return httpx.get(f"{url}/studio/api/{path}", headers={"Authorization": f"Bearer {token}"},
                     timeout=30)


def test_anyone_the_directory_knows_has_a_home_role_or_none(stack, approving, provider):
    assert httpx.get(f"{approving}/studio/api/home", timeout=30).status_code == 401
    chen = api(approving, provider, "chen", "home").json()  # who holds none of a5s's roles
    assert (chen["you"], chen["waiting"], chen["catalogue"], chen["authoring"]) == (
        "Chen Wei", [], False, False)
    assert api(approving, provider, "chen", "you").json()["roles"] == []
    assert api(approving, provider, "nobody-we-know", "home").status_code == 403


def test_it_says_what_waits_for_whom_and_where_they_do_it(stack, approving, provider):
    waiting = version(stack, level=0)  # billing's owner approves a change to its instance
    asked(stack)  # and decides a change the assistant asked for there
    assert held(stack)
    ana = {w["kind"]: w for w in api(approving, provider, "ana", "home").json()["waiting"]}
    assert ana["settings"] == {
        "kind": "settings", "go": "/settings/",
        "what": f"Version {waiting['serial']} of the settings waits for your approval",
        "why": ["the owner of billing hasn't approved it"]}
    assert ana["decide"]["what"] == "1 change an agent asked for waits for your decision"
    assert ana["decide"]["go"] == "/decide/"
    for nobody in ("chen", "priya", "ben"):  # none of it waits for them
        assert api(approving, provider, nobody, "home").json()["waiting"] == []


def test_a_grader_and_a_tasks_owner_see_theirs(stack, approving, provider):
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
            "part, action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
            "gen_random_uuid(), 'assistant-finance', %s, 'assistant', 'billing', "
            "'change-due-date', 'a change', '{}', '{ben}', now())", (release(stack),))
        task = str(uuid.uuid4())  # one of Ben's, stopped until he says what to do
        conn.execute("insert into tasks (id, instance_id, owner, audience, task, status, "
                     "token_budget, deadline, root, created_at) values (%s, 'assistant-finance', "
                     "'ben', '{ben}', 'go through the open invoices', 'blocked', 1000, "
                     "now() + interval '1 day', %s, now())", (task, task))
    [graded] = api(approving, provider, "dana", "home").json()["waiting"]
    assert (graded["what"], graded["go"]) == ("1 sample of agents' work waits for your grade",
                                              "/grade/")
    [tasks] = api(approving, provider, "ben", "home").json()["waiting"]
    assert (tasks["what"], tasks["go"]) == (
        "1 of your tasks waits for you, blocked or asked for", "/tasks/")


def test_it_says_which_roles_someone_holds_what_gave_them_and_what_they_let_them_do(
        stack, approving, provider):
    mapped(stack, approving, provider)  # the settings give billing's owners' group the role
    ben = api(approving, provider, "ben", "you", OWNERS).json()  # his sign-in shows the group
    [owner] = [r for r in ben["roles"] if r["role"] == "part-owner:billing"]
    assert owner["by"] == [f"group {OWNERS}"] and owner["may"].startswith(
        "approve the instances that work in billing")
    assert ben["groups"] == [OWNERS]
    ana = {r["role"]: r for r in api(approving, provider, "ana", "you").json()["roles"]}
    assert ana["instance-approver"]["by"] == ["the directory"]
    priya = api(approving, provider, "priya", "you").json()["roles"]
    assert priya[0]["role"] == "the team that runs a5s"  # first, as it can make a5s safer alone
    assert {"agent-owner:assistant", "agent-owner:watcher"} <= {r["role"] for r in priya}


def test_the_release_waits_for_those_it_needs_who_havent_signed(stack):
    raw = releases.manifest(ROOT, ROOT / "scenarios" / "sample")
    running = releases.Running(raw)
    scenario, team = stack.gateway.scenario, stack.cfg.team
    with db.transaction(stack.admin) as conn:  # nothing approved here yet: it needs everyone
        roles = {n.role for n in releases.needs(yaml.safe_load(raw), releases.last_approved(conn), None)}
        kofi = releases.awaiting(conn, running, scenario, team, scenario.person("kofi"))
        assert ASSURANCE in roles and [n.role for n in kofi] == [ASSURANCE]
        assert releases.awaiting(conn, running, scenario, team, scenario.person("chen")) == []
        broken = releases.Running(raw, problems=("its code isn't what was built",))
        assert releases.awaiting(conn, broken, scenario, team, scenario.person("kofi")) == []


def test_someone_finds_what_waits_and_what_they_may_do_in_the_studio(stack, approving, provider,
                                                                      browser):
    from test_ui_pages import shot

    version(stack, level=0)
    asked(stack)
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    refused = []
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#waiting .wait", timeout=30000)
    waits = page.inner_text("#waiting")
    assert "waits for your approval" in waits and "the owner of billing hasn't approved it" in waits
    assert page.get_attribute("#waiting a:has-text('waits for your decision')", "href") == "/decide/"
    shot(page, "studio-home")
    page.click("#next a:has-text('What you may do in a5s')")
    page.wait_for_selector("#roles table", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/you"
    row = page.inner_text("#roles tr:has-text('part-owner:billing')")
    assert "approve the instances that work in billing" in row and "the directory" in row
    assert refused == []
