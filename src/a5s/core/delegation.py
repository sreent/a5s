"""Acting with someone's own permissions (docs/connectors.md#acting-as-the-person): a tool whose
MCP server acts as the person a run is for, such as one for ServiceNow, GitHub or Microsoft Graph
through Entra ID, calls their system with their own access, never a5s's, so the system's own rules
decide what they may see and change there, as they would for them.

- The deployment names each system people may connect (A5S_DELEGATION): its OAuth endpoints,
  a5s's client there and the scopes a5s asks for. a5s's client secret there is for the core
  alone, in A5S_DELEGATION_<NAME>_SECRET.
- Someone connects their account on their own page in the studio: the system asks them, as itself,
  whether a5s may act for them with those scopes, and sends them back with a code, which the core
  exchanges for their tokens within a minute, with PKCE, so a code is no use to anyone else. With
  Entra ID, that's its authorization code flow, with offline access for the API's delegated
  permissions: chats pass a5s no token of the person's to exchange on their behalf, so a5s asks
  for their consent once instead.
- The core keeps their tokens sealed, with AES-GCM under a key it derives from its own seal keys,
  which the channels app hasn't, bound to the person and the system, and gets a fresh access
  token with them when one of their runs calls such a tool: only for a run acting for that one
  person, once they've connected. a5s's policy, levels and need-to-know decide first, as for any
  tool, and then the system's own rules, so an agent may do the narrower of the two.
- Someone disconnects on the same page, and a5s forgets their tokens. They go too when the system
  stops taking them, after 90 days unused, when someone leaves, or asks a5s to erase what it keeps
  of them; their export says which systems they connected, never a token. The ledger records each
  connection and its end, never a token.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import json
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from a5s import config, db
from a5s.contract import Person
from a5s.core import ledger

NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
WHOSE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}(\.[A-Za-z_][A-Za-z0-9_]{0,63}){0,3}")  # a field
WITHIN = timedelta(minutes=15)  # to come back with a code, from starting to connect [starting value]
UNUSED = timedelta(days=90)  # tokens unused this long are forgotten [starting value]
EARLY = timedelta(seconds=60)  # an access token is renewed this long before it lapses
TIMEOUT = 20.0  # seconds a system's token endpoint has to answer
INFO = b"a5s delegated tokens v1"
BACK = "/studio/connections"  # where each system sends people back, on the channels' address


class Refused(ValueError):
    """Why someone can't connect, or a run can't act as them, in words."""


class NotConnected(Refused):
    """They haven't connected their account in that system, or it no longer takes their tokens."""


def _address(url: str, what: str) -> str:
    """A system's endpoint, as a5s may use it: HTTPS, or HTTP on this machine alone."""
    parsed = urlsplit(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username \
            or parsed.fragment or (parsed.scheme == "http" and not local):
        raise config.ConfigError(f"A5S_DELEGATION's {what} {url!r} isn't an HTTPS address")
    return url


@dataclass(frozen=True)
class System:
    """A system people may connect, so a5s acts there with their own permissions."""

    name: str
    authorize: str  # where they're asked, in their browser
    token: str  # where the core exchanges a code and renews tokens
    client_id: str
    scopes: tuple[str, ...] = ()
    title: str = ""  # its name, as people know it, such as ServiceNow
    secret: str | None = field(default=None, repr=False)  # the core's alone
    whoami: str = ""  # where the core asks, with a new token, whose account it is
    whose: str = ""  # the field of that answer naming the account, such as id or result.user_name
    known_as: str = ""  # the directory's identities it is, such as entra; none: the a5s id


@dataclass(frozen=True)
class Delegation:
    systems: tuple[System, ...]

    @classmethod
    def from_env(cls, secrets_too: bool = False,
                 env: dict[str, str] | None = None) -> Delegation | None:
        """Each system from A5S_DELEGATION, a JSON list of {name, authorize, token, client_id,
        scopes, title, whoami, whose, known_as}, with a5s's client secret there from
        A5S_DELEGATION_<NAME>_SECRET where `secrets_too`, as the core reads it; None where nobody
        may connect anything. Each says where the core asks whose account a token is, and how
        the directory knows that account, since the core keeps a token only for its own."""
        source = os.environ if env is None else env
        listed = config.DELEGATION.read(source)
        if not listed:
            return None
        found = []
        for s in listed:
            if not isinstance(s, dict) or not NAME.fullmatch(str(s.get("name", ""))):
                raise config.ConfigError("A5S_DELEGATION names each system in lowercase, such as "
                                         "servicenow")
            name = str(s["name"])
            secret = source.get(f"A5S_DELEGATION_{name.upper().replace('-', '_')}_SECRET")
            authorize = _address(str(s.get("authorize", "")), "authorize")
            token = _address(str(s.get("token", "")), "token")
            whose = str(s.get("whose") or "")
            if not WHOSE.fullmatch(whose):
                raise config.ConfigError(
                    f"A5S_DELEGATION's {name} says where a5s asks whose account a token is "
                    "(whoami) and the field of its answer that names it (whose), such as id: "
                    "a5s keeps someone's token only for an account the system says is theirs")
            known_as = str(s.get("known_as") or "")
            if known_as and not NAME.fullmatch(known_as):
                raise config.ConfigError(f"A5S_DELEGATION's {name} names the directory's "
                                         "identities it is in lowercase, such as entra")
            found.append(System(name=name, authorize=authorize, token=token,
                                client_id=str(s.get("client_id") or ""),
                                scopes=tuple(str(x) for x in s.get("scopes") or ()),
                                title=str(s.get("title") or name),
                                secret=secret if secrets_too else None,
                                whoami=_address(str(s.get("whoami", "")), "whoami"),
                                whose=whose, known_as=known_as))
        return cls(systems=tuple(found))

    def system(self, name: str) -> System | None:
        return next((s for s in self.systems if s.name == name), None)


# Their tokens, sealed by the core

def _keys(seal_keys: tuple[str, ...]) -> list[bytes]:
    return [HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(k.encode())
            for k in seal_keys]


def seal(seal_keys: tuple[str, ...], person: str, system: str, tokens: dict) -> bytes:
    """Someone's tokens in a system, sealed under the core's first key, bound to them both."""
    if not seal_keys:
        raise Refused("the core holds no seal key, so it can't keep anyone's tokens")
    nonce = secrets.token_bytes(12)
    bound = f"{person}\x00{system}".encode()
    return nonce + AESGCM(_keys(seal_keys)[0]).encrypt(nonce, json.dumps(tokens).encode(), bound)


def unseal(seal_keys: tuple[str, ...], person: str, system: str, sealed: bytes) -> dict:
    """Someone's tokens, as sealed for them in that system, under any of the core's keys."""
    bound, nonce = f"{person}\x00{system}".encode(), bytes(sealed[:12])
    for key in _keys(seal_keys):
        with contextlib.suppress(InvalidTag):  # another key's, or not theirs
            return json.loads(AESGCM(key).decrypt(nonce, bytes(sealed[12:]), bound))
    raise NotConnected(f"a5s can't read what it kept for {person} in {system}: connect it again")


# Connecting, in the channels app, then the core

def challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def start(conn: db.Connection, cfg: Delegation, person: str, system: str, back: str) -> str:
    """Begin connecting someone's account: where to send them, to say a5s may act for them."""
    found = cfg.system(system)
    if found is None:
        raise Refused(f"a5s connects no {system} here")
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    conn.execute("delete from delegation_starts where person = %s and system = %s", (person, system))
    conn.execute("insert into delegation_starts (state, person, system, verifier) "
                 "values (%s, %s, %s, %s)", (state, person, system, verifier))
    query = {"response_type": "code", "client_id": found.client_id, "redirect_uri": back,
             "state": state, "code_challenge": challenge(verifier), "code_challenge_method": "S256"}
    if found.scopes:
        query["scope"] = " ".join(found.scopes)
    return f"{found.authorize}{'&' if '?' in found.authorize else '?'}{urlencode(query)}"


def came_back(conn: db.Connection, cfg: Delegation, person: str, state: str,
              code: str | None) -> System:
    """The system someone came back from, with the code it sent them back with, for the core
    to exchange: theirs alone, while their start is fresh. Without a code, they said no there,
    and the start goes."""
    row = conn.execute("select person, system from delegation_starts where state = %s "
                       "and started_at > now() - %s and code is null for update",
                       (state[:200], WITHIN)).fetchone()
    found = cfg.system(row["system"]) if row is not None else None
    if row is None or row["person"] != person or found is None:
        raise Refused("that isn't your way back from connecting an account, or it took too long: "
                      "connect it again on your own page")
    if code:
        conn.execute("update delegation_starts set code = %s, coded_at = now() where state = %s",
                     (code[:2048], state))
    else:
        conn.execute("delete from delegation_starts where state = %s", (state,))
    return found


def _post(system: System, form: dict[str, str], http: httpx.Client) -> dict:
    """What a system's token endpoint answers, as JSON, or Refused, saying why."""
    try:
        answer = http.post(system.token, data={**form, "client_id": system.client_id,
                                               "client_secret": system.secret or ""},
                           headers={"Accept": "application/json"}, timeout=TIMEOUT,
                           follow_redirects=False)
    except httpx.HTTPError as e:
        raise Refused(f"{system.title} couldn't be reached: {type(e).__name__}") from None
    try:
        body = answer.json()
    except ValueError:
        body = {}
    if answer.status_code >= 400 or not isinstance(body, dict) or "access_token" not in body:
        said = body.get("error") if isinstance(body, dict) else None
        raise (NotConnected if said == "invalid_grant" else Refused)(
            f"{system.title} didn't give a5s a token: {str(said or answer.status_code)[:60]}")
    return body


def _account(system: System, access: str, http: httpx.Client) -> str:
    """Whose account a token is, as the system says it: the field `whose` names, of what it
    answers at `whoami` with the token. Refused, saying why, if it says none."""
    try:
        answer = http.get(system.whoami, headers={"Authorization": f"Bearer {access}",
                                                  "Accept": "application/json"},
                          timeout=TIMEOUT, follow_redirects=False)
        found: Any = answer.json() if answer.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        found = None
    for key in system.whose.split("."):
        found = found.get(key) if isinstance(found, dict) else None
    if not isinstance(found, str | int) or isinstance(found, bool) or not str(found).strip():
        raise Refused(f"{system.title} didn't say whose account it is, so a5s keeps nothing")
    return str(found).strip()


def theirs(system: System, account: str, person: Person | None) -> bool:
    """Whether an account in a system is someone's, as the directory knows them: their
    identity of the kind the system says, or where it says none, their a5s id."""
    if person is None:
        return False
    if not system.known_as:
        return account.casefold() == person.id.casefold()
    return f"{system.known_as}:{account}".casefold() in {i.casefold() for i in person.identities}


def _kept(body: dict, before: dict | None) -> tuple[dict, timedelta | None]:
    """What to keep of a token endpoint's answer: the access token, the refresh token, the one
    before if it sent no new one, and how long until the access token lapses."""
    given = body.get("expires_in")
    lapses = timedelta(seconds=int(given)) if isinstance(given, int | float) \
        and not isinstance(given, bool) and 0 <= given < 10 ** 8 else None
    return ({"access": str(body["access_token"]),
             "refresh": str(body.get("refresh_token") or (before or {}).get("refresh") or ""),
             "scope": str(body.get("scope") or (before or {}).get("scope") or "")}, lapses)


def sweep(conn: db.Connection, cfg: Delegation | None, seal_keys: tuple[str, ...], back: str,
          http: httpx.Client, person: Callable[[str], Person | None]) -> dict[str, int]:
    """The core exchanges each code people came back with for their tokens, keeping them
    sealed only once the system says whose account they are and the directory, `person`, says
    that's who came back with it: whatever the part people reach recorded, a5s acts as nobody
    in an account that isn't theirs. It lets go of starts nobody came back to. How many
    connected, and failed: by the database's clock, as retention goes."""
    done = {"connected": 0, "failed": 0}
    conn.execute("delete from delegation_starts where code is null and started_at < now() - %s",
                 (WITHIN,))
    for row in conn.execute("select * from delegation_starts where code is not null "
                            "order by coded_at for update skip locked").fetchall():
        conn.execute("delete from delegation_starts where state = %s", (row["state"],))
        system = cfg.system(row["system"]) if cfg else None
        try:
            if system is None:
                raise Refused(f"a5s connects no {row['system']} here")
            body = _post(system, {"grant_type": "authorization_code", "code": row["code"],
                                  "redirect_uri": back, "code_verifier": row["verifier"]}, http)
            tokens, lapses = _kept(body, None)
            if not theirs(system, _account(system, tokens["access"], http), person(row["person"])):
                raise Refused(f"{system.title} says that account isn't theirs, as the directory "
                              "knows them, so a5s keeps nothing")
            conn.execute(
                "insert into delegations (person, system, sealed, scopes, expires_at) "
                "values (%s, %s, %s, %s, now() + %s) on conflict (person, system) do update set "
                "sealed = excluded.sealed, scopes = excluded.scopes, expires_at = excluded.expires_at, "
                "connected_at = now(), used_at = null",
                (row["person"], row["system"], seal(seal_keys, row["person"], row["system"], tokens),
                 tokens["scope"].split() or list(system.scopes), lapses))
            done["connected"] += 1
            ledger.append(conn, {"kind": "admin", "action": "connect", "run": None, "instance": None,
                                 "acts_for": [row["person"]], "decision": "record",
                                 "args": {"system": row["system"]}})
        except Refused as e:
            done["failed"] += 1
            ledger.append(conn, {"kind": "admin", "action": "connect", "run": None, "instance": None,
                                 "acts_for": [row["person"]], "decision": "record",
                                 "args": {"system": row["system"]},
                                 "outcome": {"status": "error", "error": str(e)[:200]}})
    return done


def access(url: str, cfg: Delegation | None, seal_keys: tuple[str, ...], person: str,
           system: str, http: httpx.Client) -> str:
    """An access token for acting as someone in a system: theirs, renewed with their refresh
    token if it's about to lapse. NotConnected, saying how to connect, if they haven't, or the
    system no longer takes it, which forgets it."""
    found = cfg.system(system) if cfg else None
    if found is None:
        raise Refused(f"this deployment doesn't act as people in {system}")
    with db.transaction(url) as conn:
        row = conn.execute("select sealed, expires_at is null or expires_at > now() + %s as fresh "
                           "from delegations where person = %s and system = %s for update",
                           (EARLY, person, system)).fetchone()
        if row is None:
            raise NotConnected(f"{person} hasn't connected their {found.title} account, so a5s "
                               "can't act as them there: they connect it on their own page in "
                               "the studio")
        tokens = unseal(seal_keys, person, system, bytes(row["sealed"]))
        if row["fresh"]:
            conn.execute("update delegations set used_at = now() where person = %s and system = %s",
                         (person, system))
            return str(tokens["access"])
        try:
            if not tokens.get("refresh"):
                raise NotConnected(f"{found.title} gave a5s no way to renew {person}'s access")
            body = _post(found, {"grant_type": "refresh_token", "refresh_token": tokens["refresh"],
                                 **({"scope": " ".join(found.scopes)} if found.scopes else {})}, http)
        except NotConnected as e:
            refused = e  # forgotten below, once this transaction ends as it should
        else:
            renewed, lapses = _kept(body, tokens)
            conn.execute("update delegations set sealed = %s, expires_at = now() + %s, "
                         "used_at = now() where person = %s and system = %s",
                         (seal(seal_keys, person, system, renewed), lapses, person, system))
            return renewed["access"]
    with db.transaction(url) as conn:
        forget(conn, person, system, f"{found.title} no longer takes it")
    raise NotConnected(f"{refused}: {person} connects their {found.title} account again on their "
                       "own page in the studio")


def forget(conn: db.Connection, person: str, system: str, why: str) -> bool:
    """Forget someone's tokens in a system, with the ledger's word on it: whether there were any."""
    gone = conn.execute("delete from delegations where person = %s and system = %s returning 1",
                        (person, system)).fetchone() is not None
    conn.execute("delete from delegation_starts where person = %s and system = %s", (person, system))
    if gone:
        ledger.append(conn, {"kind": "admin", "action": "disconnect", "run": None, "instance": None,
                             "acts_for": [person], "decision": "record",
                             "args": {"system": system, "why": why}})
    return gone


def connections(conn: db.Connection, cfg: Delegation | None, person: str) -> list[dict]:
    """Each system someone may connect, and whether they have: since when, with which scopes,
    when a5s last acted as them there, or whether it's on its way."""
    if cfg is None:
        return []
    kept = {r["system"]: r for r in conn.execute(
        "select system, scopes, connected_at, used_at from delegations where person = %s", (person,))}
    coming = {r["system"] for r in conn.execute(
        "select system from delegation_starts where person = %s and code is not null", (person,))}
    return [{"system": s.name, "title": s.title,
             "connected": s.name in kept, "connecting": s.name in coming and s.name not in kept,
             "scopes": list(kept[s.name]["scopes"]) if s.name in kept else list(s.scopes),
             "connected_at": kept[s.name]["connected_at"].isoformat() if s.name in kept else None,
             "used_at": kept[s.name]["used_at"].isoformat()
             if s.name in kept and kept[s.name]["used_at"] else None}
            for s in cfg.systems]


Supplier = Callable[[str, str], str]  # (person, system) to their access token there


@functools.cache
def client() -> httpx.Client:
    """The core's client for the systems' token endpoints: theirs alone, following no redirect."""
    return httpx.Client(timeout=TIMEOUT, follow_redirects=False)


def supplier(url: str, seal_keys: tuple[str, ...], cfg: Delegation | None,
             http: httpx.Client | None = None) -> Supplier:
    """What an MCP server that acts as the person asks for their token with, in the core."""

    def token(person: str, system: str) -> str:
        return access(url, cfg, seal_keys, person, system, http or client())

    return token
