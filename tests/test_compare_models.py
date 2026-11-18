"""Comparing models on an agent's own test cases (docs/studio.md): each case run in the sandbox
says what it took, its time, its runs' tokens and what they cost at the model's prices, and
the test pane runs a draft's cases on each model its author chooses, side by side, to pick the
cheapest that's good enough."""

from dataclasses import replace

import httpx
import pytest

from a5s import cases, sandbox
from conftest import FAKE_MODELS, PROVIDER_KEY, FakeModel, build_root, deployment, free_port, serve
from test_drafts import as_, started
from test_sandbox import drafted

PRICED = FAKE_MODELS + "    prices: {input: 2.0, output: 8.0}\n"  # a million tokens in, and out
CASE = "finds a question by what it's about"


def test_a_case_says_what_it_took_and_cost_on_the_model_it_ran_on(sandbox_database, tmp_path,
                                                                  monkeypatch):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()  # 10 tokens in and 5 out each time it's called
    root = build_root(tmp_path, "fake", PRICED)
    with sandbox.opened(deployment(root), sandbox_database, tmp_path / "sandbox",
                        transport=httpx.MockTransport(model.handler)) as box:
        files = drafted()
        number = next(n for n, c in enumerate(cases.found(files)) if c["name"] == CASE)
        model.reply(None, ("search_records", {"query": "invoice"}))
        model.reply("I looked it up and found Q-1001, about an invoice.")
        ran = box.case("3f2a9c1d", files, "fake", number)
        assert (ran["model"], ran["tokens"]) == ("fake", 30) and ran["seconds"] >= 0
        assert ran["cost"] == pytest.approx((20 * 2.0 + 10 * 8.0) / 1_000_000)
        stood_in = box.case("3f2a9c1d", files, "stand-in", number)
        assert stood_in["model"] == "stand-in" and stood_in["cost"] is None  # no prices


@pytest.fixture
def priced_sandbox(stack, sandbox_database, tmp_path):
    """The stack's studio with a sandbox that has the stand-in and a priced model, which
    answers every question the same way. Ask for it before the channels app, as `approving`."""
    model = FakeModel(answering=lambda body: "Q-1001 mentions an invoice.")
    root = build_root(tmp_path / "box", "fake", PRICED)
    with sandbox.opened(deployment(root), sandbox_database, tmp_path / "sandbox",
                        transport=httpx.MockTransport(model.handler)) as box, \
            serve(sandbox.create_app(box, "shared-token"), free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="shared-token")
        yield box


def test_the_test_pane_compares_models_side_by_side(stack, priced_sandbox, approving, provider,
                                                    browser):
    draft = started(as_(approving, provider, "priya"))
    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(f"{approving}/studio/drafts/{draft['id']}")
    page.wait_for_selector("#journey >> text=Try it in the sandbox", timeout=30000)
    page.click("#journey button:has-text('Try it in the sandbox')")
    page.wait_for_selector("#compare-models", timeout=30000)
    for model in ("stand-in", "fake"):
        page.check(f"#compare-models label:has-text('{model}') input")
    page.click("#compare-run")
    page.wait_for_selector("#compare-verdict", timeout=180000)
    rows = {r.get_attribute("data-model"): r.inner_text()
            for r in page.locator("#compare-table tbody tr").all()}
    assert set(rows) == {"stand-in", "fake"}
    assert "its prices aren't known" in rows["stand-in"] and "aren't known" not in rows["fake"]
    verdict = page.inner_text("#compare-verdict")
    assert any(said in verdict for said in ("passed every case for the least",
                                            "doesn't know their prices", "No model passed"))


@pytest.fixture
def sandbox_says(stack):
    """A sandbox with models a5s knows no prices of and one priced in the deployment's
    currency, pounds, on which every case passes: the models it was asked to run cases on. Ask
    for it before the channels app, as `approving`."""
    from fastapi import FastAPI
    app, asked = FastAPI(), []

    @app.get("/sandbox")
    def about() -> dict:
        return {"people": [{"id": "ana", "name": "Ana Ortiz"}],
                "models": ["stand-in", "plain-a", "plain-b", "priced"]}

    @app.post("/sandbox/cases")
    def case(body: dict) -> dict:
        asked.append(body["model"])
        return {"name": "a case", "file": "tests/cases.yaml", "ran": True, "passed": True,
                "problems": [], "steps": [], "model": body["model"], "seconds": 1.0,
                "tokens": 0, "cost": 0.5 if body["model"] == "priced" else None,
                "judge_tokens": 0}

    with serve(app, free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="a-token")
        stack.gateway.currency = "GBP"
        yield asked


def compared(url: str, provider, browser, *models: str):
    """A draft's test pane, its cases compared on these models: the page, once it's done."""
    draft = started(as_(url, provider, "priya"))
    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(f"{url}/studio/drafts/{draft['id']}")
    page.wait_for_selector("#journey >> text=Try it in the sandbox", timeout=30000)
    page.click("#journey button:has-text('Try it in the sandbox')")
    page.wait_for_selector("#compare-models", timeout=30000)
    for model in models:
        page.check(f"#compare-models label:has-text('{model}') input")
    page.click("#compare-run")
    page.wait_for_selector("#compare-verdict", timeout=180000)
    return page


def test_comparing_says_which_passed_where_it_knows_no_prices_and_costs_in_the_currency(
        stack, sandbox_says, approving, provider, browser):
    """Round 14 (D12): models.yaml ships with no prices, so of the models that passed every
    case, Compare says which, and that it can't say which costs least, rather than that none
    passed; and what it knows a model's cases cost is in the deployment's currency."""
    page = compared(approving, provider, browser, "plain-a", "plain-b", "priced")
    rows = {r.get_attribute("data-model"): r.inner_text()
            for r in page.locator("#compare-table tbody tr").all()}
    assert "\u00a3" in rows["priced"] and "its prices aren't known" in rows["plain-a"]
    verdict = page.inner_text("#compare-verdict")
    assert verdict.startswith("priced passed every case for the least: \u00a3")
    assert "plain-a, plain-b passed every case too, at prices a5s doesn't know." in verdict
    page.uncheck("#compare-models label:has-text('priced') input")
    page.click("#compare-run")
    page.wait_for_function("() => { const v = document.querySelector('#compare-verdict'); "
                           "return !!v && !v.innerText.includes('priced'); }", timeout=180000)
    assert page.inner_text("#compare-verdict").startswith(
        "plain-a, plain-b passed every case, and a5s doesn't know their prices")


def test_comparing_stops_at_the_first_refusal_and_says_why(stack, sandbox_says, approving,
                                                          provider, browser):
    """Round 14 (E-L2): once someone's day of tries on real models is spent, every case would be
    refused, so Compare stops at the first, saying why in a5s's words, rather than showing each
    model as having passed none."""
    from a5s import db
    from a5s.core import budgets
    from a5s.core.studio_api import SANDBOX_DAY
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into sandbox_spend (person, day, tokens) values ('priya', %s, %s)",
                     (budgets.day_of(stack.gateway.scenario, "priya", stack.gateway.clock()),
                      SANDBOX_DAY))
    page = compared(approving, provider, browser, "plain-a", "plain-b")
    assert page.inner_text("#compare-verdict").startswith(
        "It stopped: your tries in the sandbox have taken")
    rows = {r.get_attribute("data-model") for r in page.locator("#compare-table tbody tr").all()}
    assert rows == {"plain-a"} and sandbox_says == []  # it went no further, nor asked the sandbox
