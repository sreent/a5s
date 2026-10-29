"""The `a5s` command."""

from __future__ import annotations

import argparse
import base64
import hashlib
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
from a5s.contract import Signature
from a5s.core import anchor, inbox, ledger, registry, releases, signing
from a5s.services.scheduler import Scheduler, remote_worker

log = logging.getLogger("a5s")


def _dev_up(root: Path) -> None:
    state = root / ".a5s"
    state.mkdir(exist_ok=True)
    for name in ("service-token", "seal-key"):  # the core's own secrets, for development
        secret = state / name
        if not secret.exists():
            secret.write_text(secrets.token_urlsafe(32))
            secret.chmod(0o600)
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


def _propose(cfg: Config, path: Path | None) -> None:
    """Ask the instance approvers to approve the settings where they work, with a card."""
    raw = path.read_bytes() if path else build.scenario(cfg).settings().raw
    asked = _admin(cfg, "/settings/proposals", {"raw": base64.b64encode(raw).decode()})
    print(f"Serial {asked['serial']} of the settings:")
    for change in asked["changes"]:
        print(f"- {change['text']}")
    if asked["new"]:
        print(f"Asked {', '.join(asked['asked']) or 'nobody: no instance approver is in the directory'}"
              f" to approve it. a5s applies it once one has.")
    else:
        print("The approvers were asked about this version before.")
    print(f"It's approved at {asked['link']}")


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


def _inbox(cfg: Config, person: str, wait: float) -> None:
    """Print what's been written to a person without answering them, such as reminders."""
    token = os.environ.get("A5S_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(base_url=cfg.channels_url, headers=headers, timeout=wait + 30) as channel:
        found = channel.get("/channels/local/inbox", params={"person": person, "wait": wait})
    if found.status_code >= 400:
        sys.exit(found.json()["detail"])
    for message in found.json()["messages"]:
        print(f"[{message['at'][:16].replace('T', ' ')} UTC, {message['from']}] {message['text']}")
    if not found.json()["messages"]:
        print("Nothing new.")


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
          "Chat in a browser at http://127.0.0.1:8703/chat/, or send messages with\n"
          "`a5s say --as <person> <agent> <text>`. Press Ctrl-C to stop.", flush=True)
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
        except anchor.AnchorError as exc:  # the ledger doesn't match its copies: stop, loudly
            log.error("%s", exc)
            sys.exit(1)
        except Exception:
            if every is None:
                raise
            log.exception("copying the ledger failed")  # such as the store being down: try again
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


def _release(cfg: Config, args: argparse.Namespace) -> None:
    """Approving releases: each organisation's people sign what a5s is in their deployment."""
    if args.what == "manifest":  # of a source tree, such as when an image is built
        root = args.root or Path.cwd()
        sys.stdout.buffer.write(releases.manifest(root, root / "scenarios" / "sample"))
        return
    if args.what == "sign":
        raw = args.manifest.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        key = args.key or cfg.scenario_dir / "keys" / f"{args.person}.key"
        value = signing.sign(key.read_text().strip(), raw, signing.RELEASE)
        signed = yaml.safe_load(args.out.read_text()) if args.out.exists() else None
        if signed and signed.get("release") != digest:
            sys.exit(f"{args.out} holds signatures for another release.")
        others = [s for s in (signed or {}).get("signatures", []) if s["signer"] != args.person]
        args.out.write_text(
            "# Signatures over a release of a5s, made with `a5s release sign`.\n"
            + yaml.safe_dump({"release": digest, "signatures": [
                *others, {"signer": args.person, "value": value}]}, sort_keys=False))
        print(f"{args.person} signed release {yaml.safe_load(raw)['version']} ({digest[:12]}).")
        return
    sc = build.scenario(cfg)
    if args.what == "approve":  # as the database's administrator
        raw = args.manifest.read_bytes()
        signed = yaml.safe_load(args.signatures.read_text()) or {}
        if signed.get("release") != hashlib.sha256(raw).hexdigest():
            sys.exit(f"{args.signatures} holds signatures for another release.")
        with db.transaction(cfg.database_url) as conn:
            verdict = releases.record(conn, raw, [Signature(s["signer"], s["value"])
                                                  for s in signed.get("signatures", [])],
                                      sc, cfg.team, args.advisory, baseline=args.baseline)
    else:
        current = releases.running(cfg.root, cfg.scenario_dir)
        if args.what == "show":
            sys.stdout.buffer.write(current.raw)
            return
        print(f"Release {current.version} of a5s, {current.digest}.")
        if current.problems:
            sys.exit("It can't run: " + "; ".join(current.problems))
        with db.transaction(cfg.database_url) as conn:
            verdict = releases.check(conn, current.digest, sc, cfg.team)
            if not verdict.needs:  # nobody has signed it here yet: say what it needs
                need = releases.needs(yaml.safe_load(current.raw), releases.last_approved(conn))
                verdict = releases.Verdict(False, tuple(need), verdict.missing)
    for need in verdict.needs:
        print(f"- It needs {releases.who(need.role)}, because {need.why}.")
    if verdict.signed_by:
        print(f"Signed by {', '.join(verdict.signed_by)}.")
    if not verdict.ok:
        sys.exit("Not approved here: " + "; ".join(verdict.missing))
    print("Approved here.")


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
    propose = sub.add_parser("propose", help="ask the instance approvers to approve the settings "
                                             "where they work, with a card")
    propose.add_argument("--file", type=Path, help="a version of the settings (default: the "
                                                   "scenario's)")
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
    box = sub.add_parser("inbox", help="read what's been written to a person, such as reminders")
    box.add_argument("--as", dest="person", required=True)
    box.add_argument("--wait", type=float, default=0, metavar="SECONDS")
    for verb in ("suspend", "resume"):
        p = sub.add_parser(verb, help=f"{verb} an instance")
        p.add_argument("instance")
        p.add_argument("--by", help="who you are, in development; else your sign-in in A5S_TOKEN")
    copy = sub.add_parser("anchor", help="copy the ledger to locked storage")
    copy.add_argument("--every", type=int, metavar="SECONDS", help="keep copying, this often")
    rel = sub.add_parser("release", help="approve a release of a5s for this deployment")
    rel_sub = rel.add_subparsers(dest="what", required=True)
    manifest = rel_sub.add_parser("manifest", help="print the manifest of a source tree, as an "
                                                   "image is built with")
    manifest.add_argument("--root", type=Path)
    rel_sub.add_parser("show", help="print the release a5s is here, for its approvers to sign")
    rel_sign = rel_sub.add_parser("sign", help="sign a release's manifest, as a person")
    rel_sign.add_argument("--as", dest="person", required=True)
    rel_sign.add_argument("--manifest", type=Path, default=Path("release.yaml"))
    rel_sign.add_argument("--key", type=Path, help="their private key (default: the sample's)")
    rel_sign.add_argument("--out", type=Path, default=Path("release.sig"))
    approve = rel_sub.add_parser("approve", help="record signatures over a release, as the "
                                                 "administrator")
    approve.add_argument("--manifest", type=Path, default=Path("release.yaml"))
    approve.add_argument("--signatures", type=Path, default=Path("release.sig"))
    approve.add_argument("--advisory", help="the security advisory it fixes, such as GHSA-...")
    approve.add_argument("--baseline", action="store_true",
                         help="weigh it against nothing, so it needs everyone: for when someone "
                              "who approved an earlier release has left")
    rel_sub.add_parser("status", help="whether this deployment approved the release a5s is")
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
    elif args.command == "propose":
        _propose(cfg, args.file)
    elif args.command in ("gateway", "worker", "channels"):
        import uvicorn

        uvicorn.run(_service(cfg, args.command), host=args.host, port=args.port)
    elif args.command == "scheduler":
        _scheduler(cfg)
    elif args.command == "dev":
        _dev(cfg)
    elif args.command == "say":
        _say(cfg, args.person, args.agent, args.text)
    elif args.command == "inbox":
        _inbox(cfg, args.person, args.wait)
    elif args.command in ("suspend", "resume"):
        print(_admin(cfg, f"/instances/{args.instance}/{args.command}",
                     {"by": args.by, "identity": os.environ.get("A5S_TOKEN")}))
    elif args.command == "anchor":
        _anchor(cfg, args.every)
    elif args.command == "release":
        _release(cfg, args)
    elif args.command == "ledger" and args.what == "verify":
        _verify(cfg)
    elif args.command == "ledger":
        with db.transaction(cfg.database_url) as conn:
            for entry in ledger.entries(conn, limit=args.n):
                print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
