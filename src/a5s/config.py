"""Every setting a deployment gives a5s, in one place, and where it finds its models.

Each setting is an environment variable, and `VARS` lists every one a5s reads: what it sets,
what it takes, and its default, which is written here alone (docs/configuration.md is made
from this list, and compose and the chart set only what differs: tests/test_configuration.py).
A part reads a setting as the code needs it, never as a module is imported, so a value it
can't use never breaks an import; and every part checks them all as it starts (`check`), so
such a value stops it there, saying which variable and what it takes, rather than failing
later. An A5S_ variable a5s doesn't know stops a part too, as a misspelt setting would
otherwise do nothing, such as a second factor nobody is asked for. `shown` says what a part
runs with, and which values are defaults, its secrets masked: for `a5s config`, the line each
part logs as it starts, and the core's status.

Only what differs between deployments is set here. What someone else decides, such as how
long a5s keeps what's said, is in the signed settings, which they approve; what only a
release changes is in the code (docs/starting-values.md).
"""

from __future__ import annotations

import difflib
import ipaddress
import itertools
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, NamedTuple
from urllib.parse import urlsplit

import yaml

DEFAULT_DATABASE_URL = "postgresql://a5s@127.0.0.1:54329/postgres"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8700"
DEFAULT_CHANNELS_URL = "http://127.0.0.1:8703"


class ConfigError(ValueError):
    """A setting a part can't use, by its variable, and what it takes."""


# How each kind of value is read from its variable's text: each raises ValueError, saying
# what's wrong, for a message that names the variable.

Parse = Callable[[str], Any]


def _text(given: str) -> str:
    return given.strip()


def _whole(least: int, most: int) -> Parse:
    def parse(given: str) -> int:
        try:
            n = int(given.strip())
        except ValueError:
            raise ValueError from None
        if not least <= n <= most:
            raise ValueError
        return n
    return parse


def _seconds(least: float, most: float) -> Parse:
    def parse(given: str) -> float:
        try:
            n = float(given.strip())
        except ValueError:
            raise ValueError from None
        if not least <= n <= most:
            raise ValueError
        return n
    return parse


def _flag(given: str) -> bool:
    if (said := given.strip().lower()) in ("1", "true", "yes", "on"):
        return True
    if said in ("0", "false", "no", "off"):
        return False
    raise ValueError


def _url(*schemes: str, exact: bool = False) -> Parse:
    """An address, without a slash at its end, or `exact`ly as given."""
    def parse(given: str) -> str:
        found = urlsplit(given.strip())
        if found.scheme not in schemes or not found.netloc:
            raise ValueError
        return given.strip() if exact else given.strip().rstrip("/")
    return parse


def _path(given: str) -> Path:
    return Path(given.strip())


LEAST_SECRET = 32  # characters in a seal key or the service token, as `a5s up` makes 43 (round 15)


def _items(given: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i.strip() for i in given.split(",") if i.strip()))


def _names(given: str) -> frozenset[str]:
    return frozenset(_items(given))


def _pairs(of: Parse, example: str) -> Parse:
    """agent=value, agent=value: each agent's own, such as its pool's address."""
    def parse(given: str) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for item in _items(given):
            agent, sep, value = item.partition("=")
            if not sep or not agent.strip() or not value.strip():
                raise ValueError(f"{item!r} isn't an agent and its value, such as {example}")
            found[agent.strip()] = of(value)
        return found
    return parse


def _json_list(given: str) -> list[dict[str, Any]]:
    try:
        found = json.loads(given)
    except json.JSONDecodeError:
        raise ValueError("not JSON") from None
    if not isinstance(found, list) or not all(isinstance(i, dict) for i in found):
        raise ValueError("not a JSON list of objects")
    return found


def _matching(pattern: str) -> Parse:
    def parse(given: str) -> str:
        if not re.fullmatch(pattern, given.strip()):
            raise ValueError
        return given.strip()
    return parse


def second_factor(given: str) -> tuple[str, tuple[str, ...]]:
    """The claim a sign-in shows a second factor by, and the values that do, from
    `claim:value,value`, such as amr:mfa, or acr:gold for a provider's step-up level."""
    claim, _, values = given.partition(":")
    accepted = tuple(v.strip() for v in values.split(",") if v.strip())
    if not claim.strip() or not accepted:
        raise ValueError
    return claim.strip(), accepted


@dataclass(frozen=True)
class Var:
    """One setting: its environment variable, what it sets, what it takes, and its default,
    the value it has when the variable isn't set, or is set empty, as compose may pass it."""

    name: str
    means: str
    default: Any = None
    parse: Parse = _text
    takes: str = "text"
    secret: bool = False
    area: str = ""
    # What it is set empty, if not its default: so an empty value can turn off what the
    # default turns on, as for the claim sign-ins show groups in
    empty: Any = None
    empty_is_default: bool = True
    # Where, under A5S_ROOT, `a5s up` keeps its value for development, if it isn't set
    file: str | None = None

    def read(self, env: Mapping[str, str] | None = None) -> Any:
        """Its value, as the environment gives it now: ConfigError if it can't be used."""
        env = os.environ if env is None else env
        given = env.get(self.name)
        if given is not None and not given.strip() and not self.empty_is_default:
            return self.empty
        if given is None or not given.strip():
            if self.file and (kept := _root(env) / self.file).exists():
                given = kept.read_text()
            else:
                return self.default
        try:
            return self.parse(given)
        except ValueError as e:
            why = f" ({e})" if str(e) else ""
            shown = ("set to something it can't use" if self.secret
                     else repr(masked(given.strip())[:80]))
            raise ConfigError(f"{self.name} is {shown}{why}: it takes {self.takes}") from None

    def source(self, env: Mapping[str, str] | None = None) -> str:
        """Whether the environment sets it, `a5s up`'s file does, or it's a5s's default."""
        env = os.environ if env is None else env
        if (given := env.get(self.name)) is not None and (given.strip() or not self.empty_is_default):
            return "set"
        if self.file and (_root(env) / self.file).exists():
            return "file"
        return "default"

    def is_set(self, env: Mapping[str, str] | None = None) -> bool:
        return self.source(env) != "default"


def _root(env: Mapping[str, str]) -> Path:
    return ROOT.read(env) or Path.cwd()


@dataclass(frozen=True)
class Family:
    """Settings named for each of something, such as each part's database password."""

    pattern: str  # such as A5S_DB_<PART>_PASSWORD
    means: str
    secret: bool = True
    area: str = ""

    def matches(self, name: str) -> bool:
        head, _, tail = self.pattern.partition("<")
        tail = tail.partition(">")[2]
        return (name.startswith(head) and name.endswith(tail)
                and len(name) > len(head) + len(tail))


DATABASE = "The database"
CORE = "The core and its parts"
WORKERS = "Workers"
SIGN_IN = "Signing in"
TEAMS = "Teams"
SLACK = "Slack"
EVENTS = "Events from other systems"
DELEGATION_AREA = "Acting as the person"
MATRIX = "Matrix"
LEDGER = "The ledger's locked copies"
STUDIO = "The studio, its sandbox and publishing"
SCENARIO = "The scenario"
INVENTORY = "IT's inventory in Microsoft 365"
MAIL = "Mailboxes in Microsoft 365"
COMMAND = "The command line"

_DB = ("postgresql", "postgres")
_WEB = ("http", "https")

ROOT = Var("A5S_ROOT", "the folder a5s's own files are in: its agents, config and scenarios",
           None, _path, "a folder", area=CORE)
DATABASE_URL = Var("A5S_DATABASE_URL", "the part's database, as its own role",
                   DEFAULT_DATABASE_URL, _url(*_DB), "a postgresql:// address", area=DATABASE)
DB_POOL_SIZE = Var("A5S_DB_POOL_SIZE", "connections each part keeps open to its database",
                   10, _whole(1, 200), "a whole number from 1 to 200", area=DATABASE)
DB_CONNECT_TIMEOUT = Var("A5S_DB_CONNECT_TIMEOUT", "seconds a part waits to connect to its "
                         "database before failing", 2, _whole(1, 60),
                         "a whole number of seconds from 1 to 60", area=DATABASE)
SERVICE_TOKEN = Var("A5S_SERVICE_TOKEN", "the token a5s's parts call the core with", "",
                    secret=True, area=CORE, takes="a token", file=".a5s/service-token")
OPERATOR_TOKEN = Var("A5S_OPERATOR_TOKEN", "the token operators' commands call the core with, "
                     "such as a5s status: where it's set, the core takes it alone for theirs, and "
                     "the service token alone for the scheduler's work (round 15)", "",
                     secret=True, area=CORE, takes="a token")
SEAL_KEYS = Var("A5S_SEAL_KEYS", "the core's own keys, sealing what people approve, decide and "
                "grade: the first seals, the others are ones it's moving from, until `a5s "
                "seal-again` retires them (docs/runbooks.md#rotating-the-seal-key)", (), _items,
                "keys, by commas", secret=True, area=CORE, file=".a5s/seal-key")
GATEWAY_URL = Var("A5S_GATEWAY_URL", "where the other parts reach the core",
                  DEFAULT_GATEWAY_URL, _url(*_WEB), "an http(s):// address", area=CORE)
CHANNELS_URL = Var("A5S_CHANNELS_URL", "where people's messages reach the core's channels",
                   DEFAULT_CHANNELS_URL, _url(*_WEB), "an http(s):// address", area=CORE)
PUBLIC_URL = Var("A5S_PUBLIC_URL", "where people reach the channels, for links, if not "
                 "A5S_CHANNELS_URL", None, _url(*_WEB), "an http(s):// address", area=CORE)
TEAM = Var("A5S_TEAM", "the directory's team that runs a5s: its approvals of a release count "
           "as an engineer's, never as the release approver's", "platform", area=CORE)
DEVELOPMENT = Var("A5S_DEVELOPMENT", "without an identity provider, take people's word for "
                  "who they are: for development alone", False, _flag, "true or false",
                  area=SIGN_IN)
RUN_MINUTES = Var("A5S_RUN_MINUTES", "the longest a run may last, in minutes: its token dies "
                  "with it", 60, _whole(5, 240), "a whole number of minutes from 5 to 240",
                  area=CORE)
PROVIDER_TIMEOUT = Var("A5S_PROVIDER_TIMEOUT", "seconds the core waits for a model provider's "
                       "answer", 180.0, _seconds(5, 900), "seconds, from 5 to 900", area=CORE)

WORKER_URL = Var("A5S_WORKER_URL", "the shared worker pool, for every agent without a pool of "
                 "its own", None, _url(*_WEB), "an http(s):// address", area=WORKERS)
WORKER_URLS = Var("A5S_WORKER_URLS", "each agent's own worker pool, by its name", {},
                  _pairs(_url(*_WEB), "assistant=http://a5s-worker-assistant:8702"),
                  "agent=address pairs, by commas", area=WORKERS)
POOL_SLOTS = 4  # how many of its agent's runs a pool takes at once, unless it says
WORKER_SLOTS = Var("A5S_WORKER_SLOTS", "how many of an agent's runs the scheduler works on at "
                   f"once in its own pool: {POOL_SLOTS} unless it says", {},
                   _pairs(_whole(1, 1000), "assistant=4"), "agent=number pairs, by commas",
                   area=WORKERS)
WORKER_AGENTS = Var("A5S_WORKER_AGENTS", "in a worker: the agents its pool runs, if it's their "
                    "own", frozenset(), _names, "agents, by commas", area=WORKERS)
WORKER_POOLED = Var("A5S_WORKER_POOLED", "in the shared pool: the agents with pools of their "
                    "own, which it refuses", frozenset(), _names, "agents, by commas",
                    area=WORKERS)
WORKER_TIMEOUT = Var("A5S_WORKER_TIMEOUT", "seconds a worker waits for the core, and for a "
                     "model through it", 240.0, _seconds(10, 3600), "seconds, from 10 to 3,600",
                     area=WORKERS)
WORKER_WAIT = Var("A5S_WORKER_WAIT", "seconds the scheduler waits for a worker to finish a run",
                  600.0, _seconds(10, 7200), "seconds, from 10 to 7,200", area=WORKERS)

OIDC_ISSUER = Var("A5S_OIDC_ISSUER", "the identity provider people sign in with, exactly as its "
                  "tokens name it, as Entra ID's v1 ends in a slash", None,
                  _url(*_WEB, exact=True), "an http(s):// address", area=SIGN_IN)
OIDC_AUDIENCE = Var("A5S_OIDC_AUDIENCE", "the audiences a5s takes tokens for", ("a5s",),
                    _items, "names, by commas", area=SIGN_IN)
OIDC_PERSON_CLAIM = Var("A5S_OIDC_PERSON_CLAIM", "the claim that says who someone is, as the "
                        "directory knows them", "preferred_username", area=SIGN_IN)
OIDC_METADATA_URL = Var("A5S_OIDC_METADATA_URL", "where the provider's metadata is, if not "
                        "where the issuer says", None, _url(*_WEB), "an http(s):// address",
                        area=SIGN_IN)
OIDC_DIRECTORY_PREFIX = Var("A5S_OIDC_DIRECTORY_PREFIX", "what to take off the person claim to "
                            "find someone in the directory", None, area=SIGN_IN)
OIDC_MFA = Var("A5S_OIDC_MFA", "the second factor what counts needs a sign-in to show, as the "
               "claim and the values that show it: a level (`acr`) or an authentication context "
               "(`acrs`) the pages ask the provider for", None, second_factor,
               "claim:value,value, such as amr:mfa, acr:gold or acrs:c1", area=SIGN_IN)
OIDC_GROUPS_CLAIM = Var("A5S_OIDC_GROUPS_CLAIM", "the claim sign-ins show groups in, for the "
                        "roles the settings give them; set empty for none", "groups",
                        area=SIGN_IN, empty=None, empty_is_default=False)
WEBCHAT_CLIENT_ID = Var("A5S_WEBCHAT_CLIENT_ID", "the web chat's client at the identity "
                        "provider, a public one", None, area=SIGN_IN)

TEAMS_BOTS = Var("A5S_TEAMS_BOTS", "a bot for each agent, which turns Teams on: a JSON list of "
                 "{agent, app_id, secret_env}, each bot's registration in Entra ID and the "
                 "variable its secret is in", None, _json_list, "a JSON list", area=TEAMS)
TEAMS_TENANT_ID = Var("A5S_TEAMS_TENANT_ID", "the organisation's tenant: messages from any other "
                      "are refused", None, area=TEAMS)
TEAMS_SERVICE_HOSTS = Var("A5S_TEAMS_SERVICE_HOSTS", "the hosts a5s sends Teams replies to, and "
                          "no other", ("smba.trafficmanager.net",), _items, "hosts, by commas",
                          area=TEAMS)

EVENT_SOURCES = Var("A5S_EVENT_SOURCES", "the systems that may tell a5s something happened, "
                    "which turns events on: a JSON list of {source, secret_env}, each source's "
                    "signing secret in the variable it names", None, _json_list, "a JSON list",
                    area=EVENTS)

DELEGATION = Var("A5S_DELEGATION", "the systems people may connect their own accounts in, so "
                 "agents act there as them, with their permissions: a JSON list of {name, title, "
                 "authorize, token, client_id, scopes, whoami, whose, known_as}, each system's "
                 "OAuth endpoints, a5s's client there, and where a5s asks whose account a token "
                 "is and how the directory knows it", None, _json_list, "a JSON list",
                 area=DELEGATION_AREA)

SLACK_BOTS = Var("A5S_SLACK_BOTS", "an app for each agent, which turns Slack on: a JSON list of "
                 "{agent, app_id, secret_env, token_env}, its signing secret and bot token each in "
                 "the variable it names", None, _json_list, "a JSON list", area=SLACK)
SLACK_TEAM = Var("A5S_SLACK_TEAM", "the organisation's workspace, by its team id: events from any "
                 "other are refused", None, area=SLACK)
SLACK_API = Var("A5S_SLACK_API", "where a5s calls Slack's Web API", "https://slack.com/api",
                _url("https", "http"), "an http(s):// address", area=SLACK)

MATRIX_HOMESERVER = Var("A5S_MATRIX_HOMESERVER", "the organisation's Matrix homeserver, which "
                        "turns Matrix on", None, _url(*_WEB), "an http(s):// address",
                        area=MATRIX)
MATRIX_SERVER_NAME = Var("A5S_MATRIX_SERVER_NAME", "its people's domain, as in @ana:<it>", None,
                         area=MATRIX)
MATRIX_AS_TOKEN = Var("A5S_MATRIX_AS_TOKEN", "a5s's token there, to speak as its bots", None,
                      secret=True, area=MATRIX, takes="a token")
MATRIX_HS_TOKEN = Var("A5S_MATRIX_HS_TOKEN", "the homeserver's, which comes with every delivery",
                      None, secret=True, area=MATRIX, takes="a token")

ANCHOR_STORE = Var("A5S_ANCHOR_STORE", "where the ledger's locked copies go", None,
                   _matching(r"(s3|azure|gs|file)://\S+"),  # as core/stores.py keeps them
                   "s3://, azure://, gs:// or file://, such as s3://bucket/a5s", area=LEDGER)
ANCHOR_RETAIN_DAYS = Var("A5S_ANCHOR_RETAIN_DAYS", "days each copy stays locked: longer here, "
                         "and shorter only by a release, which assurance signs", 365,
                         _whole(365, 36500), "a whole number of days from 365 to 36,500",
                         area=LEDGER)

SANDBOX_URL = Var("A5S_SANDBOX_URL", "the sandbox, where the studio tries the agents people are "
                  "making", None, _url(*_WEB), "an http(s):// address", area=STUDIO)
SANDBOX_TOKEN = Var("A5S_SANDBOX_TOKEN", "the token the studio and the sandbox share", "",
                    secret=True, area=STUDIO, takes="a token")
SANDBOX_DATABASE_URL = Var("A5S_SANDBOX_DATABASE_URL", "in the sandbox: its own database, as its "
                           "administrator", None, _url(*_DB), "a postgresql:// address",
                           area=STUDIO)
SANDBOX_DIR = Var("A5S_SANDBOX_DIR", "in the sandbox: the folder it keeps people's tries in",
                  None, _path, "a folder", area=STUDIO)
GITHUB_CLIENT_ID = Var("A5S_GITHUB_CLIENT_ID", "a5s's GitHub App, by its client id, a public "
                       "thing, for publishing drafts as pull requests", None, area=STUDIO)
GITHUB_REPO = Var("A5S_GITHUB_REPO", "the agents' repository, as owner/name", None,
                  _matching(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"), "owner/name",
                  area=STUDIO)
GITHUB_BASE = Var("A5S_GITHUB_BASE", "the branch pull requests go to", "main", area=STUDIO)
GITHUB_URL = Var("A5S_GITHUB_URL", "GitHub, or a GitHub Enterprise server", "https://github.com",
                 _url(*_WEB), "an http(s):// address", area=STUDIO)
GITHUB_API_URL = Var("A5S_GITHUB_API_URL", "its API, such as https://<it>/api/v3",
                     "https://api.github.com", _url(*_WEB), "an http(s):// address", area=STUDIO)

SCENARIO_CLASS = Var("A5S_SCENARIO", "the scenario a5s serves, as module:Class",
                     "a5s.sample:SampleScenario",
                     _matching(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*"), "module:Class",
                     area=SCENARIO)
SCENARIO_DIR = Var("A5S_SCENARIO_DIR", "the scenario's folder, if not scenarios/sample", None,
                   _path, "a folder", area=SCENARIO)
AGENTS_DIR = Var("A5S_AGENTS_DIR", "the agents' folders, if not agents", None, _path, "a folder",
                 area=SCENARIO)
LIBRARY_ROOT = Var("A5S_LIBRARY_ROOT", "where the deployment keeps the checkout of each docs "
                   "repository the scenario's libraries.yaml names, in a folder by its name, "
                   "current, such as with git-sync", Path("/var/lib/a5s/libraries"), _path,
                   "a folder", area=SCENARIO)

TOKEN = Var("A5S_TOKEN", "the token the identity provider gave the person using the command "
            "line, where a5s uses one", None, secret=True, area=COMMAND, takes="a token")

# IT's one inventory: each instance mirrored into Agent 365's agent registry, from the core alone
# (core/registration.py)
REGISTRY_TENANT = Var("A5S_REGISTRY_TENANT", "the Microsoft tenant whose agent registry lists "
                      "a5s's instances, by its id: none, and a5s registers nothing", None,
                      area=INVENTORY)
REGISTRY_CLIENT_ID = Var("A5S_REGISTRY_CLIENT_ID", "the app the core signs in to the tenant as, "
                         "granted AgentRegistration.ReadWrite.All: the deployment's agent "
                         "identity blueprint, where it gives instances identities", None,
                         area=INVENTORY)
REGISTRY_SECRET = Var("A5S_REGISTRY_SECRET", "that app's client secret", None, secret=True,
                      area=INVENTORY, takes="its secret")
REGISTRY_IDENTITIES = Var("A5S_REGISTRY_IDENTITIES", "whether each instance gets an Entra agent "
                          "identity of its own too, under that blueprint, its owner and deputy "
                          "its sponsors", False, _flag, "true or false", area=INVENTORY)
REGISTRY_GRAPH = Var("A5S_REGISTRY_GRAPH", "Microsoft Graph, as the tenant's cloud has it",
                     "https://graph.microsoft.com", _url("https"), "an https:// address",
                     area=INVENTORY)
REGISTRY_LOGIN = Var("A5S_REGISTRY_LOGIN", "where the core signs in to the tenant",
                     "https://login.microsoftonline.com", _url("https"), "an https:// address",
                     area=INVENTORY)


def _graph(given: str) -> str:
    """Microsoft 365's address: https://, or http:// on this machine alone, as a stand-in is."""
    found = urlsplit(given.strip())
    if not found.netloc or not (found.scheme == "https" or (
            found.scheme == "http" and found.hostname in ("127.0.0.1", "localhost", "::1"))):
        raise ValueError
    return given.strip().rstrip("/")


# The shared mailboxes a team's work arrives in, which the core alone reads, with the
# deployment's own app (connectors/mailboxes.py)
MAIL_TENANT = Var("A5S_MAIL_TENANT", "the Microsoft tenant the scenario's mailboxes are in, by its "
                  "id, where its mailboxes.yaml names any", None, area=MAIL)
MAIL_CLIENT_ID = Var("A5S_MAIL_CLIENT_ID", "the app the core reads them as, granted Mail.Read and "
                     "Mail.ReadWrite for its drafts, which Exchange's application access policy "
                     "keeps to those mailboxes", None, area=MAIL)
MAIL_CLIENT_SECRET = Var("A5S_MAIL_CLIENT_SECRET", "that app's client secret: for the core alone",
                         None, secret=True, area=MAIL, takes="its secret")
MAIL_GRAPH = Var("A5S_MAIL_GRAPH", "Microsoft Graph, as the tenant's cloud has it",
                 "https://graph.microsoft.com/v1.0", _graph, "an https:// address", area=MAIL)
MAIL_LOGIN = Var("A5S_MAIL_LOGIN", "where the core signs in to the tenant as the app",
                 "https://login.microsoftonline.com", _graph, "an https:// address", area=MAIL)

AREAS = (CORE, DATABASE, WORKERS, SIGN_IN, TEAMS, SLACK, MATRIX, EVENTS, DELEGATION_AREA, LEDGER,
         STUDIO, SCENARIO, INVENTORY, MAIL, COMMAND)
# Every setting above, by its area
VARS: tuple[Var, ...] = tuple(sorted((v for v in globals().values() if isinstance(v, Var)),
                                     key=lambda v: AREAS.index(v.area)))
FAMILIES = (
    Family("A5S_DB_<PART>_PASSWORD", "each part's database password, which setup gives its role",
           area=DATABASE),
    Family("A5S_TEAMS_SECRET_<AGENT>", "a bot's secret, where A5S_TEAMS_BOTS names it",
           area=TEAMS),
    Family("A5S_EVENT_SECRET_<SOURCE>", "a system's signing secret for its events, where "
           "A5S_EVENT_SOURCES names it", area=EVENTS),
    Family("A5S_DELEGATION_<NAME>_SECRET", "a5s's client secret in a system people connect, "
           "where A5S_DELEGATION names it: for the core alone", area=DELEGATION_AREA),
    Family("A5S_SLACK_SECRET_<AGENT>", "an app's signing secret, where A5S_SLACK_BOTS names it",
           area=SLACK),
    Family("A5S_SLACK_TOKEN_<AGENT>", "an app's bot token, where A5S_SLACK_BOTS names it",
           area=SLACK),
    Family("A5S_MCP_<SERVER>_TOKEN", "an MCP server's bearer token, where the scenario's "
           "mcp.yaml names it as the server's token_env", area=SCENARIO),
)
# Settings that moved, and where to: a part refuses one, rather than seem to obey it
MOVED = {name: f"the signed settings' data_protection.{choice}, which the data protection "
                "officer approves (docs/data-protection.md)"
         for name, choice in (("A5S_STUDIO_NAMES", "studio_names"),
                              ("A5S_AUDIT_NAMES", "audit_names"),
                              ("A5S_FLAG_RUBBER_STAMPS", "flag_rubber_stamps"))} | {
    name: "A5S_TEAMS_BOTS, a bot for each agent, with its secret in a variable of its own"
    for name in ("A5S_TEAMS_APP_ID", "A5S_TEAMS_APP_SECRET", "A5S_TEAMS_AGENT")}
# A5S_ names a5s itself never reads: its tests' (all A5S_TEST_ ones too), such as the classes
# of the deployment's data the agents' suites hold a case kept from a real run to, those compose and
# the deployment scripts read, such as whose attestation the GitOps check asks GitHub for, and
# the folder the made-up systems of the scenarios a5s ships keep their changes in for their code
NOT_SETTINGS = frozenset({
    "A5S_AGENT", "A5S_ASKER", "A5S_ATTESTED_BY", "A5S_CHANNELS_PORT", "A5S_DATA_CLASSES",
    "A5S_DB_PASSWORD", "A5S_DOC_IMAGES", "A5S_EVAL_MODEL",
    "A5S_EXPECTED", "A5S_GUIDE", "A5S_IDP_PASSWORD", "A5S_IDP_PORT", "A5S_IMAGE", "A5S_MATRIX_CONFIG",
    "A5S_MATRIX_PORT", "A5S_PASSWORD", "A5S_POOL_ASSISTANT", "A5S_POOL_WATCHER", "A5S_QUESTION",
    "A5S_REGRESSION", "A5S_SANDBOX_DB_PASSWORD", "A5S_SCREENSHOTS", "A5S_SMOKE_ENV",
    "A5S_SMOKE_WORK", "A5S_SOAK_FOUND", "A5S_SYSTEMS_STATE"})
# What some settings need beside them
NEEDS: tuple[tuple[Var, tuple[Var, ...], str], ...] = (
    (TEAMS_BOTS, (TEAMS_TENANT_ID,), "Teams"),
    (SLACK_BOTS, (SLACK_TEAM,), "Slack"),
    (MATRIX_HOMESERVER, (MATRIX_SERVER_NAME, MATRIX_AS_TOKEN, MATRIX_HS_TOKEN), "Matrix"),
    (GITHUB_CLIENT_ID, (GITHUB_REPO,), "publishing on GitHub"),
    (SANDBOX_URL, (SANDBOX_TOKEN,), "the sandbox"),
    (REGISTRY_TENANT, (REGISTRY_CLIENT_ID, REGISTRY_SECRET), "IT's inventory in Microsoft 365"),
)
BY_NAME = {v.name: v for v in VARS}
# The waits that nest, each in seconds, shortest first: a model's answer comes within the
# worker's call for it, which ends within the scheduler's wait for the run, which ends while
# the run's token lives, so each says why it stopped before the one outside it gives up
NESTED: tuple[tuple[Var, int], ...] = ((PROVIDER_TIMEOUT, 1), (WORKER_TIMEOUT, 1), (WORKER_WAIT, 1),
                                       (RUN_MINUTES, 60))


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def db_passwords(parts: list[str], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Each part's database password, by A5S_DB_<PART>_PASSWORD, for the parts that set one."""
    env = os.environ if env is None else env
    return {part: given for part in parts
            if (given := (env.get(f"A5S_DB_{part.upper()}_PASSWORD") or "").strip())}


def known(name: str) -> bool:
    return (name in BY_NAME or name in NOT_SETTINGS or name.startswith("A5S_TEST_")
            or any(f.matches(name) for f in FAMILIES))


# What Kubernetes gives a pod for each service in its namespace, unless its spec turns them off
# (enableServiceLinks: false, as the chart does): for a service named a5s-gateway, such as
# A5S_GATEWAY_SERVICE_HOST=10.43.0.12, A5S_GATEWAY_SERVICE_PORT_HTTP=8700 and
# A5S_GATEWAY_PORT_8700_TCP=tcp://10.43.0.12:8700. Each name's shape, by what its value is
_SERVICE: Final = r"^A5S_(?:[A-Z0-9_]+?_)?"  # a5s-gateway's, or a service named a5s
_PORT_OF: Final = r"PORT_[0-9]+_(?:TCP|UDP|SCTP)"
SERVICE_LINKS: Final = {
    "address": re.compile(rf"{_SERVICE}(?:SERVICE_HOST|{_PORT_OF}_ADDR)$"),
    "port": re.compile(rf"{_SERVICE}(?:SERVICE_PORT(?:_[A-Z0-9_]+)?|{_PORT_OF}_PORT)$"),
    "protocol": re.compile(rf"{_SERVICE}{_PORT_OF}_PROTO$"),
    "url": re.compile(rf"{_SERVICE}(?:PORT|{_PORT_OF})$"),
}


def _address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _service_value(value: str) -> str | None:
    """Which of a service's variables a value could be: an address, a port, a protocol, or
    an address with its port, such as tcp://10.43.0.12:8700 or tcp://[fd00::12]:8700."""
    if value in ("tcp", "udp", "sctp"):
        return "protocol"
    if value.isascii() and value.isdigit():
        return "port" if 0 < int(value) < 65536 else None
    if _address(value):
        return "address"
    url = urlsplit(value)
    try:
        port = url.port
    except ValueError:
        return None
    if url.scheme in ("tcp", "udp", "sctp") and port and not url.path and _address(
            url.hostname or ""):
        return "url"
    return None


def service_link(name: str, value: str) -> bool:
    """Whether a variable is one Kubernetes made for a service, by its name and its value, so
    a part leaves it alone. No setting has a name of that shape (tests/test_configuration.py)."""
    kind = _service_value(value)
    return kind is not None and SERVICE_LINKS[kind].match(name) is not None


def check(env: Mapping[str, str] | None = None, serving: bool = True) -> tuple[list[str], list[str]]:
    """What a part can't start with, and what it should be told of, as the environment
    stands: every setting it can't use, each one moved elsewhere, each one missing beside
    another that needs it, and each A5S_ name that isn't a setting, which stops a part that
    serves (`serving`), and is only warned of otherwise, as at the command line."""
    env = os.environ if env is None else env
    problems: list[str] = []
    for var in VARS:
        try:
            var.read(env)
        except ConfigError as e:
            problems.append(str(e))
    for name, where in MOVED.items():
        if name in env:
            problems.append(f"{name} has moved to {where}: unset it here")
    def read(var: Var, otherwise: Any) -> Any:  # each on its own: a bad one is said above
        try:
            return var.read(env)
        except ConfigError:
            return otherwise

    development, issuer = read(DEVELOPMENT, False), read(OIDC_ISSUER, None)  # round 15 (D12,
    keys, token = read(SEAL_KEYS, ()), read(SERVICE_TOKEN, "")  # D16)
    operating = read(OPERATOR_TOKEN, "")  # and D3
    if development and issuer:
        problems.append("A5S_DEVELOPMENT takes people's word for who they are, and turns checks "
                        "off that an identity provider's deployment needs: with A5S_OIDC_ISSUER "
                        "set, unset A5S_DEVELOPMENT")
    if short := [k for k in keys if len(k) < LEAST_SECRET]:
        problems.append(f"A5S_SEAL_KEYS has a key of {len(short[0])} characters: each takes at "
                        f"least {LEAST_SECRET}, made at random, as `a5s up` makes them")
    if serving and token and len(token) < LEAST_SECRET:  # as each part that serves holds it
        problems.append(f"A5S_SERVICE_TOKEN has {len(token)} characters: it takes at least "
                        f"{LEAST_SECRET}, made at random, as `a5s up` makes it")
    if serving and operating and len(operating) < LEAST_SECRET:
        problems.append(f"A5S_OPERATOR_TOKEN has {len(operating)} characters: it takes at least "
                        f"{LEAST_SECRET}, made at random")
    if operating and operating == token:
        problems.append("A5S_OPERATOR_TOKEN is the service token: make it apart, at random, or "
                        "operators hold the scheduler's")
    for given, needed, what in NEEDS:
        if given.is_set(env) and (missing := [n.name for n in needed if not n.is_set(env)]):
            problems.append(f"{what} needs {_and(missing)} as well as {given.name}")
    try:
        waits = [(var, var.read(env) * per) for var, per in NESTED]
    except ConfigError:  # said above
        waits = []
    for (inner, shorter), (outer, longer) in itertools.pairwise(waits):
        if shorter >= longer:
            problems.append(f"{inner.name} must be shorter than {outer.name}, so it stops, and "
                            f"says why, before the wait around it gives up: they're {shorter:g} "
                            f"and {longer:g} seconds")
    try:
        bots = TEAMS_BOTS.read(env) or []
    except ConfigError:
        bots = []
    for bot in bots:
        if not (env.get(str(bot.get("secret_env"))) or "").strip():
            problems.append(f"A5S_TEAMS_BOTS gives the {bot.get('agent')} agent's bot its secret "
                            f"in {bot.get('secret_env')}, which isn't set")
    try:
        apps = SLACK_BOTS.read(env) or []
    except ConfigError:
        apps = []
    for app in apps:
        for key, what in (("secret_env", "signing secret"), ("token_env", "bot token")):
            if not (env.get(str(app.get(key))) or "").strip():
                problems.append(f"A5S_SLACK_BOTS gives the {app.get('agent')} agent's app its "
                                f"{what} in {app.get(key)}, which isn't set")
    try:
        sources = EVENT_SOURCES.read(env) or []
    except ConfigError:
        sources = []
    for source in sources:
        from a5s.core import events  # its own rules for a system's name and secret
        if why := events.unfit(source):
            problems.append(why)
        elif not (env.get(str(source.get("secret_env"))) or "").strip():
            problems.append(f"A5S_EVENT_SOURCES gives {source.get('source')} its signing secret "
                            f"in {source.get('secret_env')}, which isn't set")
    try:
        systems = DELEGATION.read(env) or []
    except ConfigError:
        systems = []
    for system in systems:
        name = str(system.get("name") if isinstance(system, Mapping) else system)
        if not isinstance(system, Mapping) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name):
            problems.append(f"A5S_DELEGATION names a system {name[:40]!r}: each is named in "
                            "lowercase, such as servicenow")
            continue
        for key in ("authorize", "token", "client_id", "whoami", "whose"):
            if not str(system.get(key) or "").strip():
                problems.append(f"A5S_DELEGATION gives {name} no {key}")
    strangers = []
    for name in sorted(n for n in env if n.startswith("A5S_") and not known(n) and n not in MOVED
                       and not service_link(n, env[n])):
        like = difflib.get_close_matches(name, BY_NAME, n=1, cutoff=0.8)
        strangers.append(f"{name} isn't one of a5s's settings"
                         + (f": did you mean {like[0]}?" if like else ""))
    return (problems + strangers, []) if serving else (problems, strangers)


_PASSWORD = re.compile(r"(?i)((?:^|[?&\s])(?:ssl)?password=)[^&\s]*")


def masked(text: str) -> str:
    """A setting's text as people may read it: an address's password masked however it's
    written, in the address before its host, escaped or not, or as a password= parameter, as
    libpq takes it, whether the address is one a5s can use or not."""
    scheme, colon, rest = text.partition("://")
    if colon and "@" in rest:
        userinfo, _, host = rest.rpartition("@")  # its last @: a password may hold others
        if ":" in userinfo:
            text = f"{scheme}://{userinfo.split(':', 1)[0]}:•••@{host}"
    return _PASSWORD.sub(r"\1•••", text)


def _one(item: Any) -> str:
    """An item of a list as a setting shows it: an object, such as a Teams bot, by the agent
    it's for, and never what else it holds."""
    if isinstance(item, Mapping):
        return str(item.get("agent") or item.get("source") or item.get("name") or "an entry")
    return str(item)


def shown(var: Var, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """What a setting is, as the environment stands, for people to read: its value, secrets
    masked and an address's password with them, and whether it's a default."""
    env = os.environ if env is None else env
    try:
        value = var.read(env)
    except ConfigError:  # shown as given, password masked, and `check` says why
        return ("•••" if var.secret else masked((env.get(var.name) or "").strip())[:80],
                "set, unusable")
    source = var.source(env)
    if var.secret:
        return ("•••" if value else "not set"), source
    if value is None:
        return ("set empty" if source == "set" else "not set"), source
    if isinstance(value, dict):
        value = ",".join(f"{k}={v}" for k, v in value.items())
    elif isinstance(value, (tuple, list, frozenset, set)):
        items = sorted(value, key=str) if isinstance(value, (frozenset, set)) else list(value)
        value = ",".join(_one(i) for i in items)
    elif isinstance(value, float):
        value = f"{value:g}"
    return masked(str(value)) or "empty", source


def set_here(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The settings the environment sets, as `shown` shows them: what differs from a5s's
    defaults, for the line a part logs as it starts, and the core's status."""
    return {v.name: shown(v, env)[0] for v in VARS if v.is_set(env)}


def described(env: Mapping[str, str] | None = None, only_set: bool = False) -> str:
    """Every setting, by its area, as the environment stands: for `a5s config`."""
    lines, area = [], None
    for var in VARS:
        value, source = shown(var, env)
        if only_set and source == "default":
            continue
        if var.area != area:
            area = var.area
            lines += ["", area]
        lines.append(f"  {var.name} = {value}  "
                     f"({'a5s default' if source == 'default' else source})")
        lines.append(f"      {var.means}")
    count = sum(1 for v in VARS if v.is_set(env))
    head = (f"{count} of a5s's {len(VARS)} settings are set here, and the rest are its defaults "
            "(docs/configuration.md).")
    return "\n".join([head, *lines])


def markdown() -> str:
    """The table docs/configuration.md shows of every setting, by its area."""
    def cell(text: Any) -> str:
        return str(text).replace("|", "\\|")

    def default(var: Var) -> str:
        if var.secret or var.default in (None, "", (), {}, frozenset()):
            return "none" if not var.file else f"none, or `{var.file}` under `A5S_ROOT`"
        value = shown(var, {})[0]
        return f"`{value}`"

    lines, area = [], None
    for var in VARS:
        if var.area != area:
            area = var.area
            lines += ["", f"### {area}", "", "| Variable | Default | Takes | What it sets |",
                      "| --- | --- | --- | --- |"]
        lines.append(f"| `{var.name}` | {cell(default(var))} | {cell(var.takes)} | "
                     f"{cell(var.means[0].upper() + var.means[1:])} |")
    lines += ["", "### Families", "", "| Variables | What they set |", "| --- | --- |"]
    lines += [f"| `{f.pattern}` | {cell(f.means[0].upper() + f.means[1:])} |" for f in FAMILIES]
    return "\n".join(lines[1:]) + "\n"


class Prices(NamedTuple):
    """What a million tokens cost: in, out, and in from the provider's cache, read or written,
    which providers price apart, at the price in when they don't say."""

    input: float
    output: float
    cached_input: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True)
class ModelConfig:
    """An approved model: who serves it, where, and which exact version."""

    alias: str
    provider: str
    api: str  # "openai" or "anthropic": the API style the provider speaks
    base_url: str
    model: str  # the provider's model id, dated where the provider offers one
    key_env: str | None = None  # where its key is; a server on the organisation's network may need none
    region: str = "not stated"  # where the provider serves it, if models.yaml says
    data_classes: tuple[str, ...] = ("synthetic",)
    reported_model: str | None = None  # what every response must report, if not `model`
    # What a million tokens cost, as the provider charges, in the deployment's currency, for
    # what a run costs (core/measures.py); none if not given
    prices: Prices | None = None
    # Whether it's approved to be sent images, such as a screenshot someone sent an agent, as
    # a5s's reader sends them (core/files.py): none is, unless models.yaml says so
    images: bool = False

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.key_env) if self.key_env else None


def load_models(path: Path) -> dict[str, ModelConfig]:
    data = yaml.safe_load(path.read_text())
    models = {}
    for alias, m in data["models"].items():
        if m["api"] not in ("openai", "anthropic"):
            raise ValueError(f"model {alias}: api must be openai or anthropic, not {m['api']}")
        if not re.search(r"\d{4}-?\d{2}-?\d{2}", m["model"]) and not m.get("reported_model"):
            raise ValueError(f"model {alias}: {m['model']} isn't a dated version, so set "
                             "reported_model to what the provider reports for it")
        models[alias] = ModelConfig(
            alias=alias,
            provider=m["provider"],
            api=m["api"],
            base_url=m["base_url"].rstrip("/"),
            model=m["model"],
            key_env=m.get("key_env"),
            region=m.get("region", "not stated"),
            data_classes=tuple(m.get("data_classes", ["synthetic"])),
            reported_model=m.get("reported_model"),
            prices=Prices(float(p["input"]), float(p["output"]),
                          *(None if p.get(k) is None else float(p[k])
                            for k in ("cached_input", "cache_write")))
            if (p := m.get("prices")) else None,
            images=m.get("images") is True,
        )
    return models


def load_currency(path: Path) -> str | None:
    """The currency models.yaml prices models in, as its ISO 4217 code, such as GBP, if it
    names one: the one budgets in the settings are in too (core/spending.py)."""
    found = (yaml.safe_load(path.read_text()) or {}).get("currency")
    if found is None:
        return None
    if not isinstance(found, str) or not re.fullmatch(r"[A-Z]{3}", found):
        raise ValueError(f"models.yaml's currency is a code such as GBP or USD, not {found!r}")
    return found


@dataclass(frozen=True)
class Config:
    """What one part runs with, from the settings above: each default is theirs."""

    database_url: str
    gateway_url: str
    service_token: str
    root: Path
    channels_url: str = CHANNELS_URL.default
    worker_url: str | None = None  # set when workers run as a service: the shared pool
    # Each agent's own worker pool, by its name, such as assistant: an agent named here runs
    # in its pool alone, and any other in the shared one, at worker_url
    worker_urls: dict[str, str] = field(default_factory=dict)
    # and how many of its runs the scheduler works on at once there
    worker_slots: dict[str, int] = field(default_factory=dict)
    # In a worker: the agents its pool runs, if it's one agent's, and in the shared pool,
    # those with pools of their own, which it refuses
    worker_agents: frozenset[str] = frozenset()
    worker_pooled: frozenset[str] = frozenset()
    # Without an identity provider, the local channel takes people's word for who they are.
    # That's for development only, so it has to be asked for.
    development: bool = False
    anchor_store: str | None = None  # where the ledger's locked copies go, such as s3://bucket/a5s
    # The web chat's client at the identity provider: a public client, with PKCE.
    webchat_client_id: str | None = None
    anchor_retain_days: int = ANCHOR_RETAIN_DAYS.default  # how long each copy stays locked
    # The directory's team that runs a5s. Its approvals of a release count as an engineer's,
    # and never as the release approver's.
    team: str = TEAM.default
    # The scenario a5s serves: a class built from its folder and a5s's database URL.
    scenario: str = SCENARIO_CLASS.default
    scenario_folder: Path | None = None  # by default, scenarios/sample
    agents_folder: Path | None = None  # by default, the reference agents in root/agents
    # Where each docs repository a library reads is checked out, by its name (connectors/libraries.py)
    library_root: Path = LIBRARY_ROOT.default
    # The core's own keys, which seal the approvals it has checked, such as of settings. Only
    # the core holds them. The first seals; any others are ones it's moving away from.
    seal_keys: tuple[str, ...] = ()
    operator_token: str = ""  # operators' own, apart from the scheduler's service token
    public_url: str | None = None  # where people reach the channels, for links: else channels_url
    # The sandbox, where the studio tries the agents people are making: a deployment of its own,
    # at this address, by a token they share (a5s/sandbox.py). None if there isn't one
    sandbox_url: str | None = None
    sandbox_token: str = ""
    # Whether this is the sandbox itself, which sets it, never a variable: its tools from MCP
    # servers call each server's declared stand-in, with no token (connectors/mcp.py)
    sandboxed: bool = False
    # Publishing drafts from the studio as pull requests on GitHub, opened as whoever publishes,
    # through GitHub's own sign-in (core/publishing.py): a5s's GitHub App's client id, a public
    # thing, and the agents' repository, as owner/name, and its branch. Without them, the studio
    # offers a draft's folder, and the pull request's words, for its author to open it with
    github_client_id: str | None = None
    github_repo: str | None = None
    github_base: str = GITHUB_BASE.default
    github_url: str = GITHUB_URL.default  # or a GitHub Enterprise server's
    github_api_url: str = GITHUB_API_URL.default  # and its API, such as https://<it>/api/v3

    @property
    def agents_dir(self) -> Path:
        return self.agents_folder or self.root / "agents"

    @property
    def models_file(self) -> Path:
        return self.root / "config" / "models.yaml"

    @property
    def scenario_dir(self) -> Path:
        return self.scenario_folder or self.root / "scenarios" / "sample"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """As the environment gives it: ConfigError for a setting it can't use, though a
        part that starts checks them all first (`check`)."""
        env = os.environ if env is None else env
        return cls(
            database_url=DATABASE_URL.read(env), gateway_url=GATEWAY_URL.read(env),
            service_token=SERVICE_TOKEN.read(env), root=_root(env),
            channels_url=CHANNELS_URL.read(env), worker_url=WORKER_URL.read(env),
            worker_urls=WORKER_URLS.read(env), worker_slots=WORKER_SLOTS.read(env),
            worker_agents=WORKER_AGENTS.read(env), worker_pooled=WORKER_POOLED.read(env),
            development=DEVELOPMENT.read(env), anchor_store=ANCHOR_STORE.read(env),
            webchat_client_id=WEBCHAT_CLIENT_ID.read(env),
            anchor_retain_days=ANCHOR_RETAIN_DAYS.read(env), team=TEAM.read(env),
            scenario=SCENARIO_CLASS.read(env), scenario_folder=SCENARIO_DIR.read(env),
            agents_folder=AGENTS_DIR.read(env), library_root=LIBRARY_ROOT.read(env),
            seal_keys=SEAL_KEYS.read(env), operator_token=OPERATOR_TOKEN.read(env),
            public_url=PUBLIC_URL.read(env), sandbox_url=SANDBOX_URL.read(env), sandbox_token=SANDBOX_TOKEN.read(env),
            github_client_id=GITHUB_CLIENT_ID.read(env), github_repo=GITHUB_REPO.read(env),
            github_base=GITHUB_BASE.read(env), github_url=GITHUB_URL.read(env),
            github_api_url=GITHUB_API_URL.read(env))
