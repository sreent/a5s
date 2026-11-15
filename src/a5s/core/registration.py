"""IT's one inventory: each instance a5s runs, mirrored into the organisation's Microsoft tenant
(docs/administration.md#its-inventory-in-microsoft-365).

a5s stays the authority. What's registered is what its signed settings and release say, and
nothing in the tenant gives an agent anything in a5s. For each instance at work or suspended,
the core registers it in Agent 365's agent registry, through the Agent Registration API: by its
id, with what its agent does and whom it works for, its release, level and parts, its owner and
deputy as owners, and a link to its agent's page in the studio. It updates the registration
when what it says changes, and deletes it once the instance retires. Where a deployment asks,
each instance gets an Entra agent identity too, under the deployment's agent identity
blueprint, which the core signs in as, with its owner and deputy as sponsors, and its
registration names it. While the settings in force don't check out, a5s changes nothing there.
Each change is in the ledger, and what the tenant last refused is kept beside the instance.

Both are Microsoft Graph's preview APIs, which Microsoft doesn't yet support in production, so
a deployment turns this on by naming its tenant (A5S_REGISTRY_TENANT), and reads the ledger for
what each call answered.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from a5s import config, db
from a5s.contract import Person
from a5s.core import ledger
from a5s.core.ledger import canonical

ORIGIN = "a5s"  # the store a5s's registrations say they came from
UPDATABLE = ("displayName", "description", "ownerIds", "sourceAgentId", "originatingStore",
             "managedByAppId", "agentIdentityId", "agentIdentityBlueprintId",
             "sourceLastModifiedDateTime", "agentCard")  # what a registration's update takes
WORDS = re.compile(r"^description:\s*(.+)$", re.MULTILINE)  # a skill's own words for itself


class RegistryError(RuntimeError):
    """What the tenant answered that a5s couldn't use, without anything it was sent."""


@dataclass
class Registry:
    """The tenant a5s's instances are registered in, and the app the core signs in as."""

    tenant: str
    client_id: str
    secret: str
    identities: bool = False
    graph: str = "https://graph.microsoft.com"
    login: str = "https://login.microsoftonline.com"
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=30))
    _token: tuple[str, float] | None = None

    @classmethod
    def from_env(cls) -> Registry | None:
        """The deployment's, or None if it names no tenant."""
        if not (tenant := config.REGISTRY_TENANT.read()):
            return None
        client, secret = config.REGISTRY_CLIENT_ID.read(), config.REGISTRY_SECRET.read()
        if not client or not secret:
            raise config.ConfigError("A5S_REGISTRY_TENANT needs A5S_REGISTRY_CLIENT_ID and "
                                     "A5S_REGISTRY_SECRET, the app the core signs in as")
        return cls(tenant, client, secret, config.REGISTRY_IDENTITIES.read(),
                   config.REGISTRY_GRAPH.read(), config.REGISTRY_LOGIN.read())

    def token(self) -> str:
        """A token for Graph, by the app's own credentials, kept until a minute before it lapses."""
        if self._token and self._token[1] > time.monotonic():
            return self._token[0]
        try:
            answer = self.http.post(f"{self.login}/{self.tenant}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": self.client_id,
                "client_secret": self.secret, "scope": f"{self.graph}/.default"})
        except httpx.HTTPError as exc:
            raise RegistryError(f"the tenant's sign-in couldn't be reached: {type(exc).__name__}") from None
        found = answer.json() if answer.headers.get("content-type", "").startswith(
            "application/json") else {}
        if answer.status_code >= 400 or not isinstance(found.get("access_token"), str):
            raise RegistryError(f"the tenant didn't sign the core in: HTTP {answer.status_code} "
                                f"{str(found.get('error') or '')[:60]}".strip())
        lasts = float(found.get("expires_in") or 3600)
        self._token = (found["access_token"], time.monotonic() + max(lasts - 60, 30))
        return found["access_token"]

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """A Graph call, as the core's app: its status, and what it answered, if JSON."""
        headers = {"Authorization": f"Bearer {self.token()}", "OData-Version": "4.0"}
        try:
            answer = self.http.request(method, f"{self.graph}{path}", json=body, headers=headers,
                                       follow_redirects=False)
        except httpx.HTTPError as exc:
            raise RegistryError(f"Microsoft Graph couldn't be reached: {type(exc).__name__}") from None
        try:
            found = answer.json() if answer.content else {}
        except ValueError:
            found = {}
        return answer.status_code, found if isinstance(found, dict) else {}


def entra_ids(person: Person | None) -> list[str]:
    """Someone's Entra object ids, as the directory gives them: entra:<object id>."""
    return [i.removeprefix("entra:") for i in (person.identities if person else ())
            if i.startswith("entra:")]


def skills(definition: Any) -> list[dict]:
    """An agent's skills, by their names and their own words, for its card."""
    found = []
    for path, text in sorted((definition.skills or {}).items()):
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
            words = WORDS.search(text)
            found.append({"id": parts[1], "name": parts[1],
                          "description": (words.group(1).strip() if words else parts[1])[:300]})
    return found


def said(inst: dict, definition: Any, owners: list[str], registry: Registry,
         public_url: str | None, identity: str | None, first: datetime) -> dict:
    """What a5s registers of an instance: what its signed settings and release say of it."""
    page = f"{public_url}/studio/agents/{definition.id}" if public_url else None
    body = {
        "displayName": f"{inst['id']} ({definition.id})"[:256],
        "description": f"{definition.does} For {definition.works_for}."[:1024],
        "ownerIds": owners,
        "createdBy": owners[0] if owners else registry.client_id,
        "sourceAgentId": inst["id"],
        "originatingStore": ORIGIN,
        "managedByAppId": registry.client_id,
        "sourceCreatedDateTime": first.isoformat(),
        "sourceLastModifiedDateTime": inst["updated_at"].isoformat(),
        "agentCard": {
            "name": inst["id"], "version": inst["release"], "description": definition.does,
            "provider": {"organization": ORIGIN, **({"url": public_url} if public_url else {})},
            **({"url": page} if page else {}),
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
            "skills": skills(definition),
            "a5s": {"agent": definition.id, "status": inst["status"], "level": inst["level"],
                    "parts": sorted(inst.get("parts") or {})},
        },
    }
    if identity:
        body["agentIdentityId"] = identity
        body["agentIdentityBlueprintId"] = registry.client_id
    return body


def digest(body: dict) -> str:
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def _refused(status: int, found: dict) -> str:
    error = found.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    return f"HTTP {status} {str(code or '')[:60]}".strip()


def sweep(conn_url: str, registry: Registry, scenario: Any, definitions: dict,
          public_url: str | None) -> list[dict]:
    """Bring the tenant's registry into line with the instances a5s runs: what changed. The
    caller has checked the settings in force; nothing here holds a transaction while it calls."""
    with db.transaction(conn_url) as conn:
        insts = conn.execute("select id, definition, release, status, level, owner, deputy, "
                             "parts, updated_at from instances order by id").fetchall()
        kept = {r["instance_id"]: r for r in conn.execute("select * from registrations")}
    changed: list[dict] = []
    for inst in insts:
        row = kept.pop(inst["id"], None)
        definition = definitions.get(inst["definition"])
        if inst["status"] not in ("active", "suspended") or definition is None:
            if row:
                changed.append(_unregister(conn_url, registry, row))
            continue
        owners = list(dict.fromkeys(oid for pid in (inst["owner"], inst["deputy"]) if pid
                                    for oid in entra_ids(scenario.person(pid))))
        identity = row["identity"] if row else None
        registration = row["registration"] if row else None
        first = row["first_registered"] if row else datetime.now().astimezone()
        body: dict = {}
        try:
            if registry.identities and not identity and owners:
                identity = _identity(registry, inst, owners)
            body = said(inst, definition, owners, registry, public_url, identity, first)
            if registration and row and row["said_sha"] == digest(body):
                continue  # as registered
            if registration:
                action = "update"
                status, found = registry.call(
                    "PATCH", f"/beta/copilot/agentRegistrations/{registration}",
                    {k: v for k, v in body.items() if k in UPDATABLE})
            else:
                action = "register"
                status, found = registry.call("POST", "/beta/copilot/agentRegistrations", body)
                registration = found.get("id") if status < 400 else None
            problem = None if status < 400 and registration else _refused(status, found)
        except RegistryError as exc:
            action, problem = ("update" if registration else "register"), str(exc)
        with db.transaction(conn_url) as conn:  # what's refused is tried again at the next sweep
            conn.execute(
                "insert into registrations (instance_id, registration, identity, said_sha, "
                "first_registered, registered_at, problem) values (%s, %s, %s, %s, %s, now(), %s) "
                "on conflict (instance_id) do update set registration = excluded.registration, "
                "identity = excluded.identity, said_sha = excluded.said_sha, "
                "registered_at = excluded.registered_at, problem = excluded.problem",
                (inst["id"], registration, identity, None if problem else digest(body), first,
                 problem))
            ledger.append(conn, {"kind": "registry", "action": action, "run": None,
                                 "instance": inst["id"], "acts_for": [], "decision": "record",
                                 "args": {"registration": registration, "identity": identity},
                                 "outcome": {"problem": problem}})
        changed.append({"instance": inst["id"], "action": action, "problem": problem})
    for row in kept.values():  # an instance a5s no longer has at all
        changed.append(_unregister(conn_url, registry, row))
    return changed


def _identity(registry: Registry, inst: dict, sponsors: list[str]) -> str:
    """A new Entra agent identity for an instance, under the deployment's blueprint."""
    status, found = registry.call("POST", "/beta/serviceprincipals/Microsoft.Graph.AgentIdentity", {
        "@odata.type": "Microsoft.Graph.AgentIdentity", "displayName": inst["id"],
        "agentIdentityBlueprintId": registry.client_id,
        "sponsors@odata.bind": [f"{registry.graph}/v1.0/users/{oid}" for oid in sponsors]})
    if status >= 400 or not isinstance(found.get("id"), str):
        raise RegistryError(f"the tenant didn't make its agent identity: {_refused(status, found)}")
    return found["id"]


def _unregister(conn_url: str, registry: Registry, row: dict) -> dict:
    """Take a retired instance out of the registry, and its agent identity away, if it has one."""
    problem = None
    try:
        for path in ((f"/beta/copilot/agentRegistrations/{row['registration']}",)
                     if row["registration"] else ()) + (
                (f"/beta/serviceprincipals/{row['identity']}",) if row["identity"] else ()):
            status, found = registry.call("DELETE", path)
            if status >= 400 and status != 404:  # gone already is gone
                problem = _refused(status, found)
    except RegistryError as exc:
        problem = str(exc)
    with db.transaction(conn_url) as conn:
        if problem:
            conn.execute("update registrations set problem = %s where instance_id = %s",
                         (problem, row["instance_id"]))
        else:
            conn.execute("delete from registrations where instance_id = %s", (row["instance_id"],))
        ledger.append(conn, {"kind": "registry", "action": "unregister", "run": None,
                             "instance": row["instance_id"], "acts_for": [], "decision": "record",
                             "args": {"registration": row["registration"],
                                      "identity": row["identity"]},
                             "outcome": {"problem": problem}})
    return {"instance": row["instance_id"], "action": "unregister", "problem": problem}
