"""The `a5s` command."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import yaml

from a5s import build, db, definitions, devdb, worker
from a5s.config import DEFAULT_DATABASE_URL, Config
from a5s.core import anchor, inbox, ledger, registry, signing
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
    _migrate(Config.from_env(), url)
    print(f"Postgres is up at {url}, and the schema is in place.")
    if url != DEFAULT_DATABASE_URL:
        print(f"Set A5S_DATABASE_URL={url}")


def _migrate(cfg: Config, url: str | None = None) -> None:
    """Bring the schema up to date and set up the scenario's tables, as the administrator."""
    url = url or cfg.database_url
    ran = db.migrate(url)
    with db.transaction(url) as conn:
        build.scenario(cfg).setup(conn, db.ROLES["gateway"])
    passwords = {part: os.environ[f"A5S_DB_{part.upper()}_PASSWORD"] for part in db.ROLES
                 if os.environ.get(f"A5S_DB_{part.upper()}_PASSWORD")}
    db.set_passwords(url, passwords)
    print(f"Migrated: {', '.join(ran) or 'nothing new'}. "
          f"Passwords set for {', '.join(passwords) or 'no roles'}.")


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


def _say(cfg: Config, person: str, agent: str, text: str, wait: float = 600) -> None:
    """Send a message through the core's local channel, and print what a5s says back."""
    token = os.environ.get("A5S_TOKEN")  # the person's, from the identity provider, if a5s uses one
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(base_url=cfg.channels_url, headers=headers, timeout=90) as channel:
        sent = channel.post("/channels/local/messages",
                            json={"person": person, "agent": agent, "text": text})
        if sent.status_code >= 400:
            sys.exit(sent.json()["detail"])
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            answers = channel.get(f"/channels/local/messages/{sent.json()['message']}",
                                  params={"wait": 60, "person": person})
            if answers.status_code >= 400:
                sys.exit(answers.json()["detail"])
            if replies := answers.json()["replies"]:
                print("\n\n".join(replies))
                return
    sys.exit("No answer yet. Is the scheduler running?")


def _service(cfg: Config, name: str):
    if name == "gateway":
        return build.app(cfg)
    if name == "worker":
        return worker.create_app(cfg.gateway_url)
    return inbox.create_app(build.gateway(cfg))  # the channels' endpoints, in the core


def _scheduler(cfg: Config) -> None:
    hand_off = remote_worker(cfg.worker_url) if cfg.worker_url else worker.run_agent
    Scheduler(cfg, build.scenario(cfg), worker=hand_off).listen(threading.Event())


def _dev(cfg: Config) -> None:
    """The core, the channels and the scheduler in one process, for development."""
    import uvicorn

    cfg = replace(cfg, development=True)
    gw = build.gateway(cfg)
    for app, port in ((build.app(cfg), 8700), (inbox.create_app(gw), 8703)):
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
    print("a5s is running for development: the gateway on port 8700, and the channels on 8703.\n"
          "Send messages with `a5s say --as <person> <agent> <text>`. Press Ctrl-C to stop.",
          flush=True)
    Scheduler(cfg, gw.scenario).listen(threading.Event())


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
    sub.add_parser("migrate", help="bring the schema up to date, as the administrator")
    sub.add_parser("apply", help="bring instances in line with the settings and releases")
    pin = sub.add_parser("pin", help="pin the schemas of an agent's tools in its release")
    pin.add_argument("agent")
    keygen = sub.add_parser("keygen", help="make a signing key for a person")
    keygen.add_argument("person")
    keygen.add_argument("--out", type=Path, default=Path("keys"))
    sign = sub.add_parser("sign", help="sign the current settings, as a person")
    sign.add_argument("--as", dest="person", required=True)
    sign.add_argument("--key", type=Path, help="their private key (default: the sample's)")
    sub.add_parser("setup", help="migrate and apply the settings, as the administrator")
    for name, port, what in (("gateway", 8700, "the gateway, in the trusted core"),
                             ("worker", 8702, "a worker, which holds no secrets"),
                             ("channels", 8703, "the core's endpoints, where messages arrive")):
        service = sub.add_parser(name, help=f"run {what}")
        service.add_argument("--host", default="127.0.0.1")
        service.add_argument("--port", type=int, default=port)
    sub.add_parser("scheduler", help="answer the messages the core receives")
    sub.add_parser("dev", help="run the core, the channels and the scheduler, for development")
    say = sub.add_parser("say", help="send an agent a message, as a person")
    say.add_argument("--as", dest="person", required=True)
    say.add_argument("agent")
    say.add_argument("text")
    for verb in ("suspend", "resume"):
        p = sub.add_parser(verb, help=f"{verb} an instance")
        p.add_argument("instance")
        p.add_argument("--by", help="who you are, in development; else your sign-in in A5S_TOKEN")
    copy = sub.add_parser("anchor", help="copy the ledger to locked storage")
    copy.add_argument("--every", type=int, metavar="SECONDS", help="keep copying, this often")
    led = sub.add_parser("ledger", help="read or verify the ledger, against its copies too")
    led.add_argument("what", choices=["tail", "verify"])
    led.add_argument("-n", type=int, default=20)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("a5s").setLevel(logging.INFO)
    root = Path.cwd()
    if args.command == "up":
        return _dev_up(root)
    if args.command == "down":
        return devdb.stop(root / ".a5s" / "pg")
    if args.command == "keygen":
        return _keygen(args.person, args.out)
    cfg = Config.from_env()
    if args.command == "migrate":
        _migrate(cfg)
    elif args.command == "apply":
        _apply(cfg)
    elif args.command == "pin":
        _pin(cfg, args.agent)
    elif args.command == "sign":
        _sign(cfg, args.person, args.key)
    elif args.command == "setup":
        _migrate(cfg)
        _apply(cfg)
    elif args.command in ("gateway", "worker", "channels"):
        import uvicorn

        uvicorn.run(_service(cfg, args.command), host=args.host, port=args.port)
    elif args.command == "scheduler":
        _scheduler(cfg)
    elif args.command == "dev":
        _dev(cfg)
    elif args.command == "say":
        _say(cfg, args.person, args.agent, args.text)
    elif args.command in ("suspend", "resume"):
        print(_admin(cfg, f"/instances/{args.instance}/{args.command}",
                     {"by": args.by, "identity": os.environ.get("A5S_TOKEN")}))
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
