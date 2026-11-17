"""Assembles a5s's parts from its configuration."""

from __future__ import annotations

import importlib
from datetime import timedelta

import httpx

from a5s import db, definitions
from a5s.config import Config, load_currency, load_models
from a5s.connectors import libraries, mailboxes, mcp
from a5s.contract import Scenario
from a5s.core import delegation, memberships, metrics, registration, registry, status, traces
from a5s.core.events import EventsConfig
from a5s.core.gateway import CORE_TOOLS, Gateway, create_app
from a5s.core.identity import verifier_from_env
from a5s.core.matrix import Matrix, MatrixConfig
from a5s.core.policy import PolicyEngine
from a5s.core.releases import Releases, running
from a5s.core.slack import Slack, SlackConfig
from a5s.core.stores import Store, store_from_url
from a5s.core.teams import Teams, TeamsConfig


def scenario(cfg: Config, delegated: mcp.Delegated | None = None) -> Scenario:
    """The scenario a5s serves, such as its own sample: any class that meets the contract, with
    the tools of MCP servers' its folder's mcp.yaml declares beside its own (connectors/mcp.py),
    and of the libraries its libraries.yaml names (connectors/libraries.py), those that act as
    the person with their own tokens (`delegated`), in the core, and of the mailboxes its
    mailboxes.yaml names (connectors/mailboxes.py), which the core alone reads, with the
    deployment's app."""
    module, _, name = cfg.scenario.partition(":")
    found = getattr(importlib.import_module(module), name)(cfg.scenario_dir, cfg.database_url)
    found = mcp.served(found, cfg.scenario_dir, sandboxed=cfg.sandboxed,
                       reserved=frozenset(CORE_TOOLS), delegated=delegated)
    found = libraries.served(found, cfg.scenario_dir, root=cfg.library_root,
                             sandboxed=cfg.sandboxed, reserved=frozenset(CORE_TOOLS),
                             delegated=delegated)
    return mailboxes.served(found, cfg.scenario_dir, database=cfg.database_url,
                            sandboxed=cfg.sandboxed, reserved=frozenset(CORE_TOOLS),
                            app=mailboxes.App.from_env())


def delegating(cfg: Config) -> tuple[delegation.Delegation | None, mcp.Delegated | None]:
    """The systems people may connect their accounts in (A5S_DELEGATION), and, in the core,
    which alone holds the seal keys and a5s's client secrets there, how a tool that acts as the
    person gets their token. The core doesn't start with a system's secret missing, nor with an
    MCP server acting as the person in a system the deployment doesn't name."""
    found = delegation.Delegation.from_env(secrets_too=bool(cfg.seal_keys))
    core = bool(cfg.seal_keys) and not cfg.sandboxed
    if core and found and (missing := [s.name for s in found.systems if not s.secret]):
        raise RuntimeError(f"A5S_DELEGATION names {', '.join(missing)}: set a5s's client secret "
                           f"there in A5S_DELEGATION_<NAME>_SECRET, for the core")
    declared = mcp.declared(cfg.scenario_dir)
    for name, server in (declared.servers.items() if declared else ()):
        if server.as_person and not cfg.sandboxed and (found is None or found.system(server.as_person) is None):
            raise RuntimeError(f"the {name} MCP server acts as the person in {server.as_person}, "
                               "which A5S_DELEGATION doesn't name, so nobody could connect it")
    for name, system in libraries.systems(cfg.scenario_dir).items():
        if not cfg.sandboxed and (found is None or found.system(system) is None):
            raise RuntimeError(f"the {name} library is read as the person in {system}, which "
                               "A5S_DELEGATION doesn't name, so nobody could connect it")
    return found, (delegation.supplier(cfg.database_url, cfg.seal_keys, found)
                   if core and found else None)


def gateway(cfg: Config, http: httpx.Client | None = None) -> Gateway:
    systems, delegated = delegating(cfg)
    sc = scenario(cfg, delegated)
    pack = sc.policy_pack()
    # Its directory, with the roles the identity provider's groups give, as the settings in
    # force map them (core/memberships.py)
    directory = memberships.grouped(sc, cfg.database_url, lambda conn: gw.groups_in_force(conn))
    gw = Gateway(
        cfg=cfg,
        scenario=directory,
        policy=PolicyEngine(packs=(pack,) if pack else ()),
        models=load_models(cfg.models_file),
        currency=load_currency(cfg.models_file),
        definitions=definitions.load_all(cfg.agents_dir),
        http=http or httpx.Client(),
        identity=verifier_from_env(),
        teams=Teams(teams) if (teams := TeamsConfig.from_env()) else None,
        matrix=Matrix(matrix) if (matrix := MatrixConfig.from_env()) else None,
        slack=Slack(slack) if (slack := SlackConfig.from_env()) else None,
        events=EventsConfig.from_env(),
        releases=Releases(running(cfg.root, cfg.scenario_dir, cfg.agents_dir)),
        registry=registration.Registry.from_env(),  # IT's inventory, if the deployment asks
        delegation=systems,  # the accounts people may connect, so agents act as them there
        mail=mailboxes.of(sc),  # the mailboxes it asks for new mail, if the scenario names any
    )
    return gw


def store(cfg: Config) -> Store | None:
    if not cfg.anchor_store:
        return None
    return store_from_url(cfg.anchor_store, timedelta(days=cfg.anchor_retain_days))


def app(cfg: Config | None = None):
    cfg = cfg or Config.from_env()
    if not cfg.service_token:
        raise RuntimeError("Set A5S_SERVICE_TOKEN, or run `a5s up` to create one.")
    if (mailboxes.declared(cfg.scenario_dir) and not cfg.sandboxed
            and mailboxes.App.from_env() is None):  # the core alone: the channels app, built
        raise RuntimeError("the scenario's mailboxes.yaml names mailboxes, which the core reads "
                           "with the deployment's app in Microsoft 365: set A5S_MAIL_TENANT, "
                           "A5S_MAIL_CLIENT_ID and A5S_MAIL_CLIENT_SECRET")  # from the same
    traces.setup("a5s-gateway")  # scenario, needs no secret of it (round 15, D4)  # if the deployment names an OpenTelemetry endpoint
    gw = gateway(cfg)
    metrics.setup("a5s-gateway", lambda: read_status(gw))  # and its figures, for its monitoring
    return create_app(gw)


def read_status(gw: Gateway) -> dict:
    """The status, as `a5s status` reads it, but never naming the deciders a rubber-stamp flag
    would name, and whom each instance serves, which decides only which instances' own figures
    may go out: for the operators' figures (core/metrics.py)."""
    with db.transaction(gw.url) as conn:
        found = status.report(conn, gw.breakers.open(), gw.cfg.seal_keys)
        found["serving"] = {i["id"]: set(registry.served(gw.scenario, i["serves"]))
                            for i in conn.execute("select id, serves from instances")}
        found["fewest_people"] = gw.data_protection(conn).fewest_people
    return found
