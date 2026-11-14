"""Round 9 of the critique: signing in to each page in a deployment set up as the docs say. The
first day's app registration and the development realm list every page's redirect, the
studio's among them, and the tests' provider refuses any other, as the organisation's does
(docs/first-day.md, deploy/identity/realm.json; docs/critique.md, round 9)."""

from __future__ import annotations

import json
import re

import httpx

from conftest import REGISTERED, ROOT


def _pages() -> set[str]:
    """Where each page asks to come back to once someone signs in: from the pages' scripts,
    and the studio's from its sources, which its build bundles."""
    found = set()
    studio = ROOT / "studio" / "src"
    for script in [*(ROOT / "src" / "a5s" / "core" / "webchat").glob("*.js"),
                   *studio.rglob("*.ts"), *studio.rglob("*.tsx")]:
        if m := re.search(r"const BACK = `\$\{location\.origin\}(/[a-z]+/)`", script.read_text()):
            found.add(m.group(1))
    return found


def test_the_first_days_app_registration_lists_every_pages_redirect():
    pages = _pages()
    assert "/studio/" in pages
    assert pages <= REGISTERED, pages - REGISTERED


def test_the_development_realm_lists_every_pages_redirect():
    realm = json.loads((ROOT / "deploy" / "identity" / "realm.json").read_text())
    uris = {u for client in realm.get("clients", []) for u in client.get("redirectUris", [])}
    listed = {re.sub(r"^https?://[^/]+", "", u).rstrip("*") for u in uris}
    assert _pages() <= listed, sorted(_pages() - listed)


def test_the_tests_provider_refuses_a_redirect_nobody_registered(provider):
    asked = httpx.get(f"{provider.url}/auth", params={
        "client_id": "a5s", "redirect_uri": "https://elsewhere.test/steal/", "state": "s",
        "nonce": "n", "code_challenge": "c", "code_challenge_method": "S256"},
        follow_redirects=False, timeout=30)
    assert asked.status_code == 400
