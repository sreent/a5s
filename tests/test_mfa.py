"""A second factor for what counts (docs/administration.md). Once the deployment says how its
identity provider shows one (A5S_OIDC_MFA, such as amr:mfa), approving settings, deciding a
held change and the officer's requests count only from a sign-in that shows it: each is
refused as it arrives, and again when the core seals it, so a channels app broken into can't
make one count. Resuming an instance asks for one too; suspending one, which only makes a5s
safer, doesn't, so nobody waits for a second factor in an emergency."""

from dataclasses import replace

import pytest

from a5s.core import status
from a5s.core.identity import IdentityConfig, second_factor, second_factor_of
from test_approvals import decide as approve
from test_approvals import proposed
from test_approvals import sign_in as sign_in_to_approve
from test_officer import ask
from test_officer import sign_in as sign_in_as_officer
from test_proposals import asked, decide, held, sweep
from test_sealing import decisions

PASSWORD, WITH_MFA = {"amr": ["pwd"]}, {"amr": ["pwd", "mfa"]}


def asking(stack) -> None:
    """The deployment asks what counts for a second factor, as Entra ID shows one."""
    stack.gateway.identity.cfg = replace(stack.gateway.identity.cfg, mfa=("amr", ("mfa",)))


def test_how_a_deployment_names_a_second_factor():
    assert second_factor_of("amr:mfa") == ("amr", ("mfa",))
    assert second_factor_of(" acr : gold, platinum ") == ("acr", ("gold", "platinum"))
    assert second_factor_of("") is None and second_factor_of(None) is None
    for wrong in ("amr", "amr:", ":mfa"):
        with pytest.raises(ValueError):
            second_factor_of(wrong)
    cfg = IdentityConfig(issuer="i", audience="a", mfa=("amr", ("mfa",)))
    assert second_factor(cfg, WITH_MFA) and not second_factor(cfg, PASSWORD)
    assert not second_factor(cfg, {})  # a provider that says nothing of how
    level = replace(cfg, mfa=("acr", ("gold",)))
    assert second_factor(level, {"acr": "gold"}) and not second_factor(level, {"acr": "bronze"})
    assert second_factor(replace(cfg, mfa=None), PASSWORD)  # asked for none


def test_a_decision_counts_only_from_a_sign_in_with_a_second_factor(stack, approving, provider):
    asking(stack)
    asked(stack)
    [p] = held(stack)
    provider.claims = PASSWORD
    refused = decide(approving, provider, [p["digest"]])
    assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
    assert decisions(stack) == []  # nothing recorded
    provider.claims = WITH_MFA
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    sweep(stack)
    [made] = decisions(stack)
    assert made["seal"] and made["refused"] is None


def test_the_core_never_seals_what_a_sign_in_without_one_made(stack, approving, provider):
    """As a channels app that didn't ask, or one broken into, would record it."""
    asked(stack)
    [p] = held(stack)
    provider.claims = PASSWORD
    assert decide(approving, provider, [p["digest"]]).status_code == 200  # recorded, unasked
    asking(stack)  # the core asks, when it seals
    sweep(stack)
    [made] = decisions(stack)
    assert made["seal"] is None and "second factor" in made["refused"]


def test_settings_are_approved_only_with_a_second_factor(stack, approving, provider):
    asking(stack)
    lower = proposed(stack, level=0)
    provider.claims = PASSWORD
    refused = approve(approving, lower["digest"], *sign_in_to_approve(approving, provider,
                                                                     lower["digest"]))
    assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
    provider.claims = WITH_MFA
    assert approve(approving, lower["digest"], *sign_in_to_approve(approving, provider,
                                                                  lower["digest"])).status_code == 200


def test_the_officer_asks_only_with_a_second_factor(stack, approving, provider):
    asking(stack)
    provider.claims = PASSWORD
    refused = ask(approving, "export", "ben", *sign_in_as_officer(approving, provider,
                                                                  "export", "ben"))
    assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
    provider.claims = WITH_MFA
    assert ask(approving, "export", "ben", *sign_in_as_officer(approving, provider, "export",
                                                               "ben")).status_code == 200


def test_resuming_an_instance_asks_for_one_and_suspending_doesnt(stack, approving, provider):
    asking(stack)
    plain, strong = (provider.id_token(person="ana", **claims) for claims in (PASSWORD, WITH_MFA))
    with stack.client() as c:
        assert c.post("/instances/assistant-finance/suspend",
                      json={"identity": plain}).status_code == 200  # safer, at once
        refused = c.post("/instances/assistant-finance/resume", json={"identity": plain})
        assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
        assert c.post("/instances/assistant-finance/resume",
                      json={"identity": strong}).status_code == 200


def test_the_status_says_whether_what_counts_needs_one(stack, approving):
    with stack.client() as c:
        unchecked = c.get("/status").json()
        asking(stack)
        checked = c.get("/status").json()
    assert unchecked["sign_ins"] == {"second_factor": None}
    assert "aren't checked for a second factor: set A5S_OIDC_MFA" in status.told(unchecked)
    assert checked["sign_ins"] == {"second_factor": "amr:mfa"}
    assert "count with a second factor only: amr:mfa" in status.told(checked)
