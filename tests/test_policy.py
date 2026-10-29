import pytest

from a5s.core.policy import PolicyEngine


def instance(status="active", level=1, grants=("search_records", "create_draft"), model="fake"):
    return {
        "uid": {"type": "Instance", "id": "assistant-finance"},
        "attrs": {"status": status, "level": level, "grants": list(grants), "model": model,
                  "serves": ["ana"]},
        "parents": [],
    }


def tool(name="search_records", writes=False, pinned=True):
    return {
        "uid": {"type": "Tool", "id": name},
        "attrs": {"name": name, "known": True, "pinned": pinned, "reads": True, "writes": writes,
                  "destructive": False, "sends_outside": False},
        "parents": [],
    }


def call(engine, inst, resource, context=None):
    return engine.decide(
        principal=inst["uid"], action="call_tool", resource=resource["uid"],
        context={"level": inst["attrs"]["level"], "read_outside": False, "acts_for": ["ana"]}
        if context is None else context,
        entities=[inst, resource],
    )


@pytest.fixture(scope="module")
def engine():
    return PolicyEngine()


def test_a_granted_tool_is_allowed_and_says_why(engine):
    d = call(engine, instance(), tool())
    assert d.allowed and d.reasons == ("active-instances-use-their-grant",)


def test_anything_not_granted_is_denied_by_default(engine):
    d = call(engine, instance(), tool("delete_everything"))
    assert not d.allowed and d.reasons == ()


def test_a_suspended_instance_is_denied(engine):
    d = call(engine, instance(status="suspended"), tool())
    assert not d.allowed and "only-active-instances-act" in d.reasons


def test_level_0_only_observes(engine):
    d = call(engine, instance(level=0), tool("create_draft", writes=True))
    assert not d.allowed and "level-0-only-observes" in d.reasons


def test_a_tool_whose_schema_changed_is_refused(engine):
    d = call(engine, instance(), tool(pinned=False))
    assert not d.allowed and "tools-match-the-release" in d.reasons


def test_missing_facts_fail_closed(engine):
    d = call(engine, instance(), tool(), context={"level": 1})  # no read_outside
    assert not d.allowed and d.errors


def test_a_scenario_pack_can_only_restrict():
    with pytest.raises(ValueError, match="only add restrictions"):
        PolicyEngine(packs=('permit (principal, action, resource);',))


def test_a_pack_that_names_unknown_facts_fails_to_load():
    with pytest.raises(ValueError, match="schema"):
        PolicyEngine(packs=('forbid (principal, action, resource is Tool) when { resource.cost > 5 };',))


def test_a_scenario_pack_adds_a_restriction():
    pack = '@id("no-drafts-here")\nforbid (principal, action, resource is Tool) when { resource.name == "create_draft" };'
    d = call(PolicyEngine(packs=(pack,)), instance(), tool("create_draft", writes=True))
    assert not d.allowed and d.reasons == ("no-drafts-here",)
