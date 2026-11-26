"""Whether a5s will reach what it needs from where it will run, before it's installed.

Run it there, such as in a pod in the namespace a5s will run in, which egress rules and proxies
treat as they will treat a5s, with the addresses the deployment will use. It needs Python 3.10
or later, and nothing else, so any Python image runs it:

    kubectl -n a5s run reach-check --rm -i --restart=Never --image=python:3.12-slim -- \\
      python - --postgres db.internal:5432 \\
               --issuer https://login.microsoftonline.com/<tenant>/v2.0 \\
               --https https://api.deepseek.com --teams < deploy/reach-check.py

Each line says ok or fix, what it tried, and what it found, and it exits 1 if anything can't be
reached. It sends each nothing but a connection, or a GET with no credentials, so it needs no
secret. --plan says what it would try, and tries nothing (docs/first-day.md#before-the-day)."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request

WAIT = 10  # seconds for each to answer

# What each chat needs a5s to reach, as a5s's own adapters call them (a5s/core/teams.py, slack.py)
TEAMS = ("https://login.botframework.com/v1/.well-known/openidconfiguration",  # checks its tokens
         "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",  # a5s's
         "https://smba.trafficmanager.net/")  # where Teams takes replies
SLACK = ("https://slack.com/api/api.test", "https://files.slack.com/")


def planned(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    """What to try, in order: what for, the kind of check, and its target."""
    found = [("Postgres", "postgres", target) for target in args.postgres]
    found += [("Signing in", "issuer", issuer.strip()) for issuer in args.issuer]
    found += [("Outside", "https", url) for url in args.https]
    found += [("Teams", "https", url) for url in (TEAMS if args.teams else ())]
    found += [("Slack", "https", url) for url in (SLACK if args.slack else ())]
    found += [("Matrix", "https", homeserver.rstrip("/") + "/_matrix/client/versions")
              for homeserver in args.matrix]
    return found


def postgres(target: str) -> tuple[bool, str]:
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit():
        return False, f"{target} isn't a host and its port, such as db.internal:5432"
    try:
        with socket.create_connection((host, int(port)), timeout=WAIT):
            return True, f"Postgres at {target} takes connections"
    except socket.gaierror:
        return False, f"{host} isn't a name this network knows: check the address, and the DNS here"
    except OSError as exc:
        return False, (f"nothing takes connections at {target} ({exc.strerror or exc}): check "
                       "the address, and that rules here let this namespace reach it")


def fetched(url: str) -> tuple[int, bytes]:
    """The status and body of a GET, with no credentials: any status at all is an answer."""
    request = urllib.request.Request(url, headers={"User-Agent": "a5s-reach-check"})
    try:
        with urllib.request.urlopen(request, timeout=WAIT) as answer:  # the addresses given
            return answer.status, answer.read(1_000_000)
    except urllib.error.HTTPError as exc:  # answered, if not with what a5s would send
        return exc.code, exc.read(1_000_000)


def why(exc: Exception) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (f"its certificate isn't one this system trusts ({reason.verify_message}): a proxy "
                "that opens TLS needs its own certificate trusted, such as by SSL_CERT_FILE")
    if isinstance(reason, socket.gaierror):
        return "its host isn't a name this network knows: check the address, and the DNS here"
    if isinstance(reason, TimeoutError):
        return f"it didn't answer within {WAIT} seconds: a firewall may drop what goes there"
    return f"it can't be reached ({reason}): check that rules here, or a proxy, let it through"


def https(url: str) -> tuple[bool, str]:
    try:
        status, _ = fetched(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"{url}: {why(exc)}"
    return True, f"{url} answers ({status})"


def issuer(given: str) -> tuple[bool, str]:
    """An identity provider: its discovery document, the issuer it names, exactly as a5s takes
    it, and its keys, which a5s checks sign-ins with."""
    discovery = given.rstrip("/") + "/.well-known/openid-configuration"
    try:
        status, body = fetched(discovery)
        found = json.loads(body) if status == 200 else None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"{discovery}: {why(exc)}"
    if not isinstance(found, dict):
        return False, (f"{discovery} answers {status}, not with a discovery document: check "
                       "the issuer, as the provider gives it")
    if found.get("issuer") != given:
        return False, (f"the provider names its issuer {found.get('issuer')!r}, and you gave "
                       f"{given!r}: set people.oidcIssuer to its own, to the last slash")
    keys = str(found.get("jwks_uri") or "")
    ok, said = https(keys) if keys else (False, "it names no jwks_uri")
    if not ok:
        return False, f"its keys, which a5s checks sign-ins with: {said}"
    return True, f"the identity provider at {given} answers, and its keys at {keys} do"


CHECKS = {"postgres": postgres, "issuer": issuer, "https": https}


def main(argv: list[str] | None = None) -> int:
    given = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    given.add_argument("--postgres", action="append", default=[], metavar="HOST:PORT",
                       help="the database a5s will use, as host:port")
    given.add_argument("--issuer", action="append", default=[], metavar="URL",
                       help="the identity provider's issuer, as people.oidcIssuer will have it")
    given.add_argument("--https", action="append", default=[], metavar="URL",
                       help="anything else a5s calls: each model provider's base_url, the "
                            "ledger's store's endpoint, an MCP server, a telemetry collector")
    given.add_argument("--matrix", action="append", default=[], metavar="URL",
                       help="the Matrix homeserver, as matrix.homeserver will have it")
    given.add_argument("--teams", action="store_true", help="what Teams needs a5s to reach")
    given.add_argument("--slack", action="store_true", help="what Slack needs a5s to reach")
    given.add_argument("--plan", action="store_true", help="say what it would try, and try nothing")
    args = given.parse_args(argv)
    plan = planned(args)
    if not plan:
        given.error("name something to reach, such as --postgres db.internal:5432")
    if args.plan:
        for name, _, target in plan:
            print(f"{name}: {target}")
        return 0
    failed = 0
    for name, kind, target in plan:
        ok, said = CHECKS[kind](target)
        failed += not ok
        print(f"{'ok ' if ok else 'fix'}  {name}: {said}.")
    print("Everything answered." if not failed else
          f"{failed} can't be reached from here: fix {'it' if failed == 1 else 'them'} before "
          "installing a5s.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
