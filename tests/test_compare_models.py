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
    assert "passed every case for the least" in page.inner_text("#compare-verdict") or (
        "No model with known prices passed every case." in page.inner_text("#compare-verdict"))
