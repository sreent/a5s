"""The `a5s` command."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

import httpx

from a5s import build, db, definitions, devdb
from a5s.config import DEFAULT_DATABASE_URL, Config
from a5s.core import ledger, registry
from a5s.services import channels
from a5s.services.scheduler import Scheduler


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
        applied = registry.apply(conn, definitions.load_all(cfg.agents_dir), sc.settings(), sc.tools())
    print("Applied:", ", ".join(applied))


def _pin(cfg: Config, agent: str) -> None:
    tools = build.scenario(cfg).tools()
    lock = definitions.pin(cfg.agents_dir / agent, {n: t.schema_hash for n, t in tools.items()})
    print(f"Pinned {agent}'s tools in {lock}. Run `a5s apply` to roll the new release out.")


def _say(cfg: Config, person: str, agent: str, text: str) -> None:
    sc = build.scenario(cfg)
    reply = Scheduler(cfg, sc).handle_message(person=person, agent=agent, text=text)
    with db.transaction(cfg.database_url) as conn:
        channels.undelivered(conn, person=person)  # shown below, so mark it delivered
    print(reply)


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
    gateway = sub.add_parser("gateway", help="run the gateway")
    gateway.add_argument("--port", type=int, default=8700)
    say = sub.add_parser("say", help="send an agent a message, as a person")
    say.add_argument("--as", dest="person", required=True)
    say.add_argument("agent")
    say.add_argument("text")
    for verb in ("suspend", "resume"):
        p = sub.add_parser(verb, help=f"{verb} an instance")
        p.add_argument("instance")
        p.add_argument("--by", required=True)
    led = sub.add_parser("ledger", help="read or verify the ledger")
    led.add_argument("what", choices=["tail", "verify"])
    led.add_argument("-n", type=int, default=20)
    args = parser.parse_args(argv)

    root = Path.cwd()
    if args.command == "up":
        return _dev_up(root)
    if args.command == "down":
        return devdb.stop(root / ".a5s" / "pg")
    cfg = Config.from_env()
    if args.command == "migrate":
        db.migrate(cfg.database_url)
    elif args.command == "apply":
        _apply(cfg)
    elif args.command == "pin":
        _pin(cfg, args.agent)
    elif args.command == "gateway":
        import uvicorn

        uvicorn.run(build.app(cfg), host="127.0.0.1", port=args.port)
    elif args.command == "say":
        _say(cfg, args.person, args.agent, args.text)
    elif args.command in ("suspend", "resume"):
        print(_admin(cfg, f"/instances/{args.instance}/{args.command}", {"by": args.by}))
    elif args.command == "ledger" and args.what == "verify":
        with db.transaction(cfg.database_url) as conn:
            print(ledger.verify(conn))
    elif args.command == "ledger":
        with db.transaction(cfg.database_url) as conn:
            for entry in ledger.entries(conn, limit=args.n):
                print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
