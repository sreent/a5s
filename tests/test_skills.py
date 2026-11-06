"""Skills: Agent Skills a release brings, one folder each under its definition's skills/, which a
run is told of by name and purpose and reads only when it needs one, and can't change. The
definition's digest, and so the release, pins them."""

import json

import pytest

from a5s import definitions

SKILL = """---
name: refunds
description: How to answer a customer's question about a refund, step by step.
---

# Refunds

Check the question's record first, then say when its refund is paid, as the record says.
"""
BODY = "Check the question's record first"


def with_skill(stack, text: str = SKILL, name: str = "refunds") -> None:
    """A new release of the assistant, with a skill, applied."""
    folder = stack.cfg.agents_dir / "assistant" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(text)
    stack.gateway.definitions = definitions.load_all(stack.cfg.agents_dir)
    assert not stack.settle().refused


def test_a_run_is_told_of_each_skill_and_reads_it_only_when_it_needs_it(stack):
    with_skill(stack)
    stack.model.reply(None, ("read_file", {"file_path": "/skills/refunds/SKILL.md"}))
    stack.model.reply("Q-1002's refund is paid when its record says.")
    stack.say("When is Q-1002's refund paid?")
    first, second = (r["body"] for r in stack.model.requests[:2])
    told = json.dumps(first["messages"][0])
    assert "refunds" in told and "How to answer a customer's question about a refund" in told
    assert BODY not in told  # only once it's read
    assert BODY in json.dumps(second["messages"][-1])
    offered = {t["function"]["name"] for t in first["tools"]}
    assert "read_file" in offered and not offered & {"write_file", "edit_file", "execute"}


def test_a_release_without_skills_offers_none(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    assert "/skills/" not in json.dumps(stack.model.requests[0]["body"]["messages"][0])


def test_a_skill_must_say_its_name_and_what_its_for(tmp_path):
    folder = tmp_path / "skills" / "refunds"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("# Refunds\n")
    with pytest.raises(ValueError, match="front matter"):
        definitions.skills_of(tmp_path / "skills")
    (folder / "SKILL.md").write_text(SKILL.replace("name: refunds", "name: payments"))
    with pytest.raises(ValueError, match="naming it refunds"):
        definitions.skills_of(tmp_path / "skills")


def test_a_skill_is_part_of_its_release(stack):
    before = stack.gateway.definitions["assistant"].digest
    with_skill(stack)
    after = stack.gateway.definitions["assistant"]
    assert after.digest != before and after.skills == {"/skills/refunds/SKILL.md": SKILL}
