"""Risk, and the friction it earns (docs/design.md; Ocean's EnvironmentBand, ActingAs and
ActionZone): what a press will do, said where it happens, on whichever page.

Which deployment this is, across the top of every page, whoever's signed in and before anyone
is: production in the change's colour, filled, a staging, a test or someone's own machine in
amber, with its name and what that means. The classic mistake isn't made on an administrator's
page: it's doing in production what was meant for a test. A deployment nobody named is taken as
production until someone does, and the doctor says to name it (core/environment.py)."""

from __future__ import annotations

import httpx
import pytest

from a5s import config, doctor
from a5s.core import environment
from conftest import accessible
from test_personas import arrive


def named(monkeypatch, kind: str | None, name: str | None = None) -> None:
    for var, value in (("A5S_ENVIRONMENT", kind), ("A5S_ENVIRONMENT_NAME", name)):
        if value is None:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, value)


def test_a_deployment_says_its_kind_and_name_and_one_nobody_named_is_taken_as_production(
        monkeypatch):
    named(monkeypatch, None)
    assert environment.here(development=True) == {
        "kind": "development", "name": "Development", "named": True,
        "about": "On this machine, for development: a5s takes people's word for who they are."}
    unnamed = environment.here(development=False)
    assert (unnamed["kind"], unnamed["name"], unnamed["named"]) == (
        "production", "Unnamed deployment", False)
    assert unnamed["about"].startswith("Treat what you do here as real")
    named(monkeypatch, "test", "Pilot test")
    assert environment.here(development=False) == {
        "kind": "test", "name": "Pilot test", "named": True,
        "about": "A test: what you do here reaches its test accounts and made-up records alone."}
    named(monkeypatch, "production")  # named, even beside `a5s dev`
    assert environment.here(development=True)["name"] == "Production"
    named(monkeypatch, "live")
    with pytest.raises(config.ConfigError, match="production, staging or test"):
        environment.here(development=False)


def test_the_band_asks_no_sign_in_and_says_nothing_more(approving, monkeypatch):
    named(monkeypatch, "staging", "Pilot staging")
    answer = httpx.get(f"{approving}/shell/environment", timeout=30)
    assert answer.status_code == 200
    assert answer.json() == {"kind": "staging", "name": "Pilot staging", "named": True,
                             "about": environment.ABOUT["staging"]}


def test_the_doctor_says_to_name_a_deployment_nobody_named(monkeypatch):
    named(monkeypatch, None)
    [unnamed] = doctor._deployment(development=False)
    assert unnamed.state == "look" and "set A5S_ENVIRONMENT to production, staging or test" \
        in unnamed.said
    named(monkeypatch, "production", "Production")
    [found] = doctor._deployment(development=False)
    assert found.state == "ok" and found.said == (
        "Every page's band says this is Production, a production deployment.")


def test_every_page_says_which_deployment_this_is_from_before_sign_in(approving, provider,
                                                                      browser, monkeypatch):
    named(monkeypatch, "production")
    before = browser.new_page()
    before.goto(f"{approving}/studio/")  # before anyone signs in: the band is there already
    before.wait_for_selector("#environment", timeout=30000)
    assert before.get_attribute("#environment", "class") == "env-band production"
    before.close()
    page, broken = arrive(browser, approving, provider, "priya")
    band = page.locator("#environment")
    assert band.get_attribute("class") == "env-band production"
    assert band.inner_text().split("\n")[0].startswith("Production")
    assert "Real people and records: what you do here reaches them." in band.inner_text()
    page.mouse.wheel(0, 2000)  # still across the top as the page scrolls, the sidebar below it
    page.wait_for_timeout(200)
    assert band.bounding_box()["y"] == 0
    assert page.locator(".sidebar").bounding_box()["y"] >= band.bounding_box()["height"]
    accessible(page)
    page.goto(f"{approving}/chat/")  # and the web chat's, which the plain shell frames
    page.wait_for_selector("#environment", timeout=30000)
    assert page.get_attribute("#environment", "class") == "env-band production"
    assert not broken, broken


def test_a_test_says_so_in_amber_and_development_says_its_machine(approving, provider, browser,
                                                                  monkeypatch):
    named(monkeypatch, "test", "Pilot test")
    page, broken = arrive(browser, approving, provider, "ana")
    assert page.get_attribute("#environment", "class") == "env-band test"
    assert page.locator("#environment strong").inner_text() == "Pilot test"
    accessible(page)
    assert not broken, broken
