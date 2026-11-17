"""What a version of the settings would do differently: the tool calls agents made in the last
weeks, decided again as the version in force decides them and as the new one would, shown to
whoever reviews it in the settings and to its approvers before they sign (core/impact.py)."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import yaml

from a5s import db
from a5s.contract import InstanceSettings, parse_settings
from a5s.core import impact, words
from conftest import raise_cap
from test_levels import asked, levelled
from test_settings_app import api

MOVE_ANOTHER = ("change_due_date", {"key": "Q-1001", "due": "2026-11-20"})


def written(approving, provider, parts=None, limits=None) -> str:
    """The version in force, as written, with the assistant's parts or the limits changed."""
    edited = yaml.safe_load(api(approving, provider, "/settings/api").json()["in_force"]["text"])
    if parts is not None:
        edited["instances"]["assistant-finance"]["parts"] = parts
    if limits is not None:
        edited["limits"] = limits
    return yaml.safe_dump(edited)


def reviewed(approving, provider, text: str) -> dict:
    found = api(approving, provider, "/settings/api/review", text=text)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["problems"] == [], body["problems"]
    return body["impact"]


LEVEL_2 = {"billing": {"level": 1, "actions": {"change-due-date": 2}}}


def test_a_held_change_a_version_would_make_alone_is_shown_once_samples_earn_it(
        stack, approving, provider):
    asked(stack)  # Ben asks to move Q-1002: at level 1, it's held for Ana
    capped = reviewed(approving, provider, written(approving, provider, parts=LEVEL_2))
    assert capped["calls"] == 1 and capped["shifts"] == [] and capped["days"] == 28
    [held_back] = capped["capped"]  # set to level 2, but graded samples haven't earned it
    assert held_back.startswith("assistant-finance is set to make change-due-date in billing "
                                "alone, at level 2, but a5s's cap holds it at level 1")
    raise_cap(stack)
    earned = reviewed(approving, provider, written(approving, provider, parts=LEVEL_2))
    assert earned["capped"] == []
    assert earned["shifts"] == [{
        "instance": "assistant-finance", "tool": "change_due_date", "parts": ["billing"],
        "was": "hold", "would": "allow", "calls": 1, "why": "the tool is in the instance's grant"}]


def test_a_version_that_takes_a_part_away_shows_the_calls_it_would_refuse(
        stack, approving, provider):
    asked(stack)
    narrowed = reviewed(approving, provider, written(approving, provider, parts=["orders"]))
    [shift] = narrowed["shifts"]
    assert (shift["was"], shift["would"], shift["calls"]) == ("hold", "deny", 1)
    assert shift["why"] == "the record is in a part the instance doesn't work in"


def test_a_tighter_limit_shows_the_changes_it_would_have_held(stack, approving, provider):
    levelled(stack)  # level 2 for due dates in billing, earned
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"}), MOVE_ANOTHER,
          said="Please move Q-1002 to the 13th and Q-1001 to the 20th.")
    made = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "change_due_date"
            and e["decision"] == "allow"]
    assert len(made) == 2  # both made alone, within the scenario's limits
    tighter = {"change-due-date": {"per_run": 5, "per_person_30_days": 1},
               "close-question": {"per_run": 5, "per_person_30_days": 20}}
    shown = reviewed(approving, provider, written(approving, provider, parts=LEVEL_2,
                                                  limits=tighter))
    [shift] = shown["shifts"]  # Ben's second would have waited for a person, past the limit
    assert (shift["was"], shift["would"], shift["calls"]) == ("allow", "hold", 1)
    assert shift["why"].startswith("past the scenario's limit for its type of action")


def test_its_approvers_see_it_while_it_waits(stack, approving, provider):
    asked(stack)
    raise_cap(stack)
    asking = api(approving, provider, "/settings/api/requests",
                 text=written(approving, provider, parts=LEVEL_2))
    assert asking.status_code == 202, asking.text
    stack.scheduler().apply_approved()  # the gateway proposes it
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select digest from settings_proposals where outcome is null "
                             "order by serial desc limit 1").fetchall()
    shown = api(approving, provider, f"/approve/settings/{row['digest']}").json()
    assert shown["status"] == "waiting"
    assert [(s["was"], s["would"]) for s in shown["impact"]["shifts"]] == [("hold", "allow")]


def test_a_call_refused_for_what_no_version_decides_isnt_decided_again(stack, approving,
                                                                        provider):
    asked(stack, ("change_due_date", {"key": "Q-1002"}))  # no due date: it doesn't fit the tool
    shown = reviewed(approving, provider, written(approving, provider, parts=LEVEL_2))
    assert shown["calls"] == 0 and shown["shifts"] == []


def test_the_approve_page_shows_it_beside_what_the_version_says(stack, approving, provider,
                                                                browser):
    from conftest import accessible

    asked(stack)
    raise_cap(stack)
    asking = api(approving, provider, "/settings/api/requests",
                 text=written(approving, provider, parts=LEVEL_2))
    assert asking.status_code == 202, asking.text
    stack.scheduler().apply_approved()
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select digest from settings_proposals where outcome is null "
                             "order by serial desc limit 1").fetchall()
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/studio/approve?settings={row['digest']}")
    shown = page.wait_for_selector("#impact table", timeout=30000)
    text = shown.inner_text()
    assert "change_due_date" in text and "held for a person" in text and "made alone" in text
    accessible(page)


def test_whoever_reviews_it_sees_only_the_instances_they_may_watch(stack, approving, provider):
    """Omar owns orders, and may not watch billing's assistant: a version he writes that would
    change what it does shows him nothing of its calls, only how many it left out."""
    asked(stack)
    raise_cap(stack)
    text = written(approving, provider, parts=LEVEL_2)
    mine = reviewed(approving, provider, text)  # Ana's, who runs it and owns billing
    assert mine["shifts"] and mine["hidden"] == 0
    found = api(approving, provider, "/settings/api/review", person="omar", text=text)
    assert found.status_code == 200, found.text
    his = found.json()["impact"]
    assert (his["shifts"], his["calls"]) == ([], 0) and his["hidden"] == mine["calls"]


def test_a_run_for_nobody_counts_against_its_instance_and_a_shadow_as_a_shadow(stack):
    """As core/counts.py counts them: a run for nobody, such as one an event started, against
    its instance's other runs for nobody, of each type's limit for each person in 30 days. And
    a shadow is decided as a shadow, which changes nothing."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    settings["limits"]["change-due-date"]["per_person_30_days"] = 1
    version = parse_settings(yaml.safe_dump(settings).encode())
    now = datetime.now(UTC)
    call = impact.Call(seq=1, at=now, instance="assistant-finance", tool="change_due_date",
                       keys=("Q-1002",), decision="allow",
                       run={"id": "r", "trigger": {"kind": "event"}, "acts_for": [],
                            "read_outside": False})
    nobody = [f"{impact.NOBODY}assistant-finance"]
    earlier = defaultdict(list, {(nobody[0], "change-due-date"): [(now - timedelta(days=2), 1)]})
    assert impact._over(version, "change-due-date", 1, "w", nobody, call, Counter(), earlier)
    assert not impact._over(version, "change-due-date", 1, "w", nobody, call, Counter(),
                            defaultdict(list))
    shadow = InstanceSettings(id="assistant-finance", definition="assistant", serves=("ana",),
                              parts={"billing": 1}, shadows="assistant-other")
    assert impact._row(stack.gateway, shadow, call)["status"] == "shadow"


def test_each_tool_call_keeps_whether_its_run_had_read_outside_content(stack):
    """So a call decided before its run read anything from outside is decided again as it was,
    not as the run stood once it had."""
    asked(stack)
    calls = [e for e in stack.ledger() if e["kind"] == "tool"]
    assert calls and all(e["read_outside"] is False for e in calls)


def test_it_reads_in_the_language_its_reviewer_reads(stack, approving, provider):
    from test_languages import reads
    reads(stack, "ana", "th")
    found = reviewed(approving, provider, written(approving, provider, parts=LEVEL_2))
    assert found["about"] == words.TH[impact.ABOUT]  # in the language Ana reads
