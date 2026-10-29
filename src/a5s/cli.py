"""The `a5s` command."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
import yaml

from a5s import build, db, definitions, devdb, worker
from a5s.config import DEFAULT_DATABASE_URL, Config
from a5s.core import anchor, ledger, registry, signing
from a5s.core.identity import verifier_from_env
from a5s.services import channels
from a5s.services.scheduler import Scheduler, remote_worker

log = logging.getLogger("a5s")


def _dev_up(root: Path) -> None:
    state = root / ".a5s"
    state.mkdir(exist_ok=True)
    token_file = state / "service-token"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32))
        token_file.chmod(0o600)
    url = devdb.start(state / "pg", 54329)
    db.migrate(url)
    print(f"Postgres is up at {url}, and the schema is in place.")
    if url != DEFAULT_DATABASE_URL:
        print(f"Set A5S_DATABASE_URL={url}")


def _apply(cfg: Config) -> None:
    sc = build.scenario(cfg)
    with db.transaction(cfg.database_url) as conn:
        result = registry.apply(conn, definitions.load_all(cfg.agents_dir), sc.settings(),
                                sc.tools(), sc.person, sc.name)
    if result.refused:
        sys.exit("Not applied, because " + "; ".join(result.refused) + ".")
    print(f"Applied {', '.join(result.instances)}, signed by {', '.join(result.signers)}.")


def _keygen(person: str, folder: Path) -> None:
    private, public = signing.keypair()
    folder.mkdir(parents=True, exist_ok=True)
    key = folder / f"{person}.key"
    key.write_text(private + "\n")
    key.chmod(0o600)
    (folder / f"{person}.pub").write_text(public + "\n")
    print(f"Wrote {key}, which stays with {person}, and {person}.pub for the directory.")


def _sign(cfg: Config, person: str, key: Path | None) -> None:
    folder = cfg.scenario_dir
    key = key or folder / "keys" / f"{person}.key"
    raw = (folder / "settings.yaml").read_bytes()
    value = signing.sign(key.read_text().strip(), raw)
    sig_file = folder / "settings.sig"
    current = yaml.safe_load(sig_file.read_text()) if sig_file.exists() else None
    others = [s for s in (current or {}).get("signatures", []) if s["signer"] != person]
    sig_file.write_text(
        "# Signatures over settings.yaml, made with `a5s sign`. Change the settings,\n"
        "# and these no longer match: the new version needs signing again.\n"
        + yaml.safe_dump({"signatures": [*others, {"signer": person, "value": value}]},
                         sort_keys=False)
    )
    print(f"{person} signed this version of the settings.")


def _pin(cfg: Config, agent: str) -> None:
    tools = build.scenario(cfg).tools()
    lock = definitions.pin(cfg.agents_dir / agent, {n: t.schema_hash for n, t in tools.items()})
    print(f"Pinned {agent}'s tools in {lock}. Run `a5s apply` to roll the new release out.")


def _say(cfg: Config, person: str, agent: str, text: str) -> None:
    token = os.environ.get("A5S_TOKEN")  # the person's, from the identity provider, if a5s uses one
    if cfg.scheduler_url:  # the scheduler runs as a service, so ask it through the local channel
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = httpx.post(f"{cfg.scheduler_url}/channels/local/messages", headers=headers,
                              json={"person": person, "agent": agent, "text": text}, timeout=600)
        if response.status_code in (401, 403):
            sys.exit(response.json()["detail"])
        response.raise_for_status()
        reply = response.json()["reply"]
        httpx.get(f"{cfg.scheduler_url}/channels/local/outbox/{person}", headers=headers, timeout=30)
    else:
        sc = build.scenario(cfg)
        reply = Scheduler(cfg, sc).handle_message(person=person, agent=agent, text=text,
                                                  identity=token)
        with db.transaction(cfg.database_url) as conn:
            channels.undelivered(conn, person=person)  # it's printed below
    print(reply)


def _service(cfg: Config, name: str):
    if name == "gateway":
        return build.app(cfg)
    if name == "worker":
        return worker.create_app(cfg.gateway_url)
    hand_off = remote_worker(cfg.worker_url) if cfg.worker_url else worker.run_agent
    scheduler = Scheduler(cfg, build.scenario(cfg), worker=hand_off)
    return channels.create_app(scheduler, cfg.database_url, verifier_from_env())


def _anchor(cfg: Config, every: int | None) -> None:
    store = build.store(cfg)
    if store is None:
        sys.exit("Set A5S_ANCHOR_STORE to a locked store, such as s3://bucket/a5s.")
    while True:
        try:
            with db.transaction(cfg.database_url) as conn:
                made = anchor.anchor(conn, store)
            print(f"Copied entries {made[0].first} to {made[-1].seq}." if made
                  else "Nothing new to copy.", flush=True)
        except Exception:
            if every is None:
                raise
            log.exception("copying the ledger failed")  # it's tried again next time
        if every is None:
            return
        time.sleep(every)


def _verify(cfg: Config) -> None:
    store = build.store(cfg)
    with db.transaction(cfg.database_url) as conn:
        chain = ledger.verify(conn)
        copies = anchor.check(conn, store) if store else None
    print(chain)
    if copies:
        print(copies)
    elif cfg.anchor_store is None:
        print("The ledger has no copies to check against: set A5S_ANCHOR_STORE.")
    if not chain.ok or (copies and not copies.ok):
        sys.exit(1)


def _admin(cfg: Config, path: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {cfg.service_token}"}
    with httpx.Client(base_url=cfg.gateway_url, headers=headers, timeout=30) as gw:
        response = gw.post(path, json=body) if body is not None else gw.get(path)
    if response.status_code >= 400:
        sys.exit(f"{response.status_code}: {response.text}")
    return response.json()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="a5s", description="An agent OS on Deep Agents.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up", help="start a local Postgres and set up the schema")
    sub.add_parser("down", help="stop the local Postgres")
    sub.add_parser("migrate", help="set up the schema")
    sub.add_parser("apply", help="bring instances in line with the settings and releases")
    pin = sub.add_parser("pin", help="pin the schemas of an agent's tools in its release")
    pin.add_argument("agent")
    keygen = sub.add_parser("keygen", help="make a signing key for a person")
    keygen.add_argument("person")
    keygen.add_argument("--out", type=Path, default=Path("keys"))
    sign = sub.add_parser("sign", help="sign the current settings, as a person")
    sign.add_argument("--as", dest="person", required=True)
    sign.add_argument("--key", type=Path, help="their private key (default: the sample's)")
    sub.add_parser("setup", help="set up the schema and apply the settings, for a deployment")
    for name, port, what in (("gateway", 8700, "the gateway, in the trusted core"),
                             ("scheduler", 8701, "the scheduler, with the local channel"),
                             ("worker", 8702, "a worker, which holds no secrets")):
        service = sub.add_parser(name, help=f"run {what}")
        service.add_argument("--host", default="127.0.0.1")
        service.add_argument("--port", type=int, default=port)
    say = sub.add_parser("say", help="send an agent a message, as a person")
    say.add_argument("--as", dest="person", required=True)
    say.add_argument("agent")
    say.add_argument("text")
    for verb in ("suspend", "resume"):
        p = sub.add_parser(verb, help=f"{verb} an instance")
        p.add_argument("instance")
        p.add_argument("--by", required=True)
    copy = sub.add_parser("anchor", help="copy the ledger to locked storage")
    copy.add_argument("--every", type=int, metavar="SECONDS", help="keep copying, this often")
    led = sub.add_parser("ledger", help="read or verify the ledger, against its copies too")
    led.add_argument("what", choices=["tail", "verify"])
    led.add_argument("-n", type=int, default=20)
    args = parser.parse_args(argv)

    root = Path.cwd()
    if args.command == "up":
        return _dev_up(root)
    if args.command == "down":
        return devdb.stop(root / ".a5s" / "pg")
    if args.command == "keygen":
        return _keygen(args.person, args.out)
    cfg = Config.from_env()
    if args.command == "migrate":
        db.migrate(cfg.database_url)
    elif args.command == "apply":
        _apply(cfg)
    elif args.command == "pin":
        _pin(cfg, args.agent)
    elif args.command == "sign":
        _sign(cfg, args.person, args.key)
    elif args.command == "setup":
        db.migrate(cfg.database_url)
        _apply(cfg)
    elif args.command in ("gateway", "scheduler", "worker"):
        import uvicorn

        uvicorn.run(_service(cfg, args.command), host=args.host, port=args.port)
    elif args.command == "say":
        _say(cfg, args.person, args.agent, args.text)
    elif args.command in ("suspend", "resume"):
        print(_admin(cfg, f"/instances/{args.instance}/{args.command}", {"by": args.by}))
    elif args.command == "anchor":
        _anchor(cfg, args.every)
    elif args.command == "ledger" and args.what == "verify":
        _verify(cfg)
    elif args.command == "ledger":
        with db.transaction(cfg.database_url) as conn:
            for entry in ledger.entries(conn, limit=args.n):
                print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
