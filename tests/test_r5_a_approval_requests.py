"""Round 5, reviewer a: what a5s sends approvers when someone asks for a version of the
settings. The words come from code, but the names in them come from the version as its
asker wrote it, and anyone who approves instances can ask, as often as they like.

Omar owns orders. Every version covers every instance, so Ana, who owns billing, is asked
about each version he asks for.
"""

import pytest
import yaml

from a5s.contract import SettingsError, parse_settings
from test_settings_app import api

EVIL = "https://evil.example/approve/?settings=" + "0" * 64


def written(url: str, provider) -> dict:
    return yaml.safe_load(api(url, provider, "/settings/api", person="omar").json()["in_force"]["text"])


def test_approvers_are_sent_no_link_but_the_approval_pages(stack, approving, provider):
    edited = written(approving, provider)
    edited["instances"][f"[Review and approve]({EVIL})"] = {
        "definition": "assistant", "serves": ["omar"], "parts": ["orders"], "level": 0}
    asked = api(approving, provider, "/settings/api/requests", person="omar",
                text=yaml.safe_dump(edited))
    assert asked.status_code == 409  # ids are plain words, so a link can't be one
    assert "String should match pattern" in asked.json()["detail"]["problems"][0]
    stack.scheduler().apply_approved()
    assert stack.inbox("ana") == []


def test_the_teams_card_carries_no_link_but_the_approval_pages(stack):
    """In Teams the card goes instead of the text, and its TextBlocks render Markdown links."""
    before = stack.gateway.scenario.settings()
    data = yaml.safe_load(before.raw)
    data["serial"] += 1
    data["instances"][f"[Review and approve]({EVIL})"] = {
        "definition": "assistant", "serves": ["omar"], "parts": ["orders"], "level": 0}
    with pytest.raises(SettingsError):  # no version a card could be made of holds one
        parse_settings(yaml.safe_dump(data).encode())


def test_one_approver_cant_flood_the_others_with_requests(stack, approving, provider):
    """Approval requests aren't urgent messages, so no cap applies to them. Each request that
    differs at all, even in a key a5s ignores, is a new version, and everyone is asked."""
    edited = written(approving, provider)
    for n in range(5):
        api(approving, provider, "/settings/api/requests", person="omar",
            text=yaml.safe_dump({**edited, "note": n}))
    stack.scheduler().apply_approved()
    asked = [m["text"] for m in stack.inbox("ana")]
    assert len(asked) <= 1, f"Ana was asked {len(asked)} times: {asked[0][:120]}..."
