"""IT's one inventory (core/registration.py): each instance a5s runs, mirrored into the
organisation's Microsoft tenant, in Agent 365's agent registry, with an Entra agent identity of
its own where the deployment asks. a5s stays the authority: it registers what its settings and
release say, updates only what changed, and takes an instance away once it retires. The tenant
here is a fake of Microsoft Graph's preview APIs, as their docs describe them."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
import yaml

from a5s import db
from a5s.core import registration

ANA, BEN = "0a5a0000-0000-4000-8000-00000000a0a1", "0a5a0000-0000-4000-8000-00000000b0b2"
GRAPH = "https://graph.microsoft.com"


class Tenant:
    """Microsoft Graph's agent registry and agent identities, and the tenant's sign-in."""

    def __init__(self) -> None:
        self.registrations: dict[str, dict] = {}
        self.identities: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.refuse: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "login.microsoftonline.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            assert form["client_id"] == "a5s-app" and form["grant_type"] == "client_credentials"
            return httpx.Response(200, json={"access_token": "t0ken", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer t0ken"
        assert request.headers["OData-Version"] == "4.0"
        self.calls.append((request.method, path))
        if self.refuse:
            return httpx.Response(self.refuse, json={"error": {"code": "Forbidden"}})
        body = json.loads(request.content) if request.content else {}
        if request.method == "GET":  # a list, filtered as a5s asks, of what it holds
            asked = request.url.params.get("$filter", "")
            held = self.registrations if path == "/beta/copilot/agentRegistrations" else self.identities
            return httpx.Response(200, json={"value": [
                {"id": k} for k, v in held.items()
                if f"'{v.get('sourceAgentId', v.get('displayName'))}'" in asked]})
        if path == "/beta/copilot/agentRegistrations" and request.method == "POST":
            made = f"reg-{len(self.registrations) + 1}"
            self.registrations[made] = body
            return httpx.Response(201, json={"id": made})
        if path.startswith("/beta/copilot/agentRegistrations/"):
            made = path.rsplit("/", 1)[1]
            if request.method == "PATCH":
                assert "createdBy" not in body and "sourceCreatedDateTime" not in body
                self.registrations[made].update(body)
                return httpx.Response(200)
            del self.registrations[made]
            return httpx.Response(204)
        if path == "/beta/serviceprincipals/Microsoft.Graph.AgentIdentity" and request.method == "POST":
            made = f"identity-{len(self.identities) + 1}"
            self.identities[made] = body
            return httpx.Response(201, json={"id": made})
        if path.startswith("/beta/serviceprincipals/") and request.method == "DELETE":
            del self.identities[path.rsplit("/", 1)[1]]
            return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture
def tenant(stack) -> Tenant:
    found = Tenant()
    stack.gateway.registry = registration.Registry(
        "tenant-1", "a5s-app", "s3cret", identities=True,
        http=httpx.Client(transport=httpx.MockTransport(found)))
    return found


def sweep(stack) -> list[dict]:
    with stack.client() as c:
        r = c.post("/registry/sweep")
    r.raise_for_status()
    return r.json()["changed"]


def test_each_instance_is_registered_as_its_settings_and_release_say(stack, tenant):
    assert sweep(stack) == [{"instance": "assistant-finance", "action": "register",
                             "problem": None}]
    [listed] = tenant.registrations.values()
    assert listed["displayName"] == "assistant-finance (assistant)"
    assert listed["ownerIds"] == [ANA, BEN] and listed["originatingStore"] == "a5s"
    assert listed["sourceAgentId"] == "assistant-finance" and listed["managedByAppId"] == "a5s-app"
    assert listed["agentCard"]["a5s"] == {"agent": "assistant", "status": "active", "level": 1,
                                          "parts": {"billing": 1}, "actions": {}}
    [identity] = tenant.identities.values()  # its own, its owner and deputy its sponsors
    assert identity["displayName"] == "assistant-finance"
    assert identity["agentIdentityBlueprintId"] == "a5s-app"
    assert identity["sponsors@odata.bind"] == [f"{GRAPH}/v1.0/users/{ANA}",
                                               f"{GRAPH}/v1.0/users/{BEN}"]
    assert listed["agentIdentityId"] == "identity-1"
    [entry] = [e for e in stack.ledger() if e["kind"] == "registry"]
    assert (entry["action"], entry["args"]["registration"]) == ("register", "reg-1")


def test_it_registers_again_only_what_changed_and_takes_a_retired_instance_away(stack, tenant):
    sweep(stack)
    made = len(tenant.calls)
    assert sweep(stack) == [] and len(tenant.calls) == made  # as registered
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text(encoding="utf-8"))
    instance = {**settings["instances"]["assistant-finance"], "level": 0}
    assert not stack.settle(instances={**settings["instances"], "assistant-finance": instance},
                            signers=("ana",)).refused
    assert sweep(stack) == [{"instance": "assistant-finance", "action": "update",
                             "problem": None}]
    assert tenant.registrations["reg-1"]["agentCard"]["a5s"]["level"] == 0
    assert not stack.settle(instances={}, signers=("ana",)).refused  # it retires
    assert sweep(stack) == [{"instance": "assistant-finance", "action": "unregister",
                             "problem": None}]
    assert tenant.registrations == {} and tenant.identities == {}
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from registrations").fetchone()["n"] == 0


def test_what_the_tenant_refuses_is_kept_and_tried_again(stack, tenant):
    tenant.refuse = 403
    [refused] = sweep(stack)
    assert refused["problem"] == "the tenant didn't make its agent identity: HTTP 403 Forbidden"
    with db.transaction(stack.admin) as conn:
        kept = conn.execute("select * from registrations").fetchone()
    assert kept["registration"] is None and kept["problem"]
    tenant.refuse = None
    assert sweep(stack) == []  # what's unchanged is asked again once in a while, not each sweep
    with db.transaction(stack.admin) as conn:  # an hour on
        conn.execute("update registrations set registered_at = registered_at - interval '2 hours'")
    assert sweep(stack)[0]["problem"] is None and len(tenant.registrations) == 1


def test_with_no_tenant_named_a5s_registers_nothing(stack):
    with stack.client() as c:
        found = c.post("/registry/sweep").json()
    assert found == {"changed": [], "registering": "nothing, since the deployment names no tenant"}


def test_a_registrations_creation_time_is_the_same_after_a_utc_database_round_trip():
    first = datetime(2026, 11, 1, 9, tzinfo=timezone(timedelta(hours=8)))
    inst = {"id": "assistant-finance", "release": "release-1", "status": "active", "level": 1,
            "parts": {}, "actions": {}, "updated_at": first}
    agent = SimpleNamespace(id="assistant", does="Answer questions", works_for="Finance", skills={})
    registry = registration.Registry("tenant-1", "a5s-app", "s3cret")
    local = registration.said(inst, agent, [], registry, None, None, first)
    stored = registration.said(inst, agent, [], registry, None, None, first.astimezone(UTC))
    assert local == stored
    assert local["sourceCreatedDateTime"] == "2026-11-01T01:00:00+00:00"


def test_its_card_names_its_skills_by_their_own_words():
    agent = SimpleNamespace(skills={"/skills/refunds/SKILL.md": "---\nname: refunds\n"
                                    "description: How refunds go.\n---\nAsk billing.\n",
                                    "/skills/refunds/notes.md": "not a skill of its own"})
    assert registration.skills(agent) == [{"id": "refunds", "name": "refunds",
                                           "description": "How refunds go."}]
