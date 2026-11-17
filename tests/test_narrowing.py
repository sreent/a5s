"""A version that only narrows what agents may do in a part needs that part's owner alone
(registry.narrowed): a lower level there, a type of action's level lowered or taken back, or a
stricter threshold. Code decides, and anything it can't show narrows counts as widening, so it
needs every part's owner, as before. Once one is in force, the others whose approval it would
have needed hear of it in their digest."""

from __future__ import annotations

import base64
import copy
from collections.abc import Callable

import pytest
import yaml

from a5s import db
from a5s.contract import parse_settings
from a5s.core import registry
from conftest import ROOT
from test_approvals import decide, sign_in

# The sample's settings, with an instance in orders beside those in billing: Ana owns
# billing, Omar orders
BASE = yaml.safe_load((ROOT / "scenarios" / "sample" / "settings.yaml").read_text())
BASE["instances"]["assistant-finance"]["parts"] = {
    "billing": {"level": 1, "actions": {"change-due-date": 1, "close-question": 0}}}
BASE["instances"]["assistant-ops"] = {"definition": "assistant", "serves": ["chen", "omar"],
                                      "parts": ["orders"], "level": 1, "owner": "omar"}


def finance(s: dict) -> dict:
    return s["instances"]["assistant-finance"]


def billing(s: dict) -> dict:
    return finance(s)["parts"]["billing"]


def parsed(given: dict):
    return parse_settings(yaml.safe_dump(given).encode())


def edited(change: Callable[[dict], object]) -> dict:
    after = copy.deepcopy(BASE)
    after["serial"] += 1
    change(after)
    return after


CASES = [  # what a version changes, and the parts it only narrows, if that's all it does
    ("a lower level for the part", lambda s: billing(s).update(level=0), {"billing"}),
    ("a lower level for the instance, which its part takes",
     lambda s: (finance(s).update(level=0), billing(s).pop("level")), {"billing"}),
    ("a higher level", lambda s: finance(s).update(level=2, parts={"billing": {
        "actions": billing(s)["actions"]}}), None),
    ("a type of action's level lowered", lambda s: billing(s)["actions"].update(
        {"change-due-date": 0}), {"billing"}),
    ("a type of action's level raised", lambda s: billing(s)["actions"].update(
        {"change-due-date": 2}), None),
    ("a type of action taken back from level 1", lambda s: billing(s)["actions"].pop(
        "change-due-date"), {"billing"}),
    ("a type of action taken back from level 0, which then works at level 1",
     lambda s: billing(s)["actions"].pop("close-question"), None),
    ("a new type of action at level 0", lambda s: billing(s)["actions"].update(
        {"refund": 0}), {"billing"}),
    ("a new type of action at level 2", lambda s: billing(s)["actions"].update(
        {"refund": 2}), None),
    ("a stricter threshold", lambda s: s["thresholds"].update(billing=0.99), {"billing"}),
    ("a threshold taken away, so level 2 is never earned there",
     lambda s: s["thresholds"].pop("billing"), {"billing"}),
    ("a looser threshold", lambda s: s["thresholds"].update(billing=0.9), None),
    ("limits tightened, which are every part's",
     lambda s: s["limits"]["change-due-date"].update(per_run=1), None),
    ("whom it serves, beside a lower level",
     lambda s: (billing(s).update(level=0), finance(s).update(serves=["ana"])), None),
    ("an instance added", lambda s: s["instances"].update({"assistant-two": {
        **copy.deepcopy(BASE["instances"]["assistant-ops"]), "level": 0}}), None),
    ("an instance retired", lambda s: s["instances"].pop("assistant-ops"), None),
    ("a part taken away, which can raise the instance's own level",
     lambda s: s["instances"]["watcher-finance"].update(parts=[]), None),
    ("nothing but its number", lambda s: None, None),
    ("narrowing in two parts", lambda s: (billing(s).update(level=0),
                                          s["instances"]["assistant-ops"].update(level=0)),
     {"billing", "orders"}),
]


@pytest.mark.parametrize(("what", "change", "parts"), CASES, ids=[c[0] for c in CASES])
def test_code_decides_what_only_narrows_a_part(what, change, parts):
    assert registry.narrowed(parsed(edited(change)), parsed(BASE)) == parts, what


def test_the_first_version_narrows_nothing():
    assert registry.narrowed(parsed(BASE), None) is None


def test_a_narrowing_version_needs_its_parts_owners_alone(stack):
    scenario = stack.gateway.scenario
    before = parsed(BASE)
    lower = parsed(edited(lambda s: billing(s).update(level=0)))
    assert registry.missing(lower, scenario.person, ["ana"], before) == []
    assert [p.id for p in registry.approvers(lower, scenario.holders, before)] == ["ana"]
    assert [p.id for p in registry.told(lower, scenario.holders, before)] == ["omar"]
    higher = parsed(edited(lambda s: billing(s)["actions"].update({"change-due-date": 2})))
    assert "the owner of orders hasn't approved it" in registry.missing(
        higher, scenario.person, ["ana"], before)
    assert registry.told(higher, scenario.holders, before) == []
    both = parsed(edited(lambda s: (billing(s).update(level=0),
                                    s["instances"]["assistant-ops"].update(level=0))))
    assert registry.missing(both, scenario.person, ["ana"], before) == [
        "the owner of orders hasn't approved it"]  # orders' narrowing is its owner's alone


def propose(stack, settings: dict) -> dict:
    raw = yaml.safe_dump(settings).encode()
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(raw).decode()})
    r.raise_for_status()
    return r.json()


def approve(approving, provider, asked: dict, *people: str) -> list[dict]:
    said = []
    for person in people:
        token, salt = sign_in(approving, provider, asked["digest"], person)
        r = decide(approving, asked["digest"], token, salt)
        assert r.status_code == 200, r.text
        said.append(r.json())
    return said


def level(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select level from instances where id = 'assistant-finance'"
                            ).fetchone()["level"]


def test_billings_owner_narrows_it_alone_and_orders_owner_hears(stack, approving, provider):
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    settings["serial"] += 1
    settings["instances"]["assistant-ops"] = copy.deepcopy(BASE["instances"]["assistant-ops"])
    asked = propose(stack, settings)
    assert sorted(asked["asked"]) == ["ana", "omar"]  # a new instance: every part's owner
    approve(approving, provider, asked, "ana", "omar")
    stack.scheduler().apply_approved()
    assert level(stack) == 1

    lower = copy.deepcopy(settings)
    lower["serial"] += 1
    lower["instances"]["assistant-finance"]["level"] = 0  # billing takes it: it only narrows
    asked = propose(stack, lower)
    assert asked["asked"] == ["ana"]
    [said] = approve(approving, provider, asked, "ana")
    assert said["needs"] == []
    stack.scheduler().apply_approved()
    assert level(stack) == 0
    with db.transaction(stack.admin) as conn:
        [item] = conn.execute("select text from digest_items where person = 'omar'").fetchall()
    assert item["text"].startswith(f"Ana Ortiz approved version {lower['serial']} of the "
                                   "settings alone, since it only narrows what agents may do in "
                                   "billing: ")
    [told] = [e for e in stack.ledger() if e.get("action") == "narrowed"]
    assert told["args"]["to"] == "omar" and told["args"]["parts"] == ["billing"]
    stack.model.reply("Hello, Ben.")  # the core checks it again at every run: it holds
    assert stack.say("Hello", person="ben") == "Hello, Ben."

    higher = copy.deepcopy(lower)
    higher["serial"] += 1
    higher["instances"]["assistant-finance"]["level"] = 1  # back up: every part's owner again
    asked = propose(stack, higher)
    assert sorted(asked["asked"]) == ["ana", "omar"]
    [said] = approve(approving, provider, asked, "ana")
    assert "the owner of orders hasn't approved it" in said["needs"]
    stack.scheduler().apply_approved()
    assert level(stack) == 0  # it waits for Omar


def test_a_narrowing_keeps_level_2_in_every_other_part_and_tells_whoever_it_applies_from(stack):
    """Round 14 (C2, C9): Omar narrows orders alone. Ben's due dates in billing, made alone at
    level 2 before it, still are: the approvals of the version before it stand in every part it
    didn't narrow. And applied from the signed file, as `a5s apply` does, it tells Ana, as one
    approved where people work does."""
    from a5s import cli
    from a5s.contract import record_of
    from conftest import raise_cap, signed

    folder = stack.cfg.scenario_dir

    def move(due: str) -> str:
        stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": due}))
        stack.model.reply("Done what I could.")
        stack.say(f"Please move Q-1002 to {due}.", person="ben")
        return record_of(stack.gateway.scenario, "Q-1002").fields["due date"]

    s = yaml.safe_load((folder / "settings.yaml").read_text())
    finance(s)["parts"] = {"billing": {"level": 1, "actions": {"change-due-date": 2}}}
    s["instances"]["assistant-ops"] = copy.deepcopy(BASE["instances"]["assistant-ops"])
    signed(folder, s, ("ana", "omar"))
    cli._apply(stack.cfg)
    raise_cap(stack, cap=2)
    assert move("2026-11-13") == "2026-11-13"  # made alone, at level 2
    s = yaml.safe_load((folder / "settings.yaml").read_text())
    s["instances"]["assistant-ops"]["level"] = 0  # Omar narrows orders, alone
    signed(folder, s, ("omar",))
    cli._apply(stack.cfg)
    assert move("2026-11-20") == "2026-11-20"  # billing's level 2 stands
    with db.transaction(stack.admin) as conn:
        [told] = conn.execute("select person, text from digest_items where text like %s",
                              ("%only narrows%",)).fetchall()
    assert told["person"] == "ana" and told["text"].startswith(
        f"Omar Haddad approved version {s['serial'] + 1} of the settings alone, since it only "
        "narrows what agents may do in orders: ")


def test_a_thai_approver_reads_a_whole_version_in_thai(stack, approving, provider, browser):
    """Round 14 (E-M5) and its deferral: what's missing before a version goes in force, what it
    changes and the whole of it are in the language its approver reads, as on their home, and
    so is the card that asks them, each name and figure kept as the settings write it."""
    from a5s.core import words
    from test_languages import reads
    from test_settings_app import api

    reads(stack, "ana", "th")
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    settings["serial"] += 1
    settings["instances"]["assistant-ops"] = copy.deepcopy(BASE["instances"]["assistant-ops"])
    asked = propose(stack, settings)
    with db.transaction(stack.admin) as conn:  # the card in her chat, in Thai
        [card] = conn.execute("select text from outbox where person = 'ana' and text like %s",
                              (f"%{settings['serial']}%",)).fetchall()
    assert card["text"].startswith(f"การตั้งค่า a5s เวอร์ชัน {settings['serial']} รอให้ผู้อนุมัติอนุมัติ")
    assert "เพิ่ม assistant-ops: assistant ไม่อยู่ในส่วนงานใด" in card["text"] or \
        "เพิ่ม assistant-ops: assistant ทำงานใน orders ที่ระดับ" in card["text"], card["text"]
    [said] = approve(approving, provider, asked, "ana")
    english = "the owner of orders hasn't approved it"
    missing = [words.say("th", "the owner of {part} hasn't approved it", part="orders")]
    assert said["needs"] == missing != [english]
    shown = api(approving, provider, f"/approve/settings/{asked['digest']}").json()
    assert shown["needs"] == missing
    assert [c["text"].split(":")[0] for c in shown["changes"]] == ["เพิ่ม assistant-ops"]
    assert shown["whole"][0].startswith("ข้อมูลของซีนาริโอเป็น synthetic")
    assert any(line.startswith("assistant-ops: assistant ทำงานใน orders") for line in shown["whole"])
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/studio/approve?settings={asked['digest']}")
    page.wait_for_selector("#changes li", timeout=30000)
    assert page.inner_text("#needs") == missing[0]
    assert page.inner_text("#changes li").startswith("เพิ่ม assistant-ops")
    assert page.locator("#in-english").count() == 0  # no word that any of it is in English
