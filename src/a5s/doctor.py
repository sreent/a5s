"""`a5s doctor`: whether a5s can work where it runs, and what to fix first.

It checks, in order, what a5s needs where it runs: its settings, the database and its schema,
the release and whether this deployment approved it, the settings in force, the core and its
token, how people sign in, each model's key, the ledger's copies, and the credentials noted to
expire. Each says what it found
and, where something's wrong, what fixes it, in the words a5s says it in elsewhere, such as the
refusal a part would start with. A check that needs another first, such as the schema the
database, says it wasn't checked, rather than failing again for the same reason.

Run it where the core runs, with its settings: `kubectl exec deploy/<release>-gateway -- a5s
doctor`, or `helm test <release>`, which runs it in a pod of its own with the core's settings
(deploy/helm/a5s/templates/tests.yaml). It reads, and changes nothing."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

import psycopg

from a5s import build, config, db, definitions
from a5s.client import Client, Refused
from a5s.config import Config, load_models
from a5s.core import anchor, environment, health, releases, status
from a5s.core.identity import IdentityConfig, IdentityError, Verifier

State = Literal["ok", "look", "fix", "skip"]
SHOWN: dict[State, str] = {"ok": "ok", "look": "look at", "fix": "fix", "skip": "not checked"}
# The runbook's sections the checks here read for themselves, so the core's status adds the rest
READ_HERE = (status.COPYING, "credentials-that-expire", "settings-or-the-release-dont-check-out",
             "sign-ins-refused-for-want-of-a-second-factor")


@dataclass(frozen=True)
class Found:
    """What one check found: fine, worth a look, to fix, or not checked, and what it found,
    with what fixes it where something's wrong."""

    check: str
    state: State
    said: str


def checked() -> list[Found]:
    """Every check, in the order to fix what they find: a later one may follow from an
    earlier, such as every check of the database from its being away. As the environment it
    runs in stands, as a part's would."""
    found: list[Found] = []
    problems, warnings = config.check(serving=True)
    found += [Found("Settings", "fix", p) for p in problems]
    found += [Found("Settings", "look", w) for w in warnings]
    try:
        cfg = Config.from_env()
    except config.ConfigError:  # said above, by the setting
        return [*found, *(Found(name, "skip", "Not checked, as a setting above can't be read.")
                          for name in ("The database", "The release", "The settings in force",
                                       "The core", "Signing in", "The models",
                                       "The ledger's copies", "The core's status",
                                       "Credentials", "This deployment"))]
    if not problems and not warnings:
        found.append(Found("Settings", "ok", "Every setting a5s reads here can be used: "
                                             "`a5s config --set` shows those set."))
    reached = _database(cfg)
    found += reached
    usable = all(f.state != "fix" for f in reached)
    scenario: Any = None
    try:
        scenario = build.scenario(cfg)
    except Exception as exc:  # noqa: BLE001 - a scenario that won't load says why, and stops what needs it
        found.append(Found("The scenario", "fix", f"The scenario {cfg.scenario} can't be loaded "
                                                  f"({type(exc).__name__}: {exc}): check "
                                                  "A5S_SCENARIO and A5S_SCENARIO_DIR."))
    core, told = _core(cfg)  # asked first, as it says whether it runs in development
    development = cfg.development or bool(((told or {}).get("configuration") or {})
                                          .get("development"))
    if not usable or scenario is None:
        found += [Found(name, "skip", "Not checked, as a5s can't read the database or the "
                                      "scenario here: see above.")
                  for name in ("The release", "The settings in force")]
    else:
        found += _release(cfg, scenario, development)
        found += _in_force(cfg, scenario, told)
    found += core
    found += _signing_in(development)
    found += _models(cfg, scenario) if scenario is not None else [
        Found("The models", "skip", "Not checked, as the scenario can't be loaded: see above.")]
    found += _copies(cfg, development) if usable else [
        Found("The ledger's copies", "skip", "Not checked, as a5s can't read the database "
                                             "here: see above.")]
    found += _needs(told)
    found += _credentials(date.today())
    found += _deployment(development, cfg)
    return found


def _deployment(development: bool, cfg: Config | None = None) -> list[Found]:
    """Which deployment this is, as the band across the top of every page says it: unnamed
    outside development, every page says to treat it as production, which is worth naming
    (core/environment.py)."""
    try:
        here = environment.here(development)
    except config.ConfigError:  # the settings' check names it
        return [Found("This deployment", "skip", "Not checked, as A5S_ENVIRONMENT can't be read: "
                                                 "see above.")]
    if cfg is not None and (why := environment.published_refused(cfg.scenario_dir, cfg.root)):
        return [Found("This deployment", "fix", _sentence(f"The core won't start: {why}"))]
    if not here["named"]:  # as the core's settings here have it, as the channels' should
        return [Found("This deployment", "look",
                      "Nobody has named this deployment, so the band across the top of every "
                      "page says to treat it as production: set A5S_ENVIRONMENT to production, "
                      "staging or test, and A5S_ENVIRONMENT_NAME to its name if you like, as the "
                      "chart's environment.kind and environment.name do.")]
    return [Found("This deployment", "ok", f"As the core's settings here have it, every page's "
                                           f"band says this is {here['name']}, a {here['kind']} "
                                           "deployment: the channels' settings name it too.")]


def _credentials(today: date) -> list[Found]:
    """The credentials A5S_EXPIRES notes: each expired, to fix, and each expiring within 30
    days, to look at, as the status says (docs/runbooks.md#credentials-that-expire)."""
    try:
        noted = config.EXPIRES.read() or {}
    except config.ConfigError:  # the settings' check names it, and how to write it
        return [Found("Credentials", "skip", "Not checked, as A5S_EXPIRES can't be read: see "
                                             "above.")]
    if not noted:
        return [Found("Credentials", "ok", "None is noted to expire in A5S_EXPIRES: note each "
                                           "that does, such as a client secret, and the status "
                                           "says so 30 days before it does.")]
    soon = status.expiring(noted, today)
    if not soon:
        name, on = min(noted.items(), key=lambda item: item[1])
        return [Found("Credentials", "ok", f"None of the {_count(len(noted), 'credential')} "
                                           f"A5S_EXPIRES notes expires within "
                                           f"{status.EXPIRY_SOON} days: the first, {name}, "
                                           f"on {on.isoformat()}.")]
    return [Found("Credentials", "fix" if c["days"] < 0 else "look",
                  status.expiry(c) + ".") for c in soon]  # named as noted, in its case


def told(found: list[Found], cfg: Config | None = None) -> str:
    """What `a5s doctor` prints: a line for each finding, and how many to fix and look at."""
    width = max(len(text) for text in SHOWN.values())
    lines = [f"{SHOWN[f.state]:<{width}}  {f.check}: {f.said}" for f in found]
    fix, look = (sum(f.state == state for f in found) for state in ("fix", "look"))
    if fix:
        also = f", and {look} to look at" if look else ""
        ending = (f"{fix} to fix{also}: fix them in order, as a later one may follow from an "
                  "earlier.")
    elif look:
        ending = f"Nothing to fix, and {look} to look at."
    else:
        ending = "Nothing to fix: a5s can work here."
    where = f"a5s doctor, for the core at {cfg.gateway_url}" if cfg else "a5s doctor"
    return "\n".join([where, "", *lines, "", ending])


def as_json(found: list[Found]) -> list[dict[str, str]]:
    return [asdict(f) for f in found]


def _count(n: int, what: str) -> str:
    return f"{n} {what}{'' if n == 1 else 's'}"


# Each check

def _database(cfg: Config) -> list[Found]:
    """Whether the database answers, as whom, and whether its schema is this release's."""
    try:
        db.known(cfg.database_url)
        with db.transaction(cfg.database_url) as conn:
            row = conn.execute("select current_user as who, coalesce((select rolsuper from "
                               "pg_roles where rolname = current_user), false) as superuser"
                               ).fetchone()
    except psycopg.OperationalError as exc:
        return [Found("The database", "fix", db.refusal(exc, cfg.database_url))]
    except psycopg.errors.UndefinedTable:
        where, _ = db.where(cfg.database_url)
        return [Found("The database", "fix", f"The database at {where} has none of a5s's "
                                             "tables: run `a5s migrate` there, as its "
                                             "administrator, or `a5s setup`, which migrates it "
                                             "and applies the settings.")]
    except (db.NewerSchema, db.OlderSchema) as exc:
        return [Found("The database", "fix", _sentence(str(exc)))]
    assert row is not None
    where, _ = db.where(cfg.database_url)
    if row["superuser"]:
        return [Found("The database", "look",
                      f"The database at {where} answers, and its schema is this release's, but "
                      f"a5s connects as {row['who']}, a superuser, whom none of a5s's grants "
                      "binds: each part connects as its own role, such as "
                      f"{db.ROLES['gateway']} for the core (docs/runbooks.md).")]
    return [Found("The database", "ok", f"The database at {where} answers, as {row['who']}, "
                                        "and its schema is this release's.")]


def _release(cfg: Config, scenario: Any, development: bool) -> list[Found]:
    """Whether the release a5s is here can run, and whether this deployment approved it."""
    current = releases.running(cfg.root, cfg.scenario_dir, cfg.agents_dir)
    named = f"Release {current.version} of a5s ({current.digest[:12]})"
    if current.problems:
        return [Found("The release", "fix", f"{named} can't run: {'; '.join(current.problems)}.")]
    with db.transaction(cfg.database_url) as conn:
        verdict = releases.check(conn, current.digest, scenario, cfg.team)
    if verdict.ok:
        return [Found("The release", "ok", f"{named} is approved here, signed by "
                                           f"{', '.join(verdict.signed_by) or 'its approvers'}.")]
    missing = "; ".join(verdict.missing) or "nobody here has signed it"
    said = (f"{named} isn't approved here ({missing}), so the core runs nothing: its approvers "
            "sign it with `a5s release sign`, and `a5s release approve` records their "
            "signatures; `a5s release status` says who must sign.")
    if development:  # which runs any release, as `a5s dev` does
        return [Found("The release", "look", said + " In development, a5s runs it anyway.")]
    return [Found("The release", "fix", said)]


def _in_force(cfg: Config, scenario: Any, told: dict | None = None) -> list[Found]:
    """Whether a version of the settings is in force, whether it counts, as the core checks it
    at every run, against the directory as it is now, and whether any agent is at work."""
    with db.transaction(cfg.database_url) as conn:
        version = conn.execute("select serial from settings_versions where scenario = %s "
                               "order by serial desc limit 1", (scenario.name,)).fetchone()
        counts = {r["status"]: r["n"] for r in conn.execute(
            "select status, count(*)::int as n from instances group by status")}
    if version is None:
        return [Found("The settings in force", "fix",
                      f"No version of {scenario.name}'s settings is in force here, so no agent "
                      "is at work: `a5s apply` applies the scenario's signed settings, or its "
                      "approvers approve a version where they work.")]
    if told is not None and (problem := (told.get("settings") or {}).get("problem")):
        return [Found("The settings in force", "fix",  # every run is refused (round 17, A1)
                      f"Version {version['serial']} of the settings is the latest, and the core "
                      f"refuses every run with it: {problem}. Its approvers approve it again, or "
                      "a version that counts, where they work "
                      "(docs/runbooks.md#settings-or-the-release-dont-check-out).")]
    active = counts.get("active", 0)
    others = ", ".join(f"{n} {status}" for status, n in sorted(counts.items())
                       if status not in ("active", "retired") and n)
    if not active:
        return [Found("The settings in force", "look",
                      f"Version {version['serial']} of the settings is in force, and no "
                      f"instance is active{f' ({others})' if others else ''}: `a5s agents` "
                      "lists them, and docs/runbooks.md#an-instance-isnt-active says why one "
                      "may not be.")]
    return [Found("The settings in force", "ok",
                  f"Version {version['serial']} of the settings is in force, with "
                  f"{_count(active, 'instance')} active"
                  f"{f' ({others})' if others else ''}.")]


def _core(cfg: Config) -> tuple[list[Found], dict | None]:
    """Whether the core answers where the other parts reach it, and takes their token; and its
    status, where it does."""
    token = cfg.operator_token or cfg.service_token
    if not token:
        return [Found("The core", "fix", "No token to call the core with: set "
                                         "A5S_SERVICE_TOKEN to the core's own, or "
                                         "A5S_OPERATOR_TOKEN where the deployment sets "
                                         "one.")], None
    try:
        with Client(cfg.gateway_url, token, timeout=10) as core:
            told = core.status()
    except Refused as exc:
        if not exc.status:
            return [Found("The core", "fix", f"{_sentence(str(exc.detail))} Is it running? "
                                             "`a5s dev` runs it for development; otherwise set "
                                             "A5S_GATEWAY_URL to where yours is.")], None
        which = "A5S_OPERATOR_TOKEN" if cfg.operator_token else "A5S_SERVICE_TOKEN"
        if exc.status == 401:
            return [Found("The core", "fix", f"The core at {cfg.gateway_url} refuses the token "
                                             f"in {which}: set it to the one the core was "
                                             "started with.")], None
        return [Found("The core", "fix", f"The core at {cfg.gateway_url} answered "
                                         f"{exc.status}: {exc.text or exc.detail}")], None
    return [Found("The core", "ok", f"The core answers at {cfg.gateway_url}, and takes the "
                                    "token given here.")], told


def _signing_in(development: bool) -> list[Found]:
    """Whether the identity provider answers as A5S_OIDC_ISSUER names it, and asks for a second
    factor where it should."""
    given = IdentityConfig.from_env()
    if given is None:
        if development:
            return [Found("Signing in", "look", "Nobody signs in: a5s takes people's word for "
                                                "who they are, as in development. A deployment "
                                                "sets A5S_OIDC_ISSUER (docs/first-day.md).")]
        return [Found("Signing in", "look",
                      "Nobody signs in to the studio or the web chat here, as A5S_OIDC_ISSUER "
                      "isn't set: people reach agents only through a chat that says who they "
                      "are, such as Teams or Matrix. Set it to the identity provider people "
                      "sign in with (docs/first-day.md).")]
    try:
        Verifier(given).endpoints()
    except IdentityError as exc:  # where, and what to check, as the operators read it
        return [Found("Signing in", "fix",
                      _sentence(f"a5s can't check sign-ins: {getattr(exc, 'detail', exc)}"))]
    found = [Found("Signing in", "ok", f"The identity provider at {given.issuer} answers, as "
                                       "A5S_OIDC_ISSUER names it, and publishes its keys.")]
    if given.mfa_said_none:  # as the deployment says its provider's tokens show (round 17, A10)
        found.append(Found("Signing in", "ok",
                           "A5S_OIDC_MFA is none, as the provider's tokens show no second factor: "
                           "a5s asks none of anyone, even to approve, decide or grade."))
    elif given.mfa is None:
        found.append(Found("Signing in", "look",
                           "A5S_OIDC_MFA isn't set, so a5s asks no second factor of anyone, "
                           "even to approve, decide or grade: set it to the claim and values "
                           "the provider shows one by, such as amr:mfa, or none where its "
                           "tokens show none (docs/first-day.md#2-peoples-sign-in)."))
    return found


def _models(cfg: Config, scenario: Any) -> list[Found]:
    """Whether each model the instances at work use, as the settings in force put them on
    them, or fall back to, has its key here, and whether any is stopped: the settings in force,
    which the database holds, not the image's file, as an approved version may put an instance
    on another model (round 17, A8)."""
    try:
        approved = load_models(cfg.models_file)
        found = definitions.load_all(cfg.agents_dir)
        with db.transaction(cfg.database_url) as conn:
            instances = conn.execute("select definition, model from instances where status <> "
                                     "'retired' order by id").fetchall()
    except psycopg.Error:  # the database's own check says why
        return [Found("The models", "skip", "Not checked, as a5s can't read the instances at "
                                            "work here: see above.")]
    except Exception as exc:  # noqa: BLE001 - its own refusal, such as a definition that doesn't check out
        return [Found("The models", "fix", _sentence(f"The agents or their models can't be read "
                                                     f"({type(exc).__name__}: {exc})"))]
    using: dict[str, set[str]] = {}  # each model, and the agents that use it
    for instance in instances:
        definition = found.get(instance["definition"])
        if definition is None:
            continue
        for model in [instance["model"] or definition.model, *definition.fallbacks]:
            using.setdefault(model, set()).add(instance["definition"])
    told: list[Found] = []
    unkeyed: dict[str, list[str]] = {}  # each key that isn't set, and the models that need it
    for model in sorted(using):
        given = approved.get(model)
        if given is None:
            told.append(Found("The models", "fix", f"{model}, which {_agents(using[model])}, "
                                                   "isn't one config/models.yaml approves: "
                                                   "approve it there, in a release, or move "
                                                   "them to one it does."))
        elif given.key_env and not os.environ.get(given.key_env):
            unkeyed.setdefault(given.key_env, []).append(model)
    for key, models in sorted(unkeyed.items()):
        calls = " and ".join(dict.fromkeys(f"{approved[m].provider}'s {approved[m].model}"
                                           for m in models))  # aliases of one model, once
        users = set().union(*(using[m] for m in models))
        told.append(Found("The models", "fix",
                          f"{key} isn't set, so a5s can't call {calls}, which {_agents(users)}: "
                          "set it to the provider's API key where the core runs, and the "
                          "sandbox, and start them again."))
    try:
        stopped = [r["model"] for r in health.report(cfg.database_url, scenario.name)
                   if r["gated_at"] and r["model"] in using]
    except psycopg.Error:
        stopped = []  # the database's own check says why
    told += [Found("The models", "look",
                   f"{model} is stopped, as it stalled on more than half its calls in a day: "
                   f"once its provider answers again, the release approver puts it back with "
                   f"`a5s health --restore {model}` (docs/runbooks.md).") for model in stopped]
    if not told:
        keys = sorted({k for m in using if (k := getattr(approved.get(m), "key_env", None))})
        held = f" ({', '.join(keys)})" if keys else ""
        told.append(Found("The models", "ok", "Each model the agents at work use has its key "
                                              f"here: {', '.join(sorted(using)) or 'none in use'}"
                                              f"{held}."))
    return told


def _copies(cfg: Config, development: bool) -> list[Found]:
    """How the copier is doing, as it records it in the database, and, where the store is
    named here, whether the ledger's locked copies can be read from here. The chart names the
    store for the copier and `a5s restore` alone, so the core's settings may not."""
    store = build.store(cfg)
    copying = "(docs/runbooks.md#the-ledgers-copies-stop)"
    try:
        with db.transaction(cfg.database_url) as conn:
            lacking = anchor.behind(conn, store) if store is not None else None
            state = anchor.state(conn)
    except Exception as exc:  # noqa: BLE001 - the store's own error, whatever its kind of storage
        return [Found("The ledger's copies", "fix",
                      f"a5s can't read the ledger's copies at {cfg.anchor_store} "
                      f"({type(exc).__name__}): check that the core reaches the store, and its "
                      f"credentials where the core runs {copying}.")]
    if lacking:
        return [Found("The ledger's copies", "fix", _sentence(anchor.RESTORED.format(
            first=lacking[0], last=lacking[1])))]
    if state is None and not (store is None and development):  # setting it up's to fix here
        return [Found("The ledger's copies", "fix",
                      "No copier has run here, so the ledger has no locked copies: run "
                      "`a5s anchor --every` with A5S_ANCHOR_STORE, as the chart's anchor part "
                      f"does {copying}.")]
    if state is None:  # in development, which copies nothing to locked storage
        return [Found("The ledger's copies", "look",
                      "The ledger isn't copied to locked storage, as no copier has run "
                      "here: a deployment sets A5S_ANCHOR_STORE, such as s3://bucket/a5s, "
                      f"and runs the copier, `a5s anchor --every` {copying}.")]
    if told := status.copies_needs(state, development):  # as the status judges them (A2)
        return [Found("The ledger's copies", "fix" if when == status.NOW else "look",
                      _sentence(f"{said} {copying}")) for when, said in told]
    age = state["copied_seconds_ago"]
    copied = "nothing to copy yet" if age is None else f"copied {age / 60:.0f} minutes ago"
    where = (f"its copies at {cfg.anchor_store} can be read from here" if store is not None
             else "it records that here, and copies to the store the copier's settings name")
    return [Found("The ledger's copies", "ok",
                  f"The copier is at work, {copied}, {state['behind']} entries behind: "
                  f"{where}.")]


def _needs(told: dict | None) -> list[Found]:
    """What the core's own status says needs someone, beyond what the checks above read for
    themselves: what pages out of hours, to fix, and what waits for working hours, to look at,
    so the doctor passes nothing the status and the alerts say is wrong (round 17, A2)."""
    if told is None:
        return [Found("The core's status", "skip", "Not checked, as the core didn't answer: see "
                                                   "above.")]
    rest = [n for n in told.get("needs") or [] if n["runbook"].rpartition("#")[2] not in READ_HERE]
    if not rest:
        return [Found("The core's status", "ok", "Nothing else the core's status reads needs "
                                                 "anyone: `a5s status` says how the last day went.")]
    return [Found("The core's status", "fix" if n["when"] == status.NOW else "look",
                  f"{_sentence(n['said'])} ({n['runbook']})") for n in rest]


def _agents(names: set[str]) -> str:
    """The agents that use a model, and the verb: "the assistant uses", "the assistant and the
    watcher use"."""
    listed = [f"the {name}" for name in sorted(names)]
    if len(listed) == 1:
        return f"{listed[0]} uses"
    return ", ".join(listed[:-1]) + " and " + listed[-1] + " use"


def _sentence(text: str) -> str:
    """A refusal a5s says elsewhere in lower case, as a sentence of its own."""
    text = text.strip()
    return (text[:1].upper() + text[1:]).rstrip(".") + "."
