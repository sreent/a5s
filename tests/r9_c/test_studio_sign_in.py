"""Round 9, reviewer C: signing in to the studio's page in a deployment set up as the docs say.

studio.js sends people to the identity provider with /studio/ as its redirect URI, as each page
does with its own. The provider refuses a redirect URI its app registration doesn't list: the
first day's guide registers each page's (docs/first-day.md), and the development realm the
compose stack's identity provider imports lists its own (deploy/identity/realm.json). Neither
lists /studio/, so nobody can sign in to it there. The tests' own provider checks no redirect
URI, so they pass."""

from __future__ import annotations

import json
import re

from conftest import ROOT


def _pages() -> set[str]:
    found = set()
    for script in (ROOT / "src" / "a5s" / "core" / "webchat").glob("*.js"):
        if m := re.search(r"const BACK = `\$\{location\.origin\}(/[a-z]+/)`", script.read_text()):
            found.add(m.group(1))
    return found


def test_the_first_days_app_registration_lists_the_studios_redirect():
    pages = _pages()
    assert "/studio/" in pages
    guide = (ROOT / "docs" / "first-day.md").read_text()
    registered = set(re.findall(r"https://\$host(/[a-z]+/)", guide))
    # FAILS: /studio/ is missing from --public-client-redirect-uris
    assert pages - registered == set(), pages - registered


def test_the_development_realm_lists_the_studios_redirect():
    realm = json.loads((ROOT / "deploy" / "identity" / "realm.json").read_text())
    uris = {u for client in realm.get("clients", []) for u in client.get("redirectUris", [])}
    listed = {re.sub(r"^https?://[^/]+", "", u).rstrip("*") for u in uris}
    # FAILS: neither /studio/ nor, from before this round, /decide/, /grade/ and /officer/
    assert "/studio/" in listed, sorted(listed)


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
