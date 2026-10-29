"""Assembles a5s's parts from its configuration."""

from __future__ import annotations

import importlib
from datetime import timedelta

import httpx

from a5s import definitions
from a5s.config import Config, load_models
from a5s.contract import Scenario
from a5s.core.gateway import Gateway, create_app
from a5s.core.identity import verifier_from_env
from a5s.core.policy import PolicyEngine
from a5s.core.releases import Releases, running
from a5s.core.stores import Store, store_from_url
from a5s.core.teams import Teams, TeamsConfig


def scenario(cfg: Config) -> Scenario:
    """The scenario a5s serves, such as its own sample: any class that meets the contract."""
    module, _, name = cfg.scenario.partition(":")
    return getattr(importlib.import_module(module), name)(cfg.scenario_dir, cfg.database_url)


def gateway(cfg: Config, http: httpx.Client | None = None) -> Gateway:
    sc = scenario(cfg)
    pack = sc.policy_pack()
    return Gateway(
        cfg=cfg,
        scenario=sc,
        policy=PolicyEngine(packs=(pack,) if pack else ()),
        models=load_models(cfg.models_file),
        definitions=definitions.load_all(cfg.agents_dir),
        http=http or httpx.Client(),
        identity=verifier_from_env(),
        teams=Teams(teams) if (teams := TeamsConfig.from_env()) else None,
        releases=Releases(running(cfg.root, cfg.scenario_dir)),
    )


def store(cfg: Config) -> Store | None:
    if not cfg.anchor_store:
        return None
    return store_from_url(cfg.anchor_store, timedelta(days=cfg.anchor_retain_days))


def app(cfg: Config | None = None):
    cfg = cfg or Config.from_env()
    if not cfg.service_token:
        raise RuntimeError("Set A5S_SERVICE_TOKEN, or run `a5s up` to create one.")
    return create_app(gateway(cfg))
