"""The `a5s` command."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import signal
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml

from a5s import build, db, definitions, devdb, worker
from a5s.client import Client, Refused
from a5s.config import DEFAULT_DATABASE_URL, Config
from a5s.contract import Signature
from a5s.core import (
    anchor,
    audit,
    erasure,
    inbox,
    ledger,
    measures,
    registry,
    releases,
    signing,
    status,
    studio,
)
from a5s.services.scheduler import Scheduler, remote_worker

log = logging.getLogger("a5s")
KEEP_ALIVE = 30  # seconds a server keeps an idle connection open, past its clients' 5


def _officer_only(path: str) -> None:
    if os.name != "nt":
        return
    import csv
    import subprocess
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    who = subprocess.check_output([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                                  text=True)
    sid = next(csv.reader([who]))[1]
    subprocess.run([str(system / "icacls.exe"), path, "/inheritance:r", "/grant:r", f"*{sid}:F"],
                   capture_output=True, check=True)


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
        print(f"Asked {', '.join(asked['asked']) or 'nobody: none of its approvers is in the directory'}"
              f" to approve it. a5s applies it once everyone it needs has.")
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


def _summaries(cfg: Config, person: str, agent: str) -> None:
    """Print what a5s keeps of a person's conversation with an agent beyond what each run is
    given: a summary of each topic, which they can have the agent correct."""
    token = os.environ.get("A5S_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(base_url=cfg.channels_url, headers=headers, timeout=30) as channel:
        found = channel.get("/channels/local/summaries", params={"person": person, "agent": agent})
    if found.status_code >= 400:
        sys.exit(found.json()["detail"])
    for summary in found.json()["summaries"]:
        print(f"[{summary['topic']}, as of {summary['at'][:16].replace('T', ' ')} UTC]\n"
              f"{summary['text']}\n")
    if not found.json()["summaries"]:
        print("Nothing yet: the whole conversation still fits in each run.")


def _service(cfg: Config, name: str):
    if name != "worker":  # never against a schema a later release made
        db.known(cfg.database_url)
    if name == "gateway":
        return build.app(cfg)
    if name == "worker":
        return worker.create_app(cfg.gateway_url, cfg.worker_agents, cfg.worker_pooled)
    return inbox.create_app(build.gateway(cfg))  # the channels' endpoints, in the core


def _stopping() -> threading.Event:
    """What's set once the process is asked to stop, as Kubernetes asks a pod before an
    upgrade replaces it: the scheduler then takes no more work, and finishes the runs it has
    in flight, so none loses its answer. What arrives meanwhile waits in the core."""
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    return stop


def _scheduler(cfg: Config) -> None:
    db.known(cfg.database_url)  # never against a schema a later release made
    hand_off = remote_worker(cfg.worker_url) if cfg.worker_url else worker.run_agent
    pools = {agent: remote_worker(url) for agent, url in cfg.worker_urls.items()}
    Scheduler(cfg, build.scenario(cfg), worker=hand_off, pools=pools).listen(_stopping())


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


def _audit(cfg: Config, args: argparse.Namespace) -> None:
    """The audit trail (core/audit.py): through the core's API, but for an export's check,
    which needs only the file, and the locked copies, where A5S_ANCHOR_STORE names them."""
    if args.what == "verify":
        if not args.file:
            sys.exit("name the export to check")
        lines = [json.loads(line) for line in Path(args.file).read_text().splitlines() if line]
        bounds = lines.pop(0)["export"] if lines and "export" in lines[0] else None
        store = build.store(cfg)
        why = audit.checks(lines) or (audit.bounded(bounds, lines) if bounds else None)
        if store:
            why = why or audit.copied(lines + (audit.either_side(bounds) if bounds else []),
                                      store) or (audit.ended(bounds, store) if bounds else None)
        if why:
            sys.exit(f"The export doesn't check out: {why}.")
        held = f"The export's {len(lines)} entries" + (
            f", the period's {bounds['first']} to {bounds['last']}," if bounds and lines else "")
        if not bounds:
            print(f"{held} hold together, but it doesn't say what period it holds, so a5s can't "
                  "check it holds the whole of it: export it again with this version of a5s.")
        elif store:
            print(f"{held} hold together, and match the ledger's locked copies, with the "
                  "entries either side of the period, so it's the whole period as the ledger "
                  "holds it" + ("." if bounds.get("until") else ", up to the ledger's head "
                                "as it was exported: export to a time, with --until, to have "
                                "its end checked too."))
        else:
            print(f"{held} hold together, which alone proves little: someone who changed an "
                  "entry could work out every hash after it again, and leave out the period's "
                  "last entries with what it says of its end. Set A5S_ANCHOR_STORE to check "
                  "them against the ledger's locked copies, which nobody can change.")
        return
    if not args.by:
        sys.exit("say who's reading it, with --by: an auditor, or assurance")
    # their own sign-in, from the identity provider, if they have one: the ledger records
    # the read as theirs; without it, as the service token's, naming them
    period = {"since": args.since, "until": args.until, "identity": os.environ.get("A5S_TOKEN")}
    if args.what == "entries":
        found = _core(cfg, lambda core: core.audit_entries(
            args.by, **period, after=args.after, limit=args.n, kind=args.kind,
            action=args.action, decision=args.decision, instance=args.instance,
            person=args.person))
        for entry in found["entries"]:
            print(json.dumps(entry, ensure_ascii=False))
        if found["next"]:
            print(f"More: --after {found['next']}", file=sys.stderr)
    elif args.what == "export":
        if not args.out:
            sys.exit("say where to write it, with --out")
        bounds, lines = _core(cfg, lambda core: core.audit_period(args.by, **period),
                              timeout=300)
        Path(args.out).write_text("".join(json.dumps(line) + "\n"
                                          for line in [{"export": bounds}, *lines]))
        print(f"Wrote {len(lines)} entries to {args.out}"
              + (f", {lines[0]['seq']} to {lines[-1]['seq']}" if lines else "")
              + f". Check it with: a5s audit verify {args.out}")
    else:
        report = _core(cfg, lambda core: core.audit_report(args.by, **period))
        print("Who holds each role:")
        for row in report["roles"]:
            print(f"  {row['role']}: {', '.join(row['held_by']) or 'nobody'}")
        print("What was done:" if report["acts"] else "Nothing was done in the period.")
        for act in report["acts"]:
            by = act["by"] if isinstance(act["by"], str) else ", ".join(act["by"] or [])
            print(f"  {act['at']}: {by or 'a5s'} {act['what']}"
                  + (f", in {act['instance']}" if act["instance"] else ""))


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
        current = releases.running(cfg.root, cfg.scenario_dir, cfg.agents_dir)
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


def _core(cfg: Config, call, timeout: float = 30):
    """A call to the core's API, through its client (a5s/client.py), or the reason it's refused."""
    with Client(cfg.gateway_url, cfg.service_token, timeout=timeout) as core:
        try:
            return call(core)
        except Refused as exc:
            sys.exit(f"{exc.status}: {exc.text or exc.detail}" if exc.status else str(exc.detail))


def _admin(cfg: Config, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    return _core(cfg, lambda core: core.post(path, body) if body is not None else core.get(path),
                 timeout)


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
    kept = sub.add_parser("summaries", help="read the summaries a5s keeps of a person's "
                                            "conversation with an agent")
    kept.add_argument("--as", dest="person", required=True)
    kept.add_argument("agent", nargs="?", default="assistant")
    box = sub.add_parser("inbox", help="read what's been written to a person, such as reminders")
    box.add_argument("--as", dest="person", required=True)
    box.add_argument("--wait", type=float, default=0, metavar="SECONDS")
    for verb in ("suspend", "resume"):
        p = sub.add_parser(verb, help=f"{verb} an instance")
        p.add_argument("instance")
        p.add_argument("--by", help="who you are, in development; else your sign-in in A5S_TOKEN")
    exported = sub.add_parser("export", help="all a5s keeps about someone, for their request "
                                             "to see it, once the data protection officer has "
                                             "asked for it on the core's page, /officer/")
    exported.add_argument("--person", required=True, help="their id in the directory, or an "
                                                           "archive's name")
    exported.add_argument("--by", help="in development, the officer, who asks nowhere else")
    exported.add_argument("--out", type=Path, help="write it to this file, which only you may "
                                                   "read, rather than print it")
    erased = sub.add_parser("erase", help="erase all a5s keeps about someone, at their "
                                          "request, once the data protection officer has asked "
                                          "for it on the core's page, /officer/")
    erased.add_argument("--person", required=True, help="their id in the directory, or an "
                                                         "archive's name")
    erased.add_argument("--confirm", required=True, help="the same again, so that a mistyped "
                                                          "id erases nobody")
    erased.add_argument("--by", help="in development, the officer, who asks nowhere else")
    sub.add_parser("status", help="how a5s is doing: its queue, runs, denials, budgets and "
                                  "objectives")
    measured = sub.add_parser("measures", help="the measures its first users baseline, and the "
                                               "pilot's later stages show: what fell due and "
                                               "was met, who came back, what runs cost, how "
                                               "held changes were decided, and notes")
    measured.add_argument("--days", type=int, default=30, help="over the last so many days")
    scope = measured.add_mutually_exclusive_group()
    scope.add_argument("--agent", help="of one agent's instances alone")
    scope.add_argument("--instance", help="of one instance alone")
    agents = sub.add_parser("agents", help="the agents of the release, and where each runs; or "
                                           "show one, with its tools and instructions")
    agents.add_argument("what", nargs="?", choices=["show"], help="show one agent")
    agents.add_argument("agent", nargs="?", help="with show, the agent, such as assistant")
    ran = sub.add_parser("runs", help="an instance's runs, newest first; or show what one run "
                                      "did")
    ran.add_argument("instance", help="the instance, such as assistant-finance; or show")
    ran.add_argument("run", nargs="?", help="with show, the run")
    ran.add_argument("--before", help="runs opened before this time, for the next page")
    ran.add_argument("-n", type=int, default=studio.RUNS, help="how many")
    held = sub.add_parser("proposals", help="the held changes that wait, or that a5s stopped "
                                            "part way through making; or end one of those")
    held.add_argument("end", nargs="?", choices=["end"], help="end a change a5s stopped making")
    held.add_argument("key", nargs="?", help="the change, such as P-12")
    held.add_argument("--by", help="who you are, in development; else your sign-in in A5S_TOKEN")
    caps = sub.add_parser("caps", help="lower an agent's cap for a type of action in a part")
    caps.add_argument("what", choices=["lower"])
    caps.add_argument("agent")
    caps.add_argument("part")
    caps.add_argument("action")
    caps.add_argument("--by", help="who you are, in development; else your sign-in in A5S_TOKEN")
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
    aud = sub.add_parser("audit", help="the audit trail, for an auditor or assurance: find a "
                                       "period's entries, export one, check an export, or "
                                       "report who holds each role and who did what")
    aud.add_argument("what", choices=["entries", "export", "verify", "report"])
    aud.add_argument("file", nargs="?", help="with verify, the export to check")
    aud.add_argument("--by", help="the auditor, or assurance, reading it: in the directory")
    aud.add_argument("--since", type=datetime.fromisoformat, help="from this time, such as "
                                                                  "2026-11-01, in UTC unless said")
    aud.add_argument("--until", type=datetime.fromisoformat, help="up to this time")
    for name in ("kind", "action", "decision", "instance", "person"):
        aud.add_argument(f"--{name}", help=f"with entries, of this {name} alone")
    aud.add_argument("--after", type=int, default=0, help="with entries, the page after this one")
    aud.add_argument("-n", type=int, default=50, help="with entries, how many")
    aud.add_argument("--out", help="with export, the file to write")
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

        # An idle connection stays open longer than any client of a5s's keeps one, httpx's 5
        # seconds, so no client sends a call down one the server is just closing, which fails
        # it after it left, and so isn't tried again (reach.py)
        uvicorn.run(_service(cfg, args.command), host=args.host, port=args.port,
                    timeout_keep_alive=KEEP_ALIVE)
    elif args.command == "scheduler":
        _scheduler(cfg)
    elif args.command == "dev":
        _dev(cfg)
    elif args.command == "say":
        _say(cfg, args.person, args.agent, args.text)
    elif args.command == "inbox":
        _inbox(cfg, args.person, args.wait)
    elif args.command == "summaries":
        _summaries(cfg, args.person, args.agent)
    elif args.command in ("suspend", "resume"):
        print(_admin(cfg, f"/instances/{args.instance}/{args.command}",
                     {"by": args.by, "identity": os.environ.get("A5S_TOKEN")}))
    elif args.command == "export":
        found = _admin(cfg, f"/people/{quote(args.person, safe='')}/export",  # as the officer
                       {"by": args.by}, timeout=300)  # asked: it counts across the whole ledger
        text = json.dumps(found, indent=2, ensure_ascii=False) + "\n"
        if args.out is None:
            print(text, end="")
        else:  # someone's data: a new file, for the officer's eyes, never one already there
            try:
                made = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                sys.exit(f"{args.out} is there already: name a new file, which only you may read")
            try:
                _officer_only(args.out)
            except BaseException:
                os.close(made)
                os.unlink(args.out)
                raise
            with os.fdopen(made, "w") as out:
                out.write(text)
            print(f"Wrote all a5s keeps about {args.person} to {args.out}.")
        for archive in found["archives"]:  # one holder at a time
            print(f"Whoever held {args.person} until {archive['archived_at'][:10]}, maybe "
                  "someone else, left then, and what a5s kept for them is archived as "
                  f"{archive['name']}: if it's theirs, export it with --person {archive['name']}.",
                  file=sys.stderr)
    elif args.command == "erase":
        done = _admin(cfg, f"/people/{quote(args.person, safe='')}/erase",
                      {"by": args.by, "confirm": args.confirm}, timeout=300)
        print(f"Erased what a5s kept about {args.person}: " + ("; ".join(
            f"{erasure.WORDS.get(kind, kind)}, {n}" for kind, n in sorted(done["gone"].items()))
            or "it kept nothing") + ". The ledger, runs, the changes asked for them and what they "
            "owe while the records owe it stay, as evidence of what agents did.")
        for name in done.get("archives", []):  # one holder at a time
            print(f"The archive {name} stays: it's what a5s kept under {args.person} for "
                  "whoever held the id before, maybe someone else. If it's theirs, erase it "
                  f"with --person {name} --confirm {name}.", file=sys.stderr)
    elif args.command == "anchor":
        _anchor(cfg, args.every)
    elif args.command == "status":
        print(status.told(_admin(cfg, "/status")))
    elif args.command == "measures":
        print(measures.told(_core(cfg, lambda core: core.measures(
            args.days, agent=args.agent, instance=args.instance))))
    elif args.command == "agents" and args.what:
        if not args.agent:
            sys.exit("name the agent to show, such as assistant")
        print(studio.told_agent(_core(cfg, lambda core: core.agent(args.agent))))
    elif args.command == "agents":
        print(studio.told_agents(_core(cfg, lambda core: core.agents())))
    elif args.command == "runs" and args.instance == "show":
        if not args.run:
            sys.exit("name the run to show")
        print(studio.told_run(_core(cfg, lambda core: core.run(args.run))))
    elif args.command == "runs":
        print(studio.told_runs(_core(cfg, lambda core: core.runs(
            args.instance, before=args.before, limit=args.n))))
    elif args.command == "proposals" and args.end:
        if not args.key:
            sys.exit("name the change to end, such as P-12")
        print(_admin(cfg, f"/proposals/{args.key}/end",
                     {"by": args.by, "identity": os.environ.get("A5S_TOKEN")}))
    elif args.command == "proposals":
        for p in _admin(cfg, "/proposals")["proposals"]:
            print(f"{p['key']} {p['status']} since {p['decided_at'] or p['proposed_at']}, "
                  f"for {', '.join(p['for']) or 'nobody'}: {p['change']}")
    elif args.command == "caps":
        print(_admin(cfg, "/caps/lower", {"agent": args.agent, "part": args.part,
                                          "action": args.action, "by": args.by,
                                          "identity": os.environ.get("A5S_TOKEN")}))
    elif args.command == "release":
        _release(cfg, args)
    elif args.command == "ledger" and args.what == "verify":
        _verify(cfg)
    elif args.command == "audit":
        _audit(cfg, args)
    elif args.command == "ledger":
        with db.transaction(cfg.database_url) as conn:
            for entry in ledger.entries(conn, limit=args.n):
                print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
