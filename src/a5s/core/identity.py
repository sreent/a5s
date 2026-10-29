"""People's identity: tokens from the organisation's identity provider, checked in the core.

Entra ID, Google Cloud Identity, Okta and Keycloak all issue OpenID Connect
tokens, so one check works with any of them. The gateway checks each message's
sender itself, so no service can claim that a message came from someone else.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

# Asymmetric algorithms only: a token signed with a shared secret, or with none, is refused.
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384"]


class IdentityError(Exception):
    pass


@dataclass(frozen=True)
class IdentityConfig:
    issuer: str
    audience: str
    # Which claim holds the person's id in the directory. Pick one people can't change:
    # Entra ID's oid, Google's or Okta's sub, or Keycloak's preferred_username.
    person_claim: str = "preferred_username"
    metadata_url: str | None = None  # if it isn't at the issuer's well-known address
    required: tuple[str, ...] = ("exp", "iat", "iss", "aud")
    leeway: int = 30  # seconds of clock skew

    @classmethod
    def from_env(cls) -> IdentityConfig | None:
        issuer = os.environ.get("A5S_OIDC_ISSUER")
        if not issuer:
            return None
        return cls(
            issuer=issuer,  # exactly as the provider writes it: Entra ID's v1 issuer ends in a slash
            audience=os.environ.get("A5S_OIDC_AUDIENCE", "a5s"),
            person_claim=os.environ.get("A5S_OIDC_PERSON_CLAIM", "preferred_username"),
        )


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
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> tuple[PyJWKSet, dict[str, dict]]:
        url = self.cfg.metadata_url or f"{self.cfg.issuer.rstrip('/')}/.well-known/openid-configuration"
        discovery = self.http.get(url)
        discovery.raise_for_status()
        if discovery.json().get("issuer") != self.cfg.issuer:
            raise IdentityError("the identity provider names a different issuer")
        keys = self.http.get(discovery.json()["jwks_uri"])
        keys.raise_for_status()
        published = {k["kid"]: k for k in keys.json().get("keys", []) if isinstance(k, dict) and "kid" in k}
        return PyJWKSet.from_dict(keys.json()), published

    def _keyset(self, *, refresh: bool) -> PyJWKSet:
        age = time.monotonic() - self._fetched_at
        if self._keys is None or age > self.max_age or (refresh and age >= self.min_refresh):
            (self._keys, self._published), self._fetched_at = self._fetch(), time.monotonic()
        return self._keys

    def _key(self, kid: str | None) -> tuple[PyJWK, dict]:
        with self._lock:
            for refresh in (False, True):  # a key it doesn't know yet may be a rotation
                try:
                    return self._keyset(refresh=refresh)[kid], self._published.get(kid or "", {})
                except KeyError:
                    continue
        raise IdentityError("it's signed with a key the identity provider doesn't list")

    def claims(self, token: str, *, endorsed_for: str | None = None) -> dict:
        """The token's claims, if it checks out. Otherwise, IdentityError.

        With `endorsed_for`, the key that signed it must also be endorsed for that
        channel, as the Bot Framework's keys are.
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
                options={"require": list(self.cfg.required)},
            )
        except IdentityError:
            raise
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
            raise IdentityError(str(exc) or type(exc).__name__) from exc

    def person(self, token: str) -> str:
        """Who the token is for, if it checks out. Otherwise, IdentityError."""
        claims = self.claims(token)
        person = claims.get(self.cfg.person_claim)
        if not isinstance(person, str) or not person:
            raise IdentityError(f"it names nobody in {self.cfg.person_claim}")
        return person


def verifier_from_env() -> Verifier | None:
    cfg = IdentityConfig.from_env()
    return Verifier(cfg) if cfg else None
