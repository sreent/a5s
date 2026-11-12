"""The auditors' own page (core/audit.py, core/inbox.py, docs/administration.md): someone with
the auditor's role, or assurance's, signs in and reads the trail. Whoever acted in one of a5s's
roles, approving, deciding, signing or reading it, shows as themselves; whom agents acted for,
told or asked about shows as a stand-in, the same one each time, until the data protection
officer agrees to names. A stand-in finds its entries, and an id doesn't. Exports are there only
once the officer agrees, and each read is in the ledger. Nobody else reads it."""

from contextlib import contextmanager
from dataclasses import replace

import httpx

from a5s import db
from a5s.core import audit, inbox
from conftest import CLIENT, free_port, serve
from test_approvals import decide as approve
from test_approvals import proposed
from test_approvals import sign_in as sign_in_to_approve
from test_mfa import PASSWORD, WITH_MFA
from test_officer import ask
from test_officer import sign_in as sign_in_as_officer

AUDITOR = "kofi"  # the sample's assurance


def reading(url: str, provider, person: str = AUDITOR, **claims):
    def api(path: str, **params) -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person, **claims)}"}
        return httpx.get(f"{url}{path}", params=params, headers=headers, timeout=30)
    return api


def found(api, **params) -> list[dict]:
    r = api("/audit/api/entries", **params)
    assert r.status_code == 200, r.text
    return r.json()["entries"]


def strings(value) -> set[str]:
    """Every text in what the page gave, at any depth."""
    if isinstance(value, dict):
        return {s for v in value.values() for s in strings(v)}
    if isinstance(value, list):
        return {s for v in value for s in strings(v)}
    return {value} if isinstance(value, str) else set()


def unsigned(entry: dict) -> dict:
    """An entry, but for whoever acted in one of a5s's roles, who shows as themselves."""
    if entry["kind"] not in audit.ACTORS:
        return entry
    return {**entry, "args": {k: v for k, v in entry["args"].items() if k not in audit.ACTING}}


def talked(stack) -> None:
    stack.model.reply("Hello, Ana.")
    assert stack.say("Hello") == "Hello, Ana."


@contextmanager
def agreed(stack, provider):
    """The channels app once the data protection officer agrees to names on this page."""
    port = free_port()
    cfg = replace(stack.as_role("channels"), webchat_client_id=CLIENT, development=False,
                  seal_keys=(), audit_names=True)
    with serve(inbox.create_app(replace(stack.gateway, cfg=cfg,
                                        identity=stack.gateway.identity)), port) as url:
        yield url


def test_only_an_auditor_or_assurance_signed_in_reads_the_page(stack, approving, provider):
    talked(stack)
    assert httpx.get(f"{approving}/audit/api", timeout=30).status_code == 401
    for who in ("ana", "priya"):  # an approver, and the team that runs a5s
        r = reading(approving, provider, who)("/audit/api/entries")
        assert r.status_code == 403 and "auditor" in r.json()["detail"]
    now = reading(approving, provider)("/audit/api").json()
    assert now["you"] == "Kofi Mensah" and now["names"] is False and now["exports"] is False
    assert "admin" in now["kinds"] and "run" in now["kinds"]
    served = httpx.get(f"{approving}/audit/", timeout=30)
    assert "script-src 'self'" in served.headers["Content-Security-Policy"]


def test_whom_agents_acted_for_shows_as_a_stand_in_the_same_each_time(stack, approving, provider):
    talked(stack)
    talked(stack)
    entries = found(reading(approving, provider), kind="run")
    stand_ins = {p for e in entries for p in e.get("acts_for") or []}
    assert len(stand_ins) == 1 and next(iter(stand_ins)).startswith(audit.STAND_IN)
    every = found(reading(approving, provider))
    assert "ana" not in strings([unsigned(e) for e in every])  # by her id, only as an approver
    assert {p for e in every for p in e.get("acts_for") or []} == stand_ins  # and nobody else's
    with db.transaction(stack.admin) as conn:  # the key stays the same, so the stand-in does
        assert audit.stand_in(audit.key(conn), "ana") in stand_ins


def test_a_stand_in_finds_its_entries_and_an_id_finds_none(stack, approving, provider):
    talked(stack)
    api = reading(approving, provider)
    [stand_in] = {p for e in found(api, kind="run") for p in e.get("acts_for") or []}
    hers = found(api, **{"for": stand_in})
    assert hers and all(e["acts_for"] == [stand_in] for e in hers)
    assert found(api, **{"for": "ana"}) == []  # the page never says whom agents acted for
    assert found(api, **{"for": audit.STAND_IN + "000000000000"}) == []


def test_administrators_show_as_themselves(stack, approving, provider):
    lower = proposed(stack, level=0)
    assert approve(approving, lower["digest"],
                   *sign_in_to_approve(approving, provider, lower["digest"])).status_code == 200
    api = reading(approving, provider)
    [approved] = found(api, kind="admin", action="approve")
    assert approved["args"]["by"] == "ana"
    assert found(api, by="ana", action="approve") == [approved]  # and are found by their id
    report = api("/audit/api/report").json()
    assert {"by": "ana", "what": "approved settings"}.items() <= next(
        a for a in report["acts"] if a["action"] == "approve").items()
    roles = {row["role"]: row["held_by"] for row in report["roles"]}
    assert roles["instance-approver"] == ["ana"] and roles["assurance"] == [AUDITOR]


def test_whom_the_officer_asked_about_shows_as_a_stand_in(stack, approving, provider):
    assert ask(approving, "export", "ben", *sign_in_as_officer(approving, provider, "export",
                                                               "ben")).status_code == 200
    api = reading(approving, provider)
    [asked] = found(api, kind="admin", action="ask")
    assert asked["args"]["person"].startswith(audit.STAND_IN) and "ben" not in strings(asked)
    assert asked["acts_for"] == [asked["args"]["person"]]
    assert not asked["args"]["by"].startswith(audit.STAND_IN)  # the officer, as themselves
    [act] = [a for a in api("/audit/api/report").json()["acts"] if a["action"] == "ask"]
    assert act["about"]["person"] == asked["args"]["person"]


def test_each_read_of_the_page_is_in_the_ledger(stack, approving, provider):
    talked(stack)
    api = reading(approving, provider)
    [stand_in] = {p for e in found(api, kind="run") for p in e.get("acts_for") or []}
    found(api, **{"for": stand_in})
    api("/audit/api/report")
    reads = [e for e in stack.ledger() if e["kind"] == "audit"]
    assert [e["action"] for e in reads] == ["search", "search", "report"]
    assert all(e["args"]["by"] == AUDITOR and e["args"]["page"] is True
               and e["args"]["through"] == "their sign-in" for e in reads)
    assert reads[1]["args"]["acted_for"] == stand_in  # whom they asked about, as the page shows


def test_exports_are_on_the_page_only_once_the_officer_agrees(stack, approving, provider):
    talked(stack)
    refused = reading(approving, provider)("/audit/api/export")
    assert refused.status_code == 403 and "a5s audit export" in refused.json()["detail"]
    with agreed(stack, provider) as url:
        api = reading(url, provider)
        assert api("/audit/api").json()["exports"] is True
        page = api("/audit/api/export").json()
        assert page["entries"] and audit.checks(page["entries"]) is None  # as the ledger holds it
        runs = found(api, kind="run")
        assert {p for e in runs for p in e.get("acts_for") or []} == {"ana"}  # names, as agreed
        assert found(api, **{"for": "ana"})


def test_the_page_asks_for_a_second_factor_where_the_deployment_does(stack, approving, provider):
    talked(stack)
    stack.gateway.identity.cfg = replace(stack.gateway.identity.cfg, mfa=("amr", ("mfa",)))
    refused = reading(approving, provider, **PASSWORD)("/audit/api")
    assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
    assert reading(approving, provider, **WITH_MFA)("/audit/api").status_code == 200


def test_an_auditor_reads_the_trail_in_the_browser(stack, approving, provider, browser):
    talked(stack)
    provider.person = AUDITOR
    page = browser.new_page()
    page.goto(f"{approving}/audit/")
    page.wait_for_selector("#find:not([hidden])", timeout=30000)
    assert page.inner_text("#who") == "Kofi Mensah"
    assert "stand-in" in page.inner_text("#naming")
    page.select_option("#kind", "run")
    page.click("#search")
    page.wait_for_selector("#entries li", timeout=30000)
    shown = page.inner_text("#entries")
    assert "run open" in shown and audit.STAND_IN in shown and "ana" not in shown.split()
    page.click("#entries button")  # a stand-in finds its other entries
    page.wait_for_selector("#entries li", timeout=30000)
    assert page.input_value("#for").startswith(audit.STAND_IN)
    page.click("#report")
    page.wait_for_selector("#roles:not([hidden])", timeout=30000)
    assert "assurance: kofi" in page.inner_text("#holders")
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
