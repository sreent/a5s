"""The studio's Status page: how a5s is doing, as the core last said, for the team that runs it.

The channels app serves it and can't ask the core, so the core records its status each minute,
as the scheduler asks it to, and the page reads that: what needs someone first, now or in
working hours, each with its runbook, then the release and the last day's lines, as `a5s status`
says them. A record gone stale says the scheduler or the core may be away (core/status_api.py)."""

from __future__ import annotations

import re

import httpx

from a5s import db
from a5s.core import shell_api, status_api
from conftest import ROOT, accessible
from test_personas import arrive, reads_well, sidebar


def page(approving: str, provider, person: str) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.get(f"{approving}/status/api", timeout=30,
                     headers={"Authorization": f"Bearer {token}"})


def test_the_team_reads_what_the_core_last_said_and_nobody_else_does(stack, approving, provider):
    stack.suspend(by="ben")  # something that needs someone, in working hours
    stack.scheduler().seen()  # as the scheduler asks each minute
    told = page(approving, provider, "priya")  # on the team that runs a5s
    assert told.status_code == 200, told.text
    found = told.json()
    assert found["seen_seconds_ago"] < 60
    # people sign in here, and the deployment asks no second factor of them, which is worth a look
    assert found["verdict"] == "2 can wait for working hours."
    assert [(n["when"], n["runbook"]) for n in found["needs"]] == [
        ("working hours", "docs/runbooks.md#an-instance-isnt-active"),
        ("working hours", "docs/runbooks.md#sign-ins-refused-for-want-of-a-second-factor")]
    assert "Not active: assistant-finance, suspended by ben." in found["day"]
    refused = page(approving, provider, "ana")  # an instance approver, not on the team
    assert refused.status_code == 403 and "the team that runs a5s" in refused.json()["detail"]


def test_a_record_gone_stale_says_the_scheduler_or_the_core_may_be_away(stack, approving,
                                                                        provider):
    assert page(approving, provider, "priya").json()["needs"][0]["said"].startswith(
        "The core hasn't said how a5s is doing yet")  # before the scheduler asks it
    stack.scheduler().seen()
    with db.transaction(stack.admin) as conn:  # as though nothing had asked it since
        conn.execute("update status_seen set at = now() - interval '12 minutes'")
    found = page(approving, provider, "priya").json()
    assert found["needs"][0]["said"].startswith(
        "The core last said how a5s is doing 12 minutes ago")
    assert found["needs"][0]["runbook"] == "docs/runbooks.md#messages-are-waiting"


def test_the_status_page_in_the_sidebar_of_the_team_reads_well(stack, approving, provider,
                                                               browser):
    stack.scheduler().seen()
    browsed, broken = arrive(browser, approving, provider, "tomas")  # on the team, no role
    assert sidebar(browsed)["Oversee"][0] == "Status"
    browsed.click("#pages a:has-text('Status')")
    browsed.wait_for_selector("#verdict h2", timeout=30000)
    assert browsed.inner_text("#verdict h2") == "1 can wait for working hours."
    assert "set A5S_OIDC_MFA" in browsed.inner_text("#verdict .needs")  # as nobody's asked for one
    assert "As the core said it" in browsed.inner_text("#seen")
    assert "Runs: 0" in browsed.inner_text("#day")
    reads_well(browsed, broken, marked="Status")
    accessible(browsed)


def test_every_pages_icon_is_drawn_in_both_sidebars():
    """The studio's sidebar and the chat's each draw a page's icon by its name: one neither
    draws shows nothing, as Model health's once did."""
    studio = set(re.findall(r"^  (\w+): \[", (ROOT / "studio/src/icons.tsx").read_text(
        encoding="utf-8"), re.MULTILINE))
    chat = set(re.findall(r"^    (\w+): \[", (ROOT / "src/a5s/core/webchat/shell.js").read_text(
        encoding="utf-8"), re.MULTILINE))
    icons = {icon for _, _, icon, _, _ in shell_api.PAGES}
    assert icons <= studio, icons - studio
    assert icons <= chat, icons - chat


def test_nothing_recorded_yet_is_said_too(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("delete from status_seen")
    found = status_api.status_page(stack.gateway)
    assert found["seen_seconds_ago"] is None and found["day"] == []
    assert found["verdict"].startswith("The core hasn't said how a5s is doing yet")
