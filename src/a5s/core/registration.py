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
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from a5s import config, db
from a5s.contract import Person
from a5s.core import ledger, samples
from a5s.core.ledger import canonical

ORIGIN = "a5s"  # the store a5s's registrations say they came from
UPDATABLE = ("displayName", "description", "ownerIds", "sourceAgentId", "originatingStore",
             "managedByAppId", "agentIdentityId", "agentIdentityBlueprintId",
             "sourceLastModifiedDateTime", "agentCard")  # what a registration's update takes
WORDS = re.compile(r"^description:\s*(.+)$", re.MULTILINE)  # a skill's own words for itself
RETRY = timedelta(hours=1)  # a refusal of what's unchanged is asked again once in this long
REGISTRATIONS = "/beta/copilot/agentRegistrations"
IDENTITIES = "/beta/serviceprincipals/Microsoft.Graph.AgentIdentity"


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
        try:  # whatever it answered, a refusal unless a token a5s can read (round 12, D9)
            found = answer.json() if answer.headers.get("content-type", "").startswith(
                "application/json") else {}
        except ValueError:
            found = {}
        found = found if isinstance(found, dict) else {}
        if answer.status_code >= 400 or not isinstance(found.get("access_token"), str):
            raise RegistryError(f"the tenant didn't sign the core in: HTTP {answer.status_code} "
                                f"{str(found.get('error') or '')[:60]}".strip())
        lasts = float(found.get("expires_in") or 3600)
        self._token = (found["access_token"], time.monotonic() + max(lasts - 60, 30))
        return found["access_token"]

    def call(self, method: str, path: str, body: dict | None = None,
             params: dict | None = None) -> tuple[int, dict]:
        """A Graph call, as the core's app: its status, and what it answered, if JSON."""
        headers = {"Authorization": f"Bearer {self.token()}", "OData-Version": "4.0"}
        try:
            answer = self.http.request(method, f"{self.graph}{path}", json=body, headers=headers,
                                       params=params, follow_redirects=False)
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


def levels(inst: dict, caps: dict[tuple[str, str], int]) -> tuple[dict, dict]:
    """How far an instance acts in each of its parts, and for each type of change its settings
    give a level of its own there, held to a5s's cap: level 2 is only ever one of those."""
    parts = {p: (lv if lv is not None else inst["level"]) for p, lv in (inst.get("parts") or {}).items()}
    actions = {p: {a: min(lv, caps.get((p, a), 1)) for a, lv in sorted(given.items())}
               for p, given in sorted((inst.get("actions") or {}).items())}
    return dict(sorted(parts.items())), actions


def said(inst: dict, definition: Any, owners: list[str], registry: Registry,
         public_url: str | None, identity: str | None, first: datetime,
         caps: dict[tuple[str, str], int] | None = None) -> dict:
    """What a5s registers of an instance: what its signed settings and release say of it, with
    how far it acts in each part, and each type of change it makes alone, at level 2 (round 12,
    D1)."""
    parts, actions = levels(inst, caps or {})
    page = f"{public_url}/studio/agents/{definition.id}" if public_url else None
    body = {
        "displayName": f"{inst['id']} ({definition.id})"[:256],
        "description": f"{definition.does} For {definition.works_for}."[:1024],
        "ownerIds": owners,
        "createdBy": owners[0] if owners else registry.client_id,
        "sourceAgentId": inst["id"],
        "originatingStore": ORIGIN,
        "managedByAppId": registry.client_id,
        "sourceCreatedDateTime": first.astimezone(UTC).isoformat(),
        "sourceLastModifiedDateTime": inst["updated_at"].isoformat(),
        "agentCard": {
            "name": inst["id"], "version": inst["release"], "description": definition.does,
            "provider": {"organization": ORIGIN, **({"url": public_url} if public_url else {})},
            **({"url": page} if page else {}),
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
            "skills": skills(definition),
            "a5s": {"agent": definition.id, "status": inst["status"], "level": inst["level"],
                    "parts": parts, "actions": actions},
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


def _listed(registry: Registry, path: str, filter_: str) -> list[str]:
    """What the tenant holds at `path` that `filter_` names, by id: none, if it can't say, as a
    preview API may not."""
    try:
        status, found = registry.call("GET", path, params={"$filter": filter_})
    except RegistryError:
        return []
    if status >= 400:
        return []
    return [str(v["id"]) for v in found.get("value") or [] if isinstance(v, dict) and v.get("id")]


def _theirs(registry: Registry, inst_id: str) -> tuple[list[str], list[str]]:
    """The registrations and agent identities the tenant holds of an instance, a5s's own: those
    it made though Graph's answer never came back among them (round 12, D2)."""
    quoted = inst_id.replace("'", "''")
    return (_listed(registry, REGISTRATIONS,
                    f"sourceAgentId eq '{quoted}' and originatingStore eq '{ORIGIN}'"),
            _listed(registry, IDENTITIES, f"displayName eq '{quoted}' and "
                    f"agentIdentityBlueprintId eq '{registry.client_id}'"))


def sweep(conn_url: str, registry: Registry, scenario: Any, definitions: dict,
          public_url: str | None, keys: tuple[str, ...] = ()) -> list[dict]:
    """Bring the tenant's registry into line with the instances a5s runs: what changed. The
    caller has checked the settings in force; nothing here holds a transaction while it calls.
    A refusal of what's unchanged is asked again once an hour, and recorded as it changes."""
    with db.transaction(conn_url) as conn:
        insts = conn.execute("select id, definition, release, status, level, owner, deputy, "
                             "parts, actions, updated_at from instances order by id").fetchall()
        kept = {r["instance_id"]: r for r in conn.execute("select * from registrations")}
        caps = {r: samples.caps(conn, keys, r) for r in {i["release"] for i in insts}}
        clock = conn.execute("select now() as at").fetchone()
        now = clock["at"] if clock else datetime.now(UTC)
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
        moved = row is not None and row.get("tenant") not in (None, registry.tenant)
        identity = row["identity"] if row and not moved else None
        registration = row["registration"] if row and not moved else None
        sponsors = list(row.get("sponsors") or []) if row and not moved else []
        first = row["first_registered"] if row else datetime.now().astimezone()
        body = said(inst, definition, owners, registry, public_url, identity, first,
                    caps.get(inst["release"]))
        if row and not moved and row["said_sha"] == digest(body):
            if not row["problem"] and registration:
                continue  # as registered
            if row["problem"] and row["registered_at"] and row["registered_at"] > now - RETRY:
                continue  # refused lately, and nothing's changed: asked again in a while
        action = "update" if registration else "register"
        try:
            if registry.identities and owners and not identity:
                found = _theirs(registry, inst["id"])[1]  # one made though its answer was lost
                identity = found[0] if found else _identity(registry, inst, owners)
                sponsors = sponsors or owners
                body = said(inst, definition, owners, registry, public_url, identity, first,
                            caps.get(inst["release"]))
            elif identity and owners and set(owners) != set(sponsors or owners):
                _sponsored(registry, identity, owners, sponsors)  # they follow its owners
            sponsors = owners if identity else []
            status, found = 404, {}
            if registration:
                status, found = registry.call("PATCH", f"{REGISTRATIONS}/{registration}",
                                              {k: v for k, v in body.items() if k in UPDATABLE})
            if not registration or status == 404:  # never made, or removed in the tenant since
                registration = next(iter(_theirs(registry, inst["id"])[0]), None)
                if registration:  # one Graph made, though its answer never came back
                    action = "update"
                    status, found = registry.call("PATCH", f"{REGISTRATIONS}/{registration}",
                                                  {k: v for k, v in body.items() if k in UPDATABLE})
                else:
                    action = "register"
                    status, found = registry.call("POST", REGISTRATIONS, body)
                    registration = found.get("id") if status < 400 else None
            problem = None if status < 400 and registration else _refused(status, found)
        except RegistryError as exc:
            problem = str(exc)
        with db.transaction(conn_url) as conn:  # what's refused is tried again in a while
            conn.execute(
                "insert into registrations (instance_id, registration, identity, said_sha, "
                "first_registered, registered_at, problem, tenant, sponsors) values (%s, %s, %s, "
                "%s, %s, now(), %s, %s, %s) on conflict (instance_id) do update set registration "
                "= excluded.registration, identity = excluded.identity, said_sha = "
                "excluded.said_sha, registered_at = excluded.registered_at, problem = "
                "excluded.problem, tenant = excluded.tenant, sponsors = excluded.sponsors",
                (inst["id"], registration, identity, digest(body), first, problem,
                 registry.tenant, sponsors))
            if not row or moved or problem is None or problem != row["problem"]:
                ledger.append(conn, {  # as it changes: a lasting refusal is one entry
                    "kind": "registry", "action": action, "run": None, "instance": inst["id"],
                    "acts_for": [], "decision": "record",
                    "args": {"registration": registration, "identity": identity,
                             **({"moved_from": row.get("tenant")} if moved and row else {})},
                    "outcome": {"problem": problem}})
        changed.append({"instance": inst["id"], "action": action, "problem": problem})
    for row in kept.values():  # an instance a5s no longer has at all
        changed.append(_unregister(conn_url, registry, row))
    return changed


def _sponsored(registry: Registry, identity: str, owners: list[str], sponsors: list[str]) -> None:
    """An agent identity's sponsors made its instance's owner and deputy, as they are now."""
    for oid in [o for o in owners if o not in sponsors]:
        status, found = registry.call("POST", f"/beta/serviceprincipals/{identity}/sponsors/$ref",
                                      {"@odata.id": f"{registry.graph}/v1.0/users/{oid}"})
        if status >= 400:
            raise RegistryError(f"the tenant didn't add a sponsor: {_refused(status, found)}")
    for oid in [s for s in sponsors if s not in owners]:
        status, found = registry.call("DELETE", f"/beta/serviceprincipals/{identity}/sponsors/{oid}/$ref")
        if status >= 400 and status != 404:
            raise RegistryError(f"the tenant didn't remove a sponsor: {_refused(status, found)}")


def _identity(registry: Registry, inst: dict, sponsors: list[str]) -> str:
    """A new Entra agent identity for an instance, under the deployment's blueprint."""
    status, found = registry.call("POST", IDENTITIES, {
        "@odata.type": "Microsoft.Graph.AgentIdentity", "displayName": inst["id"],
        "agentIdentityBlueprintId": registry.client_id,
        "sponsors@odata.bind": [f"{registry.graph}/v1.0/users/{oid}" for oid in sponsors]})
    if status >= 400 or not isinstance(found.get("id"), str):
        raise RegistryError(f"the tenant didn't make its agent identity: {_refused(status, found)}")
    return found["id"]


def _unregister(conn_url: str, registry: Registry, row: dict) -> dict:
    """Take a retired instance out of the registry, and its agent identity away, if it has one:
    every one the tenant holds of it, those a lost answer left among them."""
    problem = None
    try:
        here = row.get("tenant") in (None, registry.tenant)  # another tenant's a5s can't reach
        regs, ids = _theirs(registry, row["instance_id"])
        known = (([row["registration"]] if row["registration"] and here else []) + regs,
                 ([row["identity"]] if row["identity"] and here else []) + ids)
        for path in ([f"{REGISTRATIONS}/{r}" for r in dict.fromkeys(known[0])]
                     + [f"/beta/serviceprincipals/{i}" for i in dict.fromkeys(known[1])]):
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
