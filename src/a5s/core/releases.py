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
- the scenario's directory or tools, its knowledge, such as who may read each
  note, the code of the scenarios a5s ships and their adapters, or anything that
  widens what an agent or a model may do: the release approver;
- an agent's instructions alone, a scenario's own agents' among them, or anything
  that narrows it: the agent's owner and a second engineer;
- the services alone, the client the team's jobs use among them: an engineer from
  the team;
- a fix for a security advisory that changes only the locked versions of what a5s
  depends on: an engineer, at once. Its approvers sign that it fixes the advisory.

Each release also records who may sign the one after it: everyone its directory
gives a key, with their team, their roles and the teams below them. A signature
over a release counts for a role only if it counts both as the release before it
was approved and as this release has it, checked with the key of record. So a
release can't approve itself with people it adds, nor count those it removes,
and nobody can add an approver by editing the database, since each record is
signed. A new agent's owner may be someone the release adds, since its release
approver signs for them. What people sign is an approval of the release (`Approval`):
its manifest, the image it runs as, the release it follows, the advisory it fixes,
and whether it's a baseline, so editing the record approves nothing. Only the first
release a deployment approves follows none, and it's judged by its own directory:
a deployment from git judges it by the approvers kept outside every release instead.

The core opens no run until the release it is has what it needs, except in
development.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from psycopg.types.json import Jsonb

import a5s
from a5s import db, definitions
from a5s.contract import AGENT_OWNER, ASSURANCE, RELEASE_APPROVER, Person, Scenario, Signature
from a5s.core import ledger, signing
from a5s.core.ledger import canonical

ENGINEER = "engineer"  # anyone in the team that runs a5s
PARTS = ("core", "services", "build", "models", "scenario")
BUILT_FROM = ("pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore",
              "studio/package.json", "studio/package-lock.json", "studio/.npmrc")
_HEADER = ("# A release of a5s: every file it runs, by part, what each agent and model may do, and\n"
           "# who may sign the next. An organisation approves it for its deployment by signing\n"
           "# exactly these bytes.\n")
_PEOPLE = {RELEASE_APPROVER: "the release approver, from outside the team that runs a5s",
           ASSURANCE: "assurance, after their tests", ENGINEER: "an engineer from the team that runs a5s"}


def agent_owner(agent: str) -> str:
    return f"{AGENT_OWNER}:{agent}"


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


# Code in the package that isn't the trusted core: the scenarios a5s ships and their
# adapters, which count as the scenario's part, and what the team runs beside the core
SCENARIO_CODE = ("a5s/sample.py", "a5s/service_desk.py", "a5s/software_delivery.py",
                 "a5s/master_data.py", "a5s/knowledge.py", "a5s/graphify.py")
SERVICE_CODE = ("a5s/worker.py", "a5s/client.py")


def _code(root: Path) -> tuple[dict, dict, dict]:
    """a5s's own code, from the source in a checkout or the installed package in an image:
    the trusted core, the services, and the scenarios' code."""
    source = root / "src" / "a5s"
    files = _files(source if source.is_dir() else Path(a5s.__file__).parent, "a5s")
    services = {k: v for k, v in files.items()
                if k.startswith("a5s/services/") or k in SERVICE_CODE}
    scenarios = {k: v for k, v in files.items() if k in SCENARIO_CODE}
    core = {k: v for k, v in files.items() if k not in services and k not in scenarios}
    return core, services, scenarios


def agent_part(folder: Path) -> dict:
    """An agent's part of a release: its files, by their hashes, and what it may do, as a
    release manifest holds it."""
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
            "judge": d.evaluation.judge if d.evaluation else None,  # whom its samples go to
            "tasks": d.tasks.model_dump() if d.tasks else None,  # long work, over days
            "owner": d.owner, "deputy": d.deputy,  # who answers for it where the settings name none
            "listed": d.listed,  # whether everyone signed in may know of it
            # what other systems may start its runs with: only where it takes any, so a
            # release made before events keeps its manifest
            **({"events": [e.model_dump() for e in d.events]} if d.events else {}),
        },
    }


def _signers(scenario_dir: Path) -> dict:
    """Who may sign the next release, as this one records them: everyone the scenario's
    directory gives a key, with their team, their roles, and the teams of everyone below
    them in their reporting lines, which keep them from approving that team's releases."""
    path = scenario_dir / "data.yaml"
    people = ((yaml.safe_load(path.read_text()) or {}).get("people") or []) if path.exists() else []
    teams = {p["id"]: p.get("team") for p in people}
    managers = {p["id"]: p.get("manager") for p in people}
    above: dict[str, set[str]] = {}
    for person, team in teams.items():
        seen, boss = {person}, managers[person]
        while boss and boss not in seen:
            seen.add(boss)
            if team:
                above.setdefault(boss, set()).add(team)
            boss = managers.get(boss)
    found = {}
    for p in people:
        key = scenario_dir / "keys" / f"{p['id']}.pub"
        if key.exists():
            found[p["id"]] = {"key": key.read_text().strip(), "team": p.get("team"),
                              "roles": sorted(p.get("roles") or []),
                              "above": sorted(above.get(p["id"], ()))}
    return found


def _models(config: Path) -> dict:
    path = config / "models.yaml"
    listed = (yaml.safe_load(path.read_text()) or {}).get("models") or {} if path.exists() else {}
    keep = ("provider", "api", "base_url", "model", "reported_model", "region", "data_classes")
    return {alias: {k: m.get(k) for k in keep} for alias, m in sorted(listed.items())}


def manifest(root: Path, scenario_dir: Path, *, built: dict | None = None,
             agents_dir: Path | None = None) -> bytes:
    """The release a5s is here. With `built`, the manifest its image was built with, what
    the image was built from comes from there, since the image doesn't carry it."""
    core, services, scenarios = _code(root)
    agents = agents_dir or root / "agents"
    try:  # a scenario's own agents count as agents, not as its folder's files
        theirs = agents.resolve().relative_to(scenario_dir.resolve()).parts
    except ValueError:
        theirs = None

    def kept_apart(inside: Path) -> bool:
        """What a release leaves out of the scenario's part: its private keys, its settings,
        which are signed on their own, its own agents, and the documents at its top."""
        return (inside.suffix == ".key" or inside.name in ("settings.yaml", "settings.sig")
                or (inside.suffix == ".md" and len(inside.parts) == 1)
                or (theirs is not None and inside.parts[:len(theirs)] == theirs))

    data = {
        "version": built["version"] if built else importlib.metadata.version("a5s"),
        "parts": {
            "core": core,
            "services": services,
            "build": built["parts"]["build"] if built else {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in BUILT_FROM if (root / name).exists()},
            "models": _files(root / "config", "config"),
            # Its knowledge and data, and the code of the scenarios a5s ships, such as who
            # may read each note: a change needs the release approver
            "scenario": {**_files(scenario_dir, "scenario", kept_apart),
                         **{f"code/{k}": v for k, v in scenarios.items()}},
        },
        "models": _models(root / "config"),
        "agents": {f.name: agent_part(f) for f in sorted(agents.iterdir())
                   if (f / "agent.yaml").exists()} if agents.is_dir() else {},
        "signers": _signers(scenario_dir),
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


def running(root: Path, scenario_dir: Path, agents_dir: Path | None = None) -> Running:
    built_path = root / "release.yaml"  # written when the image was built
    built = yaml.safe_load(built_path.read_bytes()) if built_path.exists() else None
    raw = manifest(root, scenario_dir, built=built, agents_dir=agents_dir)
    if built is None:
        return Running(raw)
    now = yaml.safe_load(raw)["parts"]
    changed = sorted(path for part in ("core", "services")
                     for path in set(now[part]) | set(built["parts"][part])
                     if now[part].get(path) != built["parts"][part].get(path))
    if changed:
        return Running(raw, (f"its code isn't what its image was built with: {', '.join(changed[:3])}",))
    return Running(raw)


# What people's signatures approve

APPROVES = b"a5s release approval\n"


@dataclass(frozen=True)
class Approval:
    """What a signature over a release approves, as `a5s release sign` signs it: the release,
    by its manifest's digest; the image it runs as, by digest, where one's named; the release
    it follows in its deployment, or none for the first; the security advisory it's approved as
    fixing, if any; and whether it's a baseline. Each is signed, so none can be changed after,
    nor added: a pull request that swaps the image, or an administrator who edits the record,
    approves nothing."""

    release: str
    image: str | None = None
    follows: str | None = None
    advisory: str | None = None
    baseline: bool = False

    @classmethod
    def of(cls, raw: bytes, **parts: Any) -> Approval:
        return cls(hashlib.sha256(raw).hexdigest(), **parts)

    def signed(self) -> bytes:
        """Exactly the bytes a signature over it is made over."""
        return APPROVES + canonical({"release": self.release, "image": self.image,
                                     "follows": self.follows, "advisory": self.advisory,
                                     "baseline": self.baseline}).encode()

    def shown(self) -> dict:
        """As release.sig holds it, beside the signatures."""
        return {"release": self.release, "image": self.image, "follows": self.follows,
                "advisory": self.advisory, "baseline": self.baseline}


def sign(private: str, approval: Approval) -> str:
    """Someone's signature over an approval of a release, with their private key."""
    return signing.sign(private, approval.signed(), signing.RELEASE)


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
    if new.get("judge") and new.get("judge") != old.get("judge"):  # its samples go to it
        found.append("has its work judged by another model")
    if "tasks" in old and (tasks := new.get("tasks")):  # what a release before recorded of it
        was = old["tasks"]
        if was is None:
            found.append("takes on long tasks")
        elif tasks["budget_tokens"] > was["budget_tokens"] or tasks["days"] > was["days"]:
            found.append("may spend more, or longer, on its tasks")
    found += [f"has another {key}" for key in ("owner", "deputy")
              if key in old and new.get(key) != old[key]]
    if "listed" in old and new.get("listed") and not old["listed"]:
        found.append("is listed for everyone signed in")
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


# What a security fix that goes in at once may change: the locked versions of a5s's dependencies,
# and nothing else it's built from, such as the Dockerfile, which could add any code at all
LOCKS = ("uv.lock", "studio/package-lock.json")


def needs(new: dict, old: dict | None, advisory: str | None = None) -> list[Need]:
    """Whose approval a release needs, given the release approved before it, if any."""
    old = old or {"parts": {}, "models": {}, "agents": {}}
    changed = [part for part in PARTS if new["parts"].get(part) != old["parts"].get(part)]
    built, was = new["parts"].get("build") or {}, old["parts"].get("build") or {}
    locks_alone = all(f in LOCKS for f in set(built) | set(was) if built.get(f) != was.get(f))
    if advisory and changed == ["build"] and locks_alone and new["agents"] == old["agents"]:
        return [Need(ENGINEER, f"it fixes {advisory}, and changes only the locked versions of "
                               "what a5s depends on")]
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
        if before is not None and after is not None:  # by what the release before recorded of it
            after = {**after, "may": {k: v for k, v in after["may"].items() if k in before["may"]}}
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


def _inside(scenario: Scenario, team: str) -> set[str]:
    """The team that runs a5s, and everyone above them in their reporting lines."""
    return {p.id for p in scenario.team(team)} | {
        boss for member in scenario.team(team) for boss in _line(scenario, member)}


@dataclass(frozen=True)
class Signer:
    """Someone the directory gives a key, as a release records them."""

    id: str
    key: str
    team: str | None
    roles: tuple[str, ...] = ()
    above: tuple[str, ...] = ()  # the teams of everyone below them in their reporting lines

    def can(self, role: str, team: str) -> bool:
        """Whether their signature meets what a release needs of a role: the release
        approver's only from outside the team that runs a5s and everyone above it."""
        if role == RELEASE_APPROVER:
            return role in self.roles and self.team != team and team not in self.above
        if role == ENGINEER:
            return self.team == team
        return role in self.roles


def _recorded(manifest: object) -> dict[str, Signer] | None:
    """The signers a release's manifest records, or None if it records none, as those from
    before releases recorded them don't."""
    found = manifest.get("signers") if isinstance(manifest, dict) else None
    if found is None:
        return None
    return {i: Signer(i, s["key"], s.get("team"), tuple(s.get("roles") or ()),
                      tuple(s.get("above") or ())) for i, s in found.items()}


def _directory(scenario: Scenario, team: str, ids: list[str]) -> dict[str, Signer]:
    """Some people as the directory now has them, for a release that records no signers."""
    inside, found = _inside(scenario, team), {}
    for i in ids:
        person = scenario.person(i)
        if person is not None and person.public_key:
            found[i] = Signer(i, person.public_key, person.team, person.roles,
                              (team,) if i in inside and person.team != team else ())
    return found


@dataclass(frozen=True)
class _Judging:
    """Whose signatures over a release count, for what, and with which key."""

    own: dict[str, Signer]  # as this release records them
    record: dict[str, Signer] | None  # as the release before it recorded them, if it did
    team: str
    named: frozenset[str]  # its new agents' owners, whom this release names
    # Roles anyone this release gives them may sign for, whatever the record says: an
    # engineer's, for a first release judged by those kept outside it, and, for a baseline,
    # each role nobody of record who remains could hold
    loose: frozenset[str] = frozenset()

    @classmethod
    def of(cls, raw: bytes, previous: dict | None, scenario: Scenario, team: str,
           ids: list[str], roots: dict[str, Signer] | None = None) -> _Judging:
        new = yaml.safe_load(raw)
        new = new if isinstance(new, dict) else {}
        own = _recorded(new)
        if own is None:  # from before releases recorded their signers
            own = _directory(scenario, team, ids)
        record = _recorded(previous) if previous else None
        agents = set(new.get("agents") or ()) - set((previous or {}).get("agents") or ())
        named = frozenset(agent_owner(a) for a in agents)
        if record is None and roots is not None:  # a first release, by those kept outside it
            return cls(own, roots, team, named, frozenset({ENGINEER}))
        return cls(own, record, team, named)

    def orphans(self, need: list[Need]) -> _Judging:
        """For a baseline: each role it needs that nobody of record, whom it still has, could
        hold, such as when the only release approver left before handing over, may be signed
        for by someone it brings in, as long as assurance of record remains to sign it too."""
        if self.record is None:
            return self
        stay = [i for i in self.record if i in self.own]
        orphaned = {n.role for n in need
                    if not any(self.record[i].can(n.role, self.team)
                               and self.own[i].can(n.role, self.team) for i in stay)}
        if ASSURANCE in orphaned:  # nobody of record is left to vouch for whom it brings in
            return self
        return replace(self, loose=self.loose | frozenset(orphaned))

    def key(self, signer: str) -> str | None:
        """Theirs as the release before recorded it, if it did: a key a release brings in
        counts from the release after it."""
        mine = self.own.get(signer)
        if mine is None:
            return None
        theirs = self.record.get(signer) if self.record is not None else None
        return (theirs or mine).key

    def new(self, signer: str) -> bool:
        """Whether this release adds them to the directory."""
        return self.record is not None and signer in self.own and signer not in self.record

    def can(self, signer: str, role: str) -> bool:
        mine = self.own.get(signer)
        if mine is None or not mine.can(role, self.team):
            return False
        if self.record is None or role in self.named or role in self.loose:
            return True
        theirs = self.record.get(signer)
        return theirs is not None and theirs.can(role, self.team)


def awaiting(conn: db.Connection, running: Running | None, scenario: Scenario, team: str,
             person: Person) -> list[Need]:
    """What the release a5s is waits for from someone, if this deployment hasn't approved it:
    each of its needs they could meet, unless they've signed it already."""
    if running is None or running.problems:
        return []
    row = conn.execute("select previous, signatures, advisory, baseline, approved_at "
                       "from releases where digest = %s", (running.digest,)).fetchone()
    if row and row["approved_at"]:
        return []
    if row and any(s["signer"] == person.id for s in row["signatures"] or []):
        return []
    old, advisory, baseline = last_approved(conn), None, False
    if row:
        before = row["previous"] and conn.execute(
            "select manifest from releases where digest = %s", (row["previous"],)).fetchone()
        old, advisory = (yaml.safe_load(bytes(before["manifest"])) if before else None), row["advisory"]
        baseline = bool(row["baseline"])
    judging = _Judging.of(running.raw, old, scenario, team, [person.id])
    need = needs(yaml.safe_load(running.raw), None if baseline else old, advisory)
    if baseline:
        judging = judging.orphans(need)
    return [n for n in need if judging.can(person.id, n.role)]


def _line(scenario: Scenario, person: Person) -> list[str]:
    """Everyone above someone in their reporting line."""
    above, seen = [], {person.id}
    while person and person.manager and person.manager not in seen:
        seen.add(person.manager)
        above.append(person.manager)
        person = scenario.person(person.manager)
    return above


def judge(need: list[Need], raw: bytes, signatures: list[Signature], scenario: Scenario,
          team: str, previous: dict | None = None, approval: Approval | None = None, *,
          roots: dict[str, Signer] | None = None) -> Verdict:
    """Whether different people, each holding what's needed, signed exactly this approval of
    these bytes, as the release before it, if any, records who may sign it, or, for a first
    release, as those kept outside it do (`roots`), and as it records them itself."""
    approval = approval or Approval.of(raw)
    judging = _Judging.of(raw, previous, scenario, team, [s.signer for s in signatures], roots)
    if approval.baseline:
        judging = judging.orphans(need)
    people: list[str] = []
    problems = []
    if approval.release != hashlib.sha256(raw).hexdigest():
        problems.append("its approval is of another release")
    for sig in signatures:
        key = judging.key(sig.signer)
        if key is None:
            problems.append(f"{sig.signer} isn't in the directory")
        elif problems[:1] == ["its approval is of another release"] or not signing.verify(
                key, approval.signed(), sig.value, signing.RELEASE):
            problems.append(f"{sig.signer}'s signature isn't for this release")
        elif sig.signer not in people:
            people.append(sig.signer)
            if judging.new(sig.signer):
                problems.append(f"{sig.signer} is new to the directory with this release, so "
                                "signs it only as a new agent's owner")

    def can(person: str, role: str) -> bool:
        return judging.can(person, role)

    def match(i: int, taken: dict[str, str]) -> bool:
        """Each need met by someone different, though one owner may own several agents."""
        if i == len(need):
            return True
        role = need[i].role
        for person in people:
            held = taken.get(person)
            shares = role.startswith("agent-owner:") and (held or "").startswith("agent-owner:")
            if can(person, role) and (held is None or shares) and match(i + 1, {**taken, person: role}):
                return True
        return False

    signed = tuple(sorted(people))
    if match(0, {}):
        return Verdict(True, tuple(need), (), signed)
    unmet = [n for n in need if not any(can(p, n.role) for p in people)]
    missing = [f"it needs {who(n.role)}, because {n.why}" for n in unmet] or [
        f"it needs {len(need)} different people: " + "; ".join(who(n.role) for n in need)]
    return Verdict(False, tuple(need), tuple(missing + problems), signed)


def signatures_in(raw: bytes, text: str) -> list[Signature]:
    """The signatures a release.sig holds over exactly this release, as `a5s release sign`
    writes them; ValueError if they're over another one."""
    signed = yaml.safe_load(text) or {}
    if signed.get("release") != hashlib.sha256(raw).hexdigest():
        raise ValueError("its signatures are over another release")
    return [Signature(s["signer"], s["value"]) for s in signed.get("signatures") or []]


def approval_in(raw: bytes, text: str) -> Approval:
    """What a release.sig's signatures approve of exactly this release; ValueError if it's
    another release's."""
    signed = yaml.safe_load(text) or {}
    if signed.get("release") != hashlib.sha256(raw).hexdigest():
        raise ValueError("its signatures are over another release")
    return Approval(signed["release"], signed.get("image"), signed.get("follows"),
                    signed.get("advisory"), bool(signed.get("baseline")))


def roots_in(text: str) -> dict[str, Signer]:
    """The people kept outside every release who judge an environment's first one, as its
    approvers.yaml names them, as a manifest records its signers (deploy/gitops)."""
    found = _recorded(yaml.safe_load(text) or {})
    if not found:
        raise ValueError("it names nobody")
    return found


def verify(raw: bytes, signatures: list[Signature], scenario: Scenario, team: str,
           previous: bytes | None = None, approval: Approval | None = None,
           roots: dict[str, Signer] | None = None, ran: Approval | None = None) -> Verdict:
    """Whether a release's signatures meet what it needs, weighed against the release before
    it, as a deployment's core weighs them when its approval job records them, but with no
    database: for the pull request that deploys it (deploy/gitops), before it's merged. Its
    approval must follow exactly that release, and a first one is judged by those kept outside
    it, its `roots`, where they're given. The release the environment runs, `previous`, as it
    was approved there, `ran`, needs nothing more; approved again as something else, such as
    another image of it, it needs the release approver and assurance, as the release it is
    records them. The core still checks them again, against what it approved before."""
    approval = approval or Approval.of(raw)
    old = yaml.safe_load(previous) if previous else None
    if previous is not None and previous == raw:  # the release the environment runs
        if ran is not None and approval == ran:
            return Verdict(True)
        if ran is not None and approval.follows != ran.follows:
            return Verdict(False, missing=(
                (f"its approval follows {_short(approval.follows)}, and the release it is "
                 f"followed {_short(ran.follows)} where it was approved"),))
        why = "it's approved again, as something else, such as to run as another image"
        need = [Need(RELEASE_APPROVER, why), Need(ASSURANCE, why)]
        return judge(need, raw, signatures, scenario, team, old, approval)
    follows = hashlib.sha256(previous).hexdigest() if previous else None
    if approval.follows != follows:
        return Verdict(False, missing=(
            (f"its approval follows {_short(approval.follows)}, and the environment runs "
             f"{_short(follows)}: promote it again, and have it signed again"),))
    need = needs(yaml.safe_load(raw), None if approval.baseline else old, approval.advisory)
    return judge(need, raw, signatures, scenario, team, old, approval, roots=roots)


def _short(digest: str | None) -> str:
    return f"release {digest[:12]}" if digest else "no release"


def _approved_others(conn: db.Connection, digest: str) -> bool:
    """Whether the ledger records this deployment approving another release before it first
    approved this one, or at all, if it hasn't yet: its history, which nobody rewrites without
    breaking the ledger's chain and its locked copies."""
    return conn.execute(
        "with approved as (select seq, (entry::jsonb) -> 'args' ->> 'release' as release "
        "from ledger where kind = 'admin' and action = 'approve-release' and decision = 'record') "
        "select 1 from approved where release <> %(d)s and seq < coalesce("
        "(select min(seq) from approved where release = %(d)s), 9223372036854775807) limit 1",
        {"d": digest}).fetchone() is not None


def check(conn: db.Connection, digest: str, scenario: Scenario, team: str,
          _seen: frozenset[str] = frozenset()) -> Verdict:
    """Whether this deployment approved a release, checked again from what was signed, back to
    the first release it approved. Editing the record approves nothing: what each release
    follows, the image it runs as, the advisory it fixes and whether it's a baseline are signed
    with it.

    Each release is judged by who the release before it records may sign it, and by who it
    records itself, so the history holds when people leave: their leaving is a release of
    its own, which those who stay approve. One recorded before releases recorded their
    signers is judged by the directory as it is now. A baseline needs everyone, as if weighed
    against nothing, and is judged by the release before it all the same, except that a role
    nobody of record who remains could hold may be signed for by someone it brings in, while
    assurance of record signs it too: such as when the only release approver left before
    handing over. Only the first release a deployment approves follows none.
    """
    row = conn.execute("select manifest, previous, signatures, advisory, image, baseline "
                       "from releases where digest = %s", (digest,)).fetchone()
    if row is None:
        return Verdict(False, missing=("nobody here has approved it yet",))
    raw = bytes(row["manifest"])
    if hashlib.sha256(raw).hexdigest() != digest:
        return Verdict(False, missing=("its record isn't what was signed",))
    approval = Approval(digest, row["image"], row["previous"], row["advisory"],
                        bool(row["baseline"]))
    old = None
    if row["previous"]:
        before = (Verdict(False, missing=("its history goes round in a circle",)) if
                  row["previous"] in _seen else
                  check(conn, row["previous"], scenario, team, _seen | {digest}))
        if not before.ok:
            return Verdict(False, missing=("the release before it isn't approved: "
                                           + "; ".join(before.missing),))
        found = conn.execute("select manifest from releases where digest = %s",
                             (row["previous"],)).fetchone()
        earlier = bytes(found["manifest"]) if found else b""
        if hashlib.sha256(earlier).hexdigest() != row["previous"]:  # whose signers judge this one
            return Verdict(False, missing=("the release before it isn't what was signed",))
        old = yaml.safe_load(earlier)
    elif _approved_others(conn, digest):
        return Verdict(False, missing=(
            ("it follows no release, as only a deployment's first may, and this deployment "
             "has approved others: its approvers sign it as following the last"),))
    signatures = [Signature(s["signer"], s["value"]) for s in row["signatures"] or []]
    need = needs(yaml.safe_load(raw), None if approval.baseline else old, approval.advisory)
    return judge(need, raw, signatures, scenario, team, old, approval)


def record(conn: db.Connection, raw: bytes, signatures: list[Signature], scenario: Scenario,
           team: str, approval: Approval | None = None) -> Verdict:
    """Record people's signatures over a release, as the database's administrator, with what
    they approve of it: the release it follows, its image, the advisory it fixes and whether
    it's a baseline, which are theirs, signed, and never the administrator's to set: a record
    that says otherwise has no signature over what it says. Signatures add up, so approvers can
    sign at different times, while what they approve stays the same; approving it as something
    else starts its signatures afresh."""
    approval = approval or Approval.of(raw)
    digest = hashlib.sha256(raw).hexdigest()
    data = yaml.safe_load(raw)
    row = conn.execute("select signatures, previous, image, advisory, baseline from releases "
                       "where digest = %s for update", (digest,)).fetchone()
    if row is not None and (row["previous"], row["image"], row["advisory"], row["baseline"]) != (
            approval.follows, approval.image, approval.advisory, approval.baseline):
        # Approved now as something else, such as a baseline: the signatures it held were over
        # what it was approved as before, so they're let go, and it's approved afresh
        conn.execute("update releases set previous = %s, image = %s, advisory = %s, "
                     "baseline = %s, signatures = '[]', approved_at = null where digest = %s",
                     (approval.follows, approval.image, approval.advisory, approval.baseline,
                      digest))
        row = None
    elif row is None:
        conn.execute("insert into releases (digest, version, manifest, previous, advisory, "
                     "image, baseline) values (%s, %s, %s, %s, %s, %s, %s)",
                     (digest, data["version"], raw, approval.follows, approval.advisory,
                      approval.image, approval.baseline))
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
                 "needs": [n.role for n in verdict.needs], "follows": approval.follows,
                 "image": approval.image, "advisory": approval.advisory,
                 "baseline": approval.baseline},
    })
    return verdict


def following(conn: db.Connection) -> str | None:
    """The release the next one a deployment approves follows: the last it approved."""
    row = conn.execute("select digest from releases where approved_at is not null "
                       "order by approved_at desc limit 1").fetchone()
    return row["digest"] if row else None


def last_approved(conn: db.Connection) -> dict | None:
    row = conn.execute("select manifest from releases where approved_at is not null "
                       "order by approved_at desc limit 1").fetchone()
    return yaml.safe_load(bytes(row["manifest"])) if row else None


@dataclass
class Releases:
    """The gateway's view: the release it is, and whether this deployment approved it."""

    current: Running | None
    approved: set[str] = field(default_factory=set)

    def problems(self, conn: db.Connection, scenario: Scenario, team: str) -> list[str]:
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
