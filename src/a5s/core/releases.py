"""Releases: what a release of a5s holds, and whether this deployment has approved it.

A release is everything a5s runs. From its image: the trusted core, the
services, and the inputs the image was built from. From the deployment: its
approved models, its scenario's directory and tools, and its agents'
definitions. The release's manifest lists a digest of every file, by part, and
what each agent and model may do, so anyone can work out offline what changed
from one release to the next.

Each organisation's own people approve a release for their deployment, by
signing its manifest. What it needs depends on what changed since the release
they last approved ([independence](../../../docs/architecture.md#independence)):

- the trusted core, or what its image is built from: the release approver, from
  outside the team that runs a5s and its reporting line, and assurance, after
  their tests, as well as an attested build;
- the scenario's directory or tools, or anything that widens what an agent or a
  model may do: the release approver;
- an agent's instructions alone, or anything that narrows it: the agent's owner
  and a second engineer;
- the services alone: an engineer from the team;
- a fix for a security advisory that changes only what the image is built from:
  an engineer, at once.

The core opens no run until the release it is has what it needs, except in
development.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb

import a5s
from a5s import definitions
from a5s.contract import ASSURANCE, RELEASE_APPROVER, Person, Scenario, Signature
from a5s.core import ledger, signing

ENGINEER = "engineer"  # anyone in the team that runs a5s
PARTS = ("core", "services", "build", "models", "scenario")
BUILT_FROM = ("pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore")
_HEADER = ("# A release of a5s: every file it runs, by part, and what each agent and model may\n"
           "# do. An organisation approves it for its deployment by signing exactly these bytes.\n")
_PEOPLE = {RELEASE_APPROVER: "the release approver, from outside the team that runs a5s",
           ASSURANCE: "assurance, after their tests", ENGINEER: "an engineer from the team that runs a5s"}


def agent_owner(agent: str) -> str:
    return f"agent-owner:{agent}"


def who(role: str) -> str:
    """A role in words, such as the assistant's owner."""
    owner = role.removeprefix("agent-owner:")
    return f"the {owner}'s owner" if owner != role else _PEOPLE[role]


# What a release holds

def _files(folder: Path, under: str, leave_out: Callable[[Path], bool] = lambda _: False) -> dict:
    """Every file in a folder, keyed by `under` and its path in the folder, with its digest."""
    found = {}
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        inside = path.relative_to(folder)
        if (path.is_file() and "__pycache__" not in inside.parts and path.suffix != ".pyc"
                and not leave_out(inside)):
            found[f"{under}/{inside.as_posix()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _code(root: Path) -> tuple[dict, dict]:
    """a5s's own code, from the source in a checkout or the installed package in an image:
    the trusted core, and the services."""
    source = root / "src" / "a5s"
    files = _files(source if source.is_dir() else Path(a5s.__file__).parent, "a5s")
    services = {k: v for k, v in files.items() if k.startswith("a5s/services/") or k == "a5s/worker.py"}
    return {k: v for k, v in files.items() if k not in services}, services


def _agent(folder: Path) -> dict:
    d = definitions.load(folder)
    return {
        "release": d.release_id,
        "files": _files(folder, f"agents/{folder.name}"),
        "may": {  # what widening it would change
            "tools": sorted(d.tool_names), "pins": dict(sorted(d.pins.items())), "model": d.model,
            "triggers": d.triggers, "schedules": [s.model_dump() for s in d.schedules],
            "reports": [r.model_dump() for r in d.reports],
            "obligations": sorted(d.obligations), "autonomy": d.autonomy.model_dump(),
            "channels": sorted(d.channels), "budget": d.budget.model_dump(), "context": d.context.model_dump(),
            "scope": d.scope, "reminders": d.reminders, "preferences": sorted(d.preferences),
        },
    }


def _models(config: Path) -> dict:
    path = config / "models.yaml"
    listed = (yaml.safe_load(path.read_text()) or {}).get("models") or {} if path.exists() else {}
    keep = ("provider", "api", "base_url", "model", "reported_model", "region", "data_classes")
    return {alias: {k: m.get(k) for k in keep} for alias, m in sorted(listed.items())}


def manifest(root: Path, scenario_dir: Path, *, built: dict | None = None) -> bytes:
    """The release a5s is here. With `built`, the manifest its image was built with, what
    the image was built from comes from there, since the image doesn't carry it."""
    core, services = _code(root)
    data = {
        "version": built["version"] if built else importlib.metadata.version("a5s"),
        "parts": {
            "core": core,
            "services": services,
            "build": built["parts"]["build"] if built else {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in BUILT_FROM if (root / name).exists()},
            "models": _files(root / "config", "config"),
            # The settings are signed on their own, and private keys never count.
            "scenario": _files(scenario_dir, "scenario", lambda p: p.suffix in (".key", ".md")
                               or p.name in ("settings.yaml", "settings.sig")),
        },
        "models": _models(root / "config"),
        "agents": {f.name: _agent(f) for f in sorted((root / "agents").iterdir())
                   if (f / "agent.yaml").exists()} if (root / "agents").is_dir() else {},
    }
    return (_HEADER + yaml.safe_dump(data, sort_keys=True, width=1000)).encode()


@dataclass(frozen=True)
class Running:
    """The release this a5s is, and why it can't run, if its code isn't what it was built as."""

    raw: bytes
    problems: tuple[str, ...] = ()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    @property
    def version(self) -> str:
        return yaml.safe_load(self.raw)["version"]


def running(root: Path, scenario_dir: Path) -> Running:
    built_path = root / "release.yaml"  # written when the image was built
    built = yaml.safe_load(built_path.read_bytes()) if built_path.exists() else None
    raw = manifest(root, scenario_dir, built=built)
    if built is None:
        return Running(raw)
    now = yaml.safe_load(raw)["parts"]
    changed = sorted(path for part in ("core", "services")
                     for path in set(now[part]) | set(built["parts"][part])
                     if now[part].get(path) != built["parts"][part].get(path))
    if changed:
        return Running(raw, (f"its code isn't what its image was built with: {', '.join(changed[:3])}",))
    return Running(raw)


# What a release needs

@dataclass(frozen=True)
class Need:
    role: str
    why: str


def _widens_agent(old: dict, new: dict) -> list[str]:
    """What an agent may do now that it couldn't before."""
    found = []
    if set(new["tools"]) - set(old["tools"]):
        found.append("uses more tools")
    if any(old["pins"].get(tool) not in (None, pin) for tool, pin in new["pins"].items()):
        found.append("uses a tool that changed")
    if new["model"] != old["model"]:
        found.append("uses another model")
    found += [f"has new {key}" for key in ("triggers", "schedules", "reports")
              if any(item not in old.get(key, []) for item in new.get(key, []))]
    if set(new["obligations"]) - set(old["obligations"]):
        found.append("chases more")
    if any(new["autonomy"][k] > old["autonomy"][k] for k in ("start", "max")):
        found.append("may act more")
    if set(new["channels"]) - set(old["channels"]):
        found.append("reaches more channels")
    if new["reminders"] and not old["reminders"]:
        found.append("records reminders")
    if set(new.get("preferences", [])) - set(old.get("preferences", [])):
        found.append("lets people set more preferences")
    found += [f"has a new {key}" for key in ("budget", "context", "scope") if new[key] != old[key]]
    return found


def _widens_models(old: dict, new: dict) -> list[str]:
    found = []
    for alias, model in new.items():
        before = old.get(alias)
        if before is None:
            found.append(f"{alias} is approved")
        elif {**model, "data_classes": None} != {**before, "data_classes": None}:
            found.append(f"{alias} changed")
        elif set(model["data_classes"] or []) - set(before["data_classes"] or []):
            found.append(f"{alias} may see more classes of data")
    return found


def needs(new: dict, old: dict | None, advisory: str | None = None) -> list[Need]:
    """Whose approval a release needs, given the release approved before it, if any."""
    old = old or {"parts": {}, "models": {}, "agents": {}}
    changed = [part for part in PARTS if new["parts"].get(part) != old["parts"].get(part)]
    if advisory and changed == ["build"] and new["agents"] == old["agents"]:
        return [Need(ENGINEER, f"it fixes {advisory}, and changes only what the image is built from")]
    found = []
    if "core" in changed or "build" in changed:
        why = "the trusted core changed" if "core" in changed else "what the image is built from changed"
        found += [Need(RELEASE_APPROVER, why), Need(ASSURANCE, why)]
    if "scenario" in changed:
        found.append(Need(RELEASE_APPROVER, "the scenario's directory or tools changed"))
    if "services" in changed:
        found.append(Need(ENGINEER, "the services changed"))
    if "models" in changed:
        widened = _widens_models(old["models"], new["models"])
        found.append(Need(RELEASE_APPROVER, "; ".join(widened)) if widened
                     else Need(ENGINEER, "the approved models changed, and none may do more"))
    for name in sorted(set(new["agents"]) | set(old["agents"])):
        before, after = old["agents"].get(name), new["agents"].get(name)
        if before == after:
            continue
        if after is None:
            found.append(Need(ENGINEER, f"the {name} is gone"))
        elif before is None:
            found += [Need(RELEASE_APPROVER, f"the {name} is new"),
                      Need(agent_owner(name), f"the {name} is new")]
        elif widened := _widens_agent(before["may"], after["may"]):
            found.append(Need(RELEASE_APPROVER, f"the {name} {', and '.join(widened)}"))
        else:
            found += [Need(agent_owner(name), f"the {name}'s instructions changed"),
                      Need(ENGINEER, f"the {name}'s instructions changed")]
    first: dict[str, Need] = {}
    for need in found:  # one of each is enough, with the first reason for it
        first.setdefault(need.role, need)
    return list(first.values())


# Whether its signatures meet what it needs

@dataclass(frozen=True)
class Verdict:
    ok: bool
    needs: tuple[Need, ...] = ()
    missing: tuple[str, ...] = ()
    signed_by: tuple[str, ...] = ()


def _line(scenario: Scenario, person: Person) -> list[str]:
    """Everyone above someone in their reporting line."""
    above, seen = [], {person.id}
    while person and person.manager and person.manager not in seen:
        seen.add(person.manager)
        above.append(person.manager)
        person = scenario.person(person.manager)
    return above


def judge(need: list[Need], raw: bytes, signatures: list[Signature], scenario: Scenario,
          team: str) -> Verdict:
    """Whether different people, each holding what's needed, signed exactly these bytes."""
    people, problems = {}, []
    for sig in signatures:
        person = scenario.person(sig.signer)
        if person is None:
            problems.append(f"{sig.signer} isn't in the directory")
        elif not person.public_key or not signing.verify(person.public_key, raw, sig.value,
                                                          signing.RELEASE):
            problems.append(f"{sig.signer}'s signature isn't for this release")
        else:
            people[person.id] = person
    inside = {p.id for p in scenario.team(team)} | {
        boss for member in scenario.team(team) for boss in _line(scenario, member)}

    def can(person: Person, role: str) -> bool:
        if role == RELEASE_APPROVER:
            return role in person.roles and person.id not in inside
        if role == ENGINEER:
            return person.team == team
        return role in person.roles

    def match(i: int, taken: dict[str, str]) -> bool:
        """Each need met by someone different, though one owner may own several agents."""
        if i == len(need):
            return True
        role = need[i].role
        for person in people.values():
            held = taken.get(person.id)
            shares = role.startswith("agent-owner:") and (held or "").startswith("agent-owner:")
            if can(person, role) and (held is None or shares) and match(i + 1, {**taken, person.id: role}):
                return True
        return False

    signed = tuple(sorted(people))
    if match(0, {}):
        return Verdict(True, tuple(need), (), signed)
    unmet = [n for n in need if not any(can(p, n.role) for p in people.values())]
    missing = [f"it needs {who(n.role)}, because {n.why}" for n in unmet] or [
        f"it needs {len(need)} different people: " + "; ".join(who(n.role) for n in need)]
    return Verdict(False, tuple(need), tuple(missing + problems), signed)


def check(conn: psycopg.Connection, digest: str, scenario: Scenario, team: str,
          _seen: frozenset[str] = frozenset()) -> Verdict:
    """Whether this deployment approved a release, checked again from what was signed,
    back to the first release it approved, or the last baseline. Editing the record
    approves nothing.

    Every signature is checked against the directory as it is now, so if someone who
    approved one of those releases leaves, or their key changes, the history no longer
    checks out. Approving the release in use again as a baseline, which needs everyone,
    starts it afresh.
    """
    row = conn.execute("select manifest, previous, signatures, advisory from releases "
                       "where digest = %s", (digest,)).fetchone()
    if row is None:
        return Verdict(False, missing=("nobody here has approved it yet",))
    raw = bytes(row["manifest"])
    if hashlib.sha256(raw).hexdigest() != digest:
        return Verdict(False, missing=("its record isn't what was signed",))
    old = None
    if row["previous"]:
        before = (Verdict(False, missing=("its history goes round in a circle",)) if
                  row["previous"] in _seen else
                  check(conn, row["previous"], scenario, team, _seen | {digest}))
        if not before.ok:
            return Verdict(False, missing=("the release before it isn't approved: "
                                           + "; ".join(before.missing),))
        old = yaml.safe_load(bytes(conn.execute("select manifest from releases where digest = %s",
                                                (row["previous"],)).fetchone()["manifest"]))
    signatures = [Signature(s["signer"], s["value"]) for s in row["signatures"] or []]
    return judge(needs(yaml.safe_load(raw), old, row["advisory"]), raw, signatures, scenario, team)


def record(conn: psycopg.Connection, raw: bytes, signatures: list[Signature], scenario: Scenario,
           team: str, advisory: str | None = None, *, baseline: bool = False) -> Verdict:
    """Record people's signatures over a release, as the database's administrator.

    It's weighed against the release approved here last, when it's first recorded,
    or, as a baseline, against nothing, so it needs everyone. Signatures add up, so
    approvers can sign at different times.
    """
    digest = hashlib.sha256(raw).hexdigest()
    data = yaml.safe_load(raw)
    row = conn.execute("select signatures from releases where digest = %s for update",
                       (digest,)).fetchone()
    if row is None:
        last = None if baseline else conn.execute(
            "select digest from releases where approved_at is not null "
            "order by approved_at desc limit 1").fetchone()
        conn.execute("insert into releases (digest, version, manifest, previous, advisory) "
                     "values (%s, %s, %s, %s, %s)",
                     (digest, data["version"], raw, last["digest"] if last else None, advisory))
    else:
        conn.execute("update releases set advisory = coalesce(%s, advisory), previous = case "
                     "when %s then null else previous end where digest = %s",
                     (advisory, baseline, digest))
    merged = {s["signer"]: s for s in (row["signatures"] if row else None) or []}
    merged.update({s.signer: {"signer": s.signer, "value": s.value} for s in signatures})
    conn.execute("update releases set signatures = %s where digest = %s",
                 (Jsonb(list(merged.values())), digest))
    verdict = check(conn, digest, scenario, team)
    if verdict.ok:
        conn.execute("update releases set approved_at = coalesce(approved_at, now()) "
                     "where digest = %s", (digest,))
    ledger.append(conn, {
        "kind": "admin", "action": "approve-release", "decision": "record" if verdict.ok else "deny",
        "reasons": list(verdict.missing),
        "args": {"version": data["version"], "release": digest, "signed_by": list(verdict.signed_by),
                 "needs": [n.role for n in verdict.needs], "advisory": advisory,
                 "baseline": baseline},
    })
    return verdict


def last_approved(conn: psycopg.Connection) -> dict | None:
    row = conn.execute("select manifest from releases where approved_at is not null "
                       "order by approved_at desc limit 1").fetchone()
    return yaml.safe_load(bytes(row["manifest"])) if row else None


@dataclass
class Releases:
    """The gateway's view: the release it is, and whether this deployment approved it."""

    current: Running | None
    approved: set[str] = field(default_factory=set)

    def problems(self, conn: psycopg.Connection, scenario: Scenario, team: str) -> list[str]:
        if self.current is None:
            return []
        if self.current.problems:
            return list(self.current.problems)
        if self.current.digest in self.approved:
            return []
        verdict = check(conn, self.current.digest, scenario, team)
        if verdict.ok:
            self.approved.add(self.current.digest)
            return []
        return [f"release {self.current.version} of a5s isn't approved here: "
                + "; ".join(verdict.missing)]
