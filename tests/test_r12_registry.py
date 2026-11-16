"""Round 12 of the critique: IT's inventory in the Microsoft tenant (docs/critique.md, round 12,
D1-D3, D7-D10). It shows a type of change an instance makes alone, at level 2; a registration or
an agent identity Graph made though its answer was lost is found and kept, not made twice, and
goes when its instance retires; one removed in the tenant is listed again; a lasting refusal is
recorded once, and tried again less often; an answer a5s can't read is a refusal, never a crash;
and an identity's sponsors follow its instance's owners."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import yaml

from a5s.core import registration
from conftest import raise_cap
from test_registration import ANA, BEN, GRAPH, Tenant

CHEN, DANA = "0a5a0000-0000-4000-8000-00000000c0c3", "0a5a0000-0000-4000-8000-00000000e0e5"
SPONSORS = "/sponsors"


class Strict(Tenant):
    """The tenant as Graph answers: 404 for a registration it doesn't hold; its lists, filtered as
    a5s asks; an identity's sponsors; and, if asked, an answer that never comes back, though Graph
    made what it was asked for."""

    def __init__(self) -> None:
        super().__init__()
        self.lose: set[str] = set()  # the paths whose POST's answer is lost
        self.token_body: bytes | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "login.microsoftonline.com" and self.token_body is not None:
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  content=self.token_body)
        if request.url.host != "login.microsoftonline.com":
            if request.method == "GET":
                self.calls.append(("GET", path))
                asked = parse_qs(urlsplit(str(request.url)).query).get("$filter", [""])[0]
                held = (self.registrations if path == "/beta/copilot/agentRegistrations"
                        else self.identities)
                return httpx.Response(200, json={"value": [
                    {"id": k} for k, v in held.items()
                    if f"'{v.get('sourceAgentId', v.get('displayName'))}'" in asked]})
            if path.startswith("/beta/copilot/agentRegistrations/") and \
                    path.rsplit("/", 1)[1] not in self.registrations:
                self.calls.append((request.method, path))
                return httpx.Response(404, json={"error": {"code": "ResourceNotFound"}})
            if SPONSORS in path:
                self.calls.append((request.method, path))
                identity = path.split("/")[3]
                bound = self.identities[identity].setdefault("sponsors@odata.bind", [])
                if request.method == "POST":
                    bound.append(json.loads(request.content)["@odata.id"])
                else:
                    oid = path.split("/")[5]
                    bound[:] = [b for b in bound if not b.endswith(oid)]
                return httpx.Response(204)
        answer = super().__call__(request)
        if request.method == "POST" and path in self.lose:
            raise httpx.ReadTimeout("timed out", request=request)  # made, but a5s never hears
        return answer


def registry(tenant: Tenant, identities: bool = False) -> registration.Registry:
    return registration.Registry("tenant-1", "a5s-app", "s3cret", identities=identities,
                                 http=httpx.Client(transport=httpx.MockTransport(tenant)))


def sweep(stack) -> list[dict]:
    with stack.client() as c:
        r = c.post("/registry/sweep")
    r.raise_for_status()
    return r.json()["changed"]


def entries(stack) -> list[dict]:
    return [e for e in stack.ledger() if e["kind"] == "registry"]


def later(stack) -> None:
    """An hour on, when a5s asks again what the tenant refused."""
    from a5s import db
    with db.transaction(stack.admin) as conn:
        conn.execute("update registrations set registered_at = registered_at - interval '2 hours'")


def test_the_inventory_shows_a_type_of_change_made_alone_at_level_2(stack):
    tenant = Tenant()
    stack.gateway.registry = registry(tenant)
    sweep(stack)
    assert not stack.settle(parts={"billing": {"level": 1, "actions": {"change-due-date": 2}}}).refused
    sweep(stack)
    [before] = tenant.registrations.values()
    assert before["agentCard"]["a5s"]["actions"] == {"billing": {"change-due-date": 1}}  # a5s's cap
    raise_cap(stack)  # graded samples raised it: it makes due dates alone in billing
    sweep(stack)
    [after] = tenant.registrations.values()
    assert after["agentCard"]["a5s"]["actions"] == {"billing": {"change-due-date": 2}}
    assert after["agentCard"]["a5s"]["parts"] == {"billing": 1}


def test_a_registration_made_though_its_answer_was_lost_is_kept_not_made_twice(stack):
    tenant = Strict()
    tenant.lose = {"/beta/copilot/agentRegistrations"}
    stack.gateway.registry = registry(tenant)
    assert sweep(stack)[0]["problem"]  # Graph made reg-1, and a5s never heard
    tenant.lose = set()
    later(stack)
    assert sweep(stack)[0]["problem"] is None
    assert list(tenant.registrations) == ["reg-1"]  # found, and kept
    assert not stack.settle(instances={}).refused  # it retires
    sweep(stack)
    assert tenant.registrations == {}


def test_an_identity_made_though_its_answer_was_lost_goes_with_its_instance(stack):
    tenant = Strict()
    tenant.lose = {"/beta/serviceprincipals/Microsoft.Graph.AgentIdentity"}
    stack.gateway.registry = registry(tenant, identities=True)
    sweep(stack)
    tenant.lose = set()
    later(stack)
    sweep(stack)
    assert list(tenant.identities) == ["identity-1"]  # found, not made again
    assert not stack.settle(instances={}).refused
    sweep(stack)
    assert tenant.identities == {} and tenant.registrations == {}


def test_a_registration_removed_in_the_tenant_is_listed_again(stack):
    tenant = Strict()
    stack.gateway.registry = registry(tenant)
    assert sweep(stack)[0]["problem"] is None
    tenant.registrations.clear()  # IT's administrator removes it in Agent 365
    assert not stack.settle(level=0).refused  # and something about it changes
    [found] = sweep(stack)
    assert found["problem"] is None and len(tenant.registrations) == 1


def test_a_lasting_refusal_is_recorded_once_and_tried_again_less_often(stack):
    tenant = Tenant()
    tenant.refuse = 403
    stack.gateway.registry = registry(tenant)
    sweep(stack)
    asked = len(tenant.calls)
    for _ in range(5):
        sweep(stack)
    assert len(tenant.calls) == asked  # not asked again within the hour
    later(stack)
    sweep(stack)
    assert len(tenant.calls) > asked  # and asked again after it
    assert len(entries(stack)) == 1  # what's refused, recorded as it first was, once


def test_an_answer_a5s_cant_read_is_a_refusal_never_a_crash(stack):
    tenant = Strict()
    tenant.token_body = b"<html>not json</html>"
    stack.gateway.registry = registry(tenant)
    [found] = sweep(stack)
    assert "sign the core in" in found["problem"], found


def test_an_identitys_sponsors_follow_its_instances_owners(stack):
    tenant = Strict()
    stack.gateway.registry = registry(tenant, identities=True)
    sweep(stack)
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    moved = {**settings["instances"]["assistant-finance"], "owner": "chen", "deputy": "dana"}
    assert not stack.settle(instances={**settings["instances"], "assistant-finance": moved}).refused
    sweep(stack)
    [identity] = tenant.identities.values()
    assert sorted(identity["sponsors@odata.bind"]) == sorted(
        f"{GRAPH}/v1.0/users/{oid}" for oid in (CHEN, DANA))
    assert f"{GRAPH}/v1.0/users/{ANA}" not in identity["sponsors@odata.bind"]
    assert f"{GRAPH}/v1.0/users/{BEN}" not in identity["sponsors@odata.bind"]
