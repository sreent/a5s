"""What someone sees of an agent, in layers, each from the roles they hold (core/studio.py,
docs/studio.md#people-roles-and-spaces): that it exists, for anyone with a role on it, the
people it serves, and everyone if its owner lists it; what it may do, for the people it serves
and those who watch its instances; how it's built, its instructions and skills, for its owners,
authors, engineers, release approvers, auditors and viewers; and how it's doing, for those who
watch its instances. An agent someone may not know of is as missing as one there isn't."""

import base64

import httpx
import pytest
import yaml

from a5s import db
from a5s.contract import SettingsError, parse_settings
from a5s.core import memberships
from test_group_roles import approve, in_force, version
from test_studio_pages import signed_in, with_ops


def seen(api, person: str, agent: str = "assistant") -> dict | int:
    found = api(f"/studio/api/agents/{agent}", person)
    return found.json() if found.status_code == 200 else found.status_code


def test_each_role_sees_its_own_layers_of_an_agent(stack, approving, provider):
    with_ops(stack)  # assistant-ops, in orders: Omar runs it, and it serves Chen
    api = signed_in(approving, provider)
    priya = seen(api, "priya")  # who owns the assistant: all of it
    assert list(priya["layers"]) == ["exists", "uses", "built", "doing", "did", "changing"]
    assert priya["instructions"] and priya["tools"] and priya["instances"]
    ana = seen(api, "ana")  # who approves instances and owns billing: how it's doing
    assert list(ana["layers"]) == ["exists", "uses", "doing", "did"]
    assert ana["tools"] and ana["instances"] and "instructions" not in ana and "skills" not in ana
    chen = seen(api, "chen")  # whom it serves: what it may do with her records, no more
    assert list(chen["layers"]) == ["exists", "uses"] and chen["instances"] == []
    assert chen["layers"]["exists"] == ["it serves you, through assistant-ops"]
    rosa = seen(api, "rosa")  # who approves its releases: how it's built, not how it's doing
    assert list(rosa["layers"]) == ["exists", "uses", "built"] and rosa["instances"] == []
    assert "you audit it" in seen(api, "kofi")["layers"]["built"]  # assurance
    assert seen(api, "lena") == 404  # she holds no role on it, and it serves her not
    assert seen(api, "lena", "no-such-agent") == 404  # just as for one there isn't
    assert api("/studio/api", "lena").json()["agents"] == []


def test_an_agent_its_owner_lists_is_known_to_everyone_and_no_more(stack, approving, provider,
                                                                   monkeypatch):
    watcher = stack.gateway.definitions["watcher"]
    monkeypatch.setitem(stack.gateway.definitions, "watcher",
                        watcher.model_copy(update={"listed": True}))
    api = signed_in(approving, provider)
    lena = seen(api, "lena", "watcher")
    assert lena["layers"] == {"exists": ["its owner lists it for everyone"]}
    assert lena["owners"] and lena["does"] and lena["instances"] == []
    assert not {"tools", "model", "triggers", "instructions"} & set(lena)
    assert [a["id"] for a in api("/studio/api", "lena").json()["agents"]] == ["watcher"]
    assert seen(api, "lena") == 404  # the assistant isn't listed


def test_the_settings_give_groups_an_agents_authors_and_viewers_and_no_more():
    base = b"instances:\n  a: {definition: assistant, serves: [ana], parts: [billing]}\n"
    found = parse_settings(base + b"groups:\n  g1: [agent-viewer:assistant, agent-author:assistant]\n")
    assert found.groups == {"g1": ("agent-author:assistant", "agent-viewer:assistant")}
    with pytest.raises(SettingsError):
        parse_settings(base + b"groups: {g1: [agent-owner:assistant]}")  # the directory's alone
    assert memberships.owner_of("agent-viewer:assistant") == "agent-owner:assistant"


def test_a_group_its_owner_gives_an_agents_viewer_sees_how_its_built(stack, approving, provider):
    asked = version(stack, {"assistant-readers": ["agent-viewer:assistant"]})
    told = approve(stack, approving, provider, asked["digest"], "ana")  # who approves instances
    assert any("agent-owner:assistant named in the directory hasn't approved giving "
               "assistant-readers" in need for need in told["needs"]), told
    assert in_force(stack)[0] < asked["serial"]  # it waits for the assistant's owner
    approve(stack, approving, provider, asked["digest"], "priya")  # who owns it
    assert in_force(stack) == (asked["serial"], None)

    def as_lena(*groups: str) -> httpx.Response:
        token = provider.id_token(person="lena", groups=list(groups))
        return httpx.get(f"{approving}/studio/api/agents/assistant", timeout=30,
                         headers={"Authorization": f"Bearer {token}"})

    lena = as_lena("assistant-readers").json()
    assert lena["layers"]["built"] == ["you may see how it's built"] and lena["instructions"]
    assert lena["instances"] == []  # how it's built, not how it's doing
    assert as_lena().status_code == 404  # once a sign-in shows she's left the group


def test_a_group_role_for_an_agent_the_release_hasnt_got_is_refused(stack, approving):
    with db.transaction(stack.admin) as conn:
        raw = bytes(conn.execute("select raw from settings_versions order by serial desc "
                                 "limit 1").fetchone()["raw"])
    settings = yaml.safe_load(raw)
    settings.update(serial=settings["serial"] + 1, groups={"g1": ["agent-viewer:nobody"]})
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(
            yaml.safe_dump(settings).encode()).decode()})
    assert r.status_code == 409 and any("agent-viewer:nobody names an agent no release here has"
                                        in why for why in r.json()["detail"]["reasons"]), r.text
