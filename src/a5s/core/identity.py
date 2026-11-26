"""People's identity: tokens from the organisation's identity provider, checked in the core.

Any provider that speaks OpenID Connect works, because one check fits them all:
Entra ID, Google Cloud Identity and Okta, and as well Keycloak, Auth0, Ping,
OneLogin, JumpCloud, Authentik, Zitadel or Active Directory Federation Services
on the organisation's own network. A directory that speaks only LDAP or SAML,
such as Active Directory on its own, connects through a bridge that speaks
OpenID Connect, such as Keycloak or Dex. The gateway checks each message's
sender itself, so no service can claim that a message came from someone else.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from a5s import config

# Asymmetric algorithms only: a token signed with a shared secret, or with none, is refused.
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512",
               "EdDSA"]


class IdentityError(Exception):
    pass


def shown(value: Any) -> str:
    """A value from a token or the provider, as a refusal shows it: quoted, a list's items
    joined, and never so long that it buries what's wrong."""
    if isinstance(value, list):
        return ", ".join(shown(v) for v in value) or "nobody"
    if value is None or value == "":
        return "nothing"
    said = repr(str(value))
    return said if len(said) <= 120 else said[:117] + "...'"


class UnknownPerson(IdentityError):
    """The token checks out, but names nobody the directory knows."""


class IdentityUnavailable(IdentityError):
    """The identity provider couldn't be reached, or answered nothing a5s could read, so a5s
    couldn't check the token just now: neither that it checks out, nor that it doesn't."""


@dataclass(frozen=True)
class IdentityConfig:
    issuer: str
    audience: str | tuple[str, ...]  # a token for any of them is accepted
    # Which claim holds the person's id in the directory. Pick one people can't change:
    # sub, which OpenID Connect never lets a provider reassign, or Entra ID's oid.
    person_claim: str = "preferred_username"
    metadata_url: str | None = None  # if it isn't at the issuer's well-known address
    required: tuple[str, ...] = ("exp", "iat", "iss", "aud")
    leeway: int = 30  # seconds of clock skew
    # How the directory knows the claim: with "entra", an oid is found as entra:<oid>.
    # Without one, the claim is the person's id in the directory itself.
    directory_prefix: str | None = None
    # The claim a sign-in shows a second factor by, and the values that do, if the deployment
    # asks for one for what counts (A5S_OIDC_MFA): such as amr holding mfa, for Entra ID
    mfa: tuple[str, tuple[str, ...]] | None = None
    # Whether the deployment says its provider's tokens show no second factor (A5S_OIDC_MFA=none):
    # a5s asks none, as with none set, but the status and the doctor take it as said (round 17, A10)
    mfa_said_none: bool = False
    # The claim a sign-in shows its groups by, for the roles the settings give them
    # (A5S_OIDC_GROUPS_CLAIM, groups if not set, and none if set empty): core/memberships.py
    groups_claim: str | None = "groups"

    @property
    def second_factor_asked(self) -> tuple[str, tuple[str, ...]] | None:
        """The second factor what counts asks for, as the status says it: none, where the
        deployment says its provider's tokens show none, and None where nobody set it."""
        return config.NO_SECOND_FACTOR if self.mfa_said_none else self.mfa

    @classmethod
    def from_env(cls) -> IdentityConfig | None:
        if not (issuer := config.OIDC_ISSUER.read()):  # exactly as the provider writes it
            return None
        audiences = list(config.OIDC_AUDIENCE.read())
        if web := config.WEBCHAT_CLIENT_ID.read():  # its sign-ins come to the core too
            audiences.append(web)
        return cls(
            issuer=issuer,
            audience=tuple(dict.fromkeys(a for a in audiences if a)),
            person_claim=config.OIDC_PERSON_CLAIM.read(),
            metadata_url=config.OIDC_METADATA_URL.read(),
            directory_prefix=config.OIDC_DIRECTORY_PREFIX.read(),
            mfa=None if (mfa := config.OIDC_MFA.read()) == config.NO_SECOND_FACTOR else mfa,
            mfa_said_none=mfa == config.NO_SECOND_FACTOR,
            groups_claim=config.OIDC_GROUPS_CLAIM.read(),
        )


def second_factor_of(given: str | None) -> tuple[str, tuple[str, ...]] | None:
    """The claim and values `claim:value,value` names, such as amr:mfa, or acr:gold for a
    provider's step-up level: None for none. ValueError if it names no claim or no value."""
    if not given or not given.strip():
        return None
    try:
        found = config.second_factor(given)
        return None if found == config.NO_SECOND_FACTOR else found
    except ValueError:
        raise ValueError("A5S_OIDC_MFA names the claim a sign-in shows a second factor by, and "
                         "the values that do, such as amr:mfa") from None


def second_factor(cfg: IdentityConfig, claims: dict[str, Any]) -> bool:
    """Whether a sign-in shows the second factor the deployment asks for, if it asks for one:
    a claim such as amr, a list, holding one of its values, or one such as acr being one."""
    if cfg.mfa is None:
        return True
    claim, accepted = cfg.mfa
    shown = claims.get(claim)
    values = [shown] if isinstance(shown, str) else shown if isinstance(shown, list) else []
    return any(str(v) in accepted for v in values)


def without_second_factor(doing: str) -> str:
    """What a5s tells someone whose sign-in showed no second factor where the deployment asks
    for one: what to do, and whom to ask, since only their organisation's sign-in policy, never
    they, makes a sign-in show one. `doing` is what they meant to do, such as "approve"."""
    return (f"a5s needs you to sign in with your second factor to {doing}, as this deployment "
            "asks, and your sign-in showed none. If you weren't asked for one as you signed "
            "in, signing in again won't change that: your organisation's sign-in policy decides "
            "when it asks, so ask whoever runs sign-ins for your organisation, such as your IT "
            "team, to ask for a second factor when you sign in to a5s.")


def asked_claims(cfg: IdentityConfig) -> str | None:
    """The claims a page asks the identity provider for as someone signs in to do what counts,
    where the deployment's second factor is an authentication context, `acrs`, as Entra ID shows
    one: so Conditional Access asks them for what that context needs then, which `amr` in a
    v2.0 token may never show (round 13, D3). None where it's anything else."""
    if not cfg.mfa or cfg.mfa[0] != "acrs":
        return None
    values = list(cfg.mfa[1])
    wanted = {"essential": True, **({"value": values[0]} if len(values) == 1 else {"values": values})}
    return json.dumps({"id_token": {"acrs": wanted}}, separators=(",", ":"))


def asked_level(cfg: IdentityConfig) -> str | None:
    """The level a page asks the identity provider for as someone signs in to do what counts,
    as acr_values, where the deployment's second factor is a level (acr), so the provider asks
    them for it then. None where it's one amr shows, which only the provider's policy asks for."""
    return " ".join(cfg.mfa[1]) if cfg.mfa and cfg.mfa[0] == "acr" else None


class Verifier:
    """Checks tokens against the identity provider's published keys.

    It fetches the keys again after `max_age` seconds, so a key the provider withdraws
    stops working, and when a token names a key it doesn't know, which may be a
    rotation, but at most once every `min_refresh` seconds.
    """

    def __init__(self, cfg: IdentityConfig, http: httpx.Client | None = None, *,
                 max_age: float = 3600, min_refresh: float = 60):
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=10)
        self.max_age, self.min_refresh = max_age, min_refresh
        self._keys: PyJWKSet | None = None
        self._published: dict[str, dict] = {}  # each key as published, with any endorsements
        self._metadata: dict = {}  # where the provider signs people in and issues tokens
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> tuple[PyJWKSet, dict[str, dict]]:
        url = self.cfg.metadata_url or f"{self.cfg.issuer.rstrip('/')}/.well-known/openid-configuration"
        discovery = self.http.get(url)
        discovery.raise_for_status()
        if (named := discovery.json().get("issuer")) != self.cfg.issuer:
            raise IdentityError(f"the identity provider at {url} names its issuer {shown(named)}, "
                                f"and A5S_OIDC_ISSUER is {shown(self.cfg.issuer)}: set "
                                "A5S_OIDC_ISSUER to exactly the provider's, to the last slash")
        self._metadata = discovery.json()
        keys = self.http.get(discovery.json()["jwks_uri"])
        keys.raise_for_status()
        published = {k["kid"]: k for k in keys.json().get("keys", []) if isinstance(k, dict) and "kid" in k}
        return PyJWKSet.from_dict(keys.json()), published

    def _keyset(self, *, refresh: bool) -> PyJWKSet:
        age = time.monotonic() - self._fetched_at
        if self._keys is None or age > self.max_age or (refresh and age >= self.min_refresh):
            try:
                fetched = self._fetch()
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                where = self.cfg.metadata_url or self.cfg.issuer
                raise IdentityUnavailable(
                    f"the identity provider at {where} couldn't be reached, or answered nothing "
                    f"a5s could read ({type(exc).__name__}): check that the core reaches it, and "
                    "that A5S_OIDC_ISSUER, or A5S_OIDC_METADATA_URL where its metadata is "
                    "elsewhere, names it") from exc
            (self._keys, self._published), self._fetched_at = fetched, time.monotonic()
        return self._keys

    def _key(self, kid: str | None) -> tuple[PyJWK, dict]:
        with self._lock:
            for refresh in (False, True):  # a key it doesn't know yet may be a rotation
                try:
                    return self._keyset(refresh=refresh)[kid], self._published.get(kid or "", {})
                except KeyError:
                    continue
        raise IdentityError("it's signed with a key the identity provider doesn't list")

    def claims(self, token: str, *, endorsed_for: str | None = None,
               expired: bool = False) -> dict:
        """The token's claims, if it checks out. Otherwise, IdentityError.

        With `endorsed_for`, the key that signed it must also be endorsed for that
        channel, as the Bot Framework's keys are. With `expired`, a token past its expiry
        still checks out, for checking again a sign-in the core recorded when it was fresh.
        """
        try:
            key, published = self._key(jwt.get_unverified_header(token).get("kid"))
            if key.algorithm_name not in _ALGORITHMS:
                raise IdentityError(f"its key is for {key.algorithm_name}, which a5s doesn't accept")
            if endorsed_for is not None and endorsed_for not in published.get("endorsements", []):
                raise IdentityError(f"its key isn't endorsed for {endorsed_for}")
            return jwt.decode(
                token, key.key, algorithms=[key.algorithm_name], audience=self.cfg.audience,
                issuer=self.cfg.issuer, leeway=self.cfg.leeway,
                options={"require": list(self.cfg.required), "verify_exp": not expired},
            )
        except IdentityError:
            raise
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
            raise IdentityError(self.why(token, exc)) from exc

    def why(self, token: str, exc: Exception) -> str:
        """Why a token doesn't check out, in words that name what it says against what a5s
        takes, and the setting that decides it, where PyJWT's own words name neither."""
        try:
            said = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            said = {}
        if isinstance(exc, jwt.InvalidIssuerError):
            return (f"it's from the issuer {shown(said.get('iss'))}, and a5s takes sign-ins from "
                    f"{shown(self.cfg.issuer)}, as A5S_OIDC_ISSUER sets it: set that to exactly "
                    "what the provider's tokens name")
        if isinstance(exc, jwt.InvalidAudienceError):
            ours = [self.cfg.audience] if isinstance(self.cfg.audience, str) else self.cfg.audience
            return (f"it's for {shown(said.get('aud'))}, and a5s takes tokens for "
                    f"{', '.join(map(shown, ours)) or 'none'}: A5S_OIDC_AUDIENCE, with "
                    "A5S_WEBCHAT_CLIENT_ID, names the client ids a5s takes tokens for")
        if isinstance(exc, jwt.ExpiredSignatureError):
            return "it has expired: sign in again"
        if isinstance(exc, jwt.ImmatureSignatureError):
            return (f"it isn't valid yet, by more than the {self.cfg.leeway} seconds a5s allows: "
                    "the clocks of the identity provider and of the machine a5s runs on "
                    "disagree, so set both by a time server")
        if isinstance(exc, jwt.MissingRequiredClaimError):
            return f"it has no {exc.claim} claim, which a5s needs in every sign-in"
        return str(exc) or type(exc).__name__

    def endpoints(self) -> dict:
        """Where people sign in, and where codes become tokens, from the provider's metadata."""
        with self._lock:
            self._keyset(refresh=False)
            return {k: self._metadata[k] for k in ("authorization_endpoint", "token_endpoint",
                                                    "end_session_endpoint") if k in self._metadata}

    def person(self, token: str) -> str:
        """Who the token is for, if it checks out. Otherwise, IdentityError."""
        return self.named(self.claims(token))

    def named(self, claims: dict) -> str:
        """Who a checked token's claims are for."""
        person = claims.get(self.cfg.person_claim)
        if not isinstance(person, str) or not person:
            held = ", ".join(sorted(k for k, v in claims.items() if isinstance(v, str) and v))
            raise IdentityError(
                f"it names nobody in {self.cfg.person_claim}, the claim A5S_OIDC_PERSON_CLAIM "
                f"says names people: it names someone in {held or 'none'}, so set "
                "A5S_OIDC_PERSON_CLAIM to the one that holds their id in the directory, such as "
                "oid for Entra ID")
        return person


def whose(verifier: Verifier, scenario: Any, claims: dict) -> Any:
    """The person in the directory a checked token's claims are for, with the roles this
    sign-in's groups give them, where the settings give groups roles (core/memberships.py).
    IdentityError if they name nobody, and UnknownPerson if the directory doesn't know who
    they name."""
    claim = verifier.named(claims)
    prefix = verifier.cfg.directory_prefix
    person = scenario.find(f"{prefix}:{claim}") if prefix else scenario.person(claim)
    if person is None:
        sought = f"{prefix}:{claim}" if prefix else claim
        raise UnknownPerson(
            f"a5s doesn't know who you are: your sign-in names you {shown(claim)} in "
            f"{verifier.cfg.person_claim}, and a5s's directory has nobody as {shown(sought)}. "
            "Ask an instance approver, or whoever runs a5s, to add you to the directory. If "
            "you're in it as someone else, whoever runs a5s sets which claim names you, "
            "A5S_OIDC_PERSON_CLAIM, and how the directory knows it, A5S_OIDC_DIRECTORY_PREFIX")
    signed_in = getattr(scenario, "signed_in", None)
    return signed_in(person, claims, verifier.cfg.groups_claim) if signed_in else person


def signed_in(verifier: Verifier, scenario: Any, token: str) -> str:
    """Who in the directory a sign-in token is for. IdentityError if it doesn't check out,
    and UnknownPerson if it names nobody the directory knows."""
    return whose(verifier, scenario, verifier.claims(token)).id


def verifier_from_env() -> Verifier | None:
    cfg = IdentityConfig.from_env()
    return Verifier(cfg) if cfg else None
