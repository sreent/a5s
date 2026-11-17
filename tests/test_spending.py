"""What agents' model calls cost each month (core/spending.py): by agent and instance, each
run's cost whole, at the prices models.yaml gives, against the budgets the signed settings set
each agent, which its owner approves, with a forecast to the month's end and what each message
answered cost; who sees which; the owners told on their home page; and the page."""

from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
from playwright.sync_api import expect

from a5s import db
from a5s.config import Prices, load_currency
from a5s.contract import parse_settings
from a5s.core import approvals, home, measures, spending
from conftest import accessible

PRICES = Prices(2000.0, 8000.0)  # a million tokens: so a call of 10 in and 5 out costs 0.06


@pytest.fixture
def priced(stack):
    """The stack's model at prices models.yaml gives it, in pounds, before the channels app
    starts, which shares the gateway's models and takes its currency."""
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"], prices=PRICES)
    stack.gateway.currency = "GBP"
    return stack


def as_person(approving: str, provider, person: str, path: str) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.get(f"{approving}{path}", timeout=30, headers={"Authorization": f"Bearer {token}"})


def both_parts(stack, **more) -> None:
    """The assistant at work in billing and orders, which Ana and Omar own."""
    assert not stack.settle(parts=["billing", "orders"], signers=("ana", "omar"), **more).refused


def runs(stack) -> list[dict]:
    """Each run that called a model, oldest first, with what it cost and the records it handled."""
    with db.transaction(stack.admin) as conn:
        found = conn.execute(
            "select id::text as id, opened_at, tokens_in, tokens_out, tokens_cached, "
            "tokens_cache_written, array(select record from run_records rr where rr.run_id = r.id) "
            "as records from runs r where tokens > 0 order by opened_at").fetchall()
    return [{**r, "cost": measures.priced(replace(stack.gateway.models["fake"], prices=PRICES),
                                          r["tokens_in"], r["tokens_out"], r["tokens_cached"],
                                          r["tokens_cache_written"])} for r in found]


def report(stack, person: str, now=None, **more) -> dict:
    who = stack.gateway.scenario.person(person)
    with db.transaction(stack.admin) as conn:
        return spending.report(conn, stack.gateway.models, stack.gateway.spending_in_force(conn),
                               who, now, **more)


def test_a_budget_is_its_agents_owners_to_approve_and_reads_in_words(stack):
    refused = stack.settle(spending={"agents": {"assistant": 300}}, signers=("ana",))
    assert any("owner of the assistant hasn't approved its budget" in why
               for why in refused.refused), refused
    assert not stack.settle(spending={"agents": {"assistant": 300}},
                            signers=("ana", "priya")).refused
    with db.transaction(stack.admin) as conn:
        assert stack.gateway.spending_in_force(conn).agents == {"assistant": 300.0}
    before = parse_settings(b"spending:\n  agents: {assistant: 300}\n")
    after = parse_settings(b"spending:\n  agents: {assistant: 400.5, watcher: 20}\n")
    said = [c["text"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                 stack.gateway.scenario.person)]
    assert "The budget for the assistant becomes 400.50 a month, instead of 300" in said[0]
    assert "The budget for the watcher becomes 20 a month" in said[1]
    assert not any(c["widens"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                          stack.gateway.scenario.person))
    for wrong in (b"spending:\n  agents: {assistant: 0}\n",
                  b"spending:\n  agents: {assistant: '4'}\n", b"spending:\n  teams: {}\n",
                  b"spending:\n  agents: {assistant: 400.505}\n",  # whole cents, as words say it
                  b"spending:\n  currency: pounds\n"):  # its ISO 4217 code
        with pytest.raises(ValueError):
            parse_settings(wrong)


def test_a_runs_cost_is_its_instances_and_agents_whole_and_no_part_has_a_budget(stack):
    """A part's share of a run that handled records in several parts, or in none, is a figure
    few could check: a run's cost is its instance's and its agent's, whole, and a version that
    budgets a part is refused, saying where a budget goes."""
    with pytest.raises(ValueError, match="a5s budgets each agent, not each part"):
        parse_settings(b"spending:\n  parts: {billing: 300}\n")
    stack.model.reply("Hello.")
    stack.say("hello")
    found = report(stack, "ana")
    assert "parts" not in found and [a["key"] for a in found["agents"]] == ["assistant"]
    # and a part's owner reads that they watch what its instances cost, never that they approve it
    assert home.may("part-owner:billing") == (
        "approve the instances that work in billing, and how far each may act there; decide the "
        "changes agents ask for there; and watch those instances' runs, and what they cost")


def test_a_budget_says_the_currency_it_is_in(stack):
    before = parse_settings(b"spending:\n  agents: {assistant: 300}\n")
    after = parse_settings(b"spending:\n  agents: {assistant: 300}\n  currency: GBP\n")
    said = [c["text"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                 stack.gateway.scenario.person)]
    assert said[0] == ("Budgets are in GBP, instead of the currency models.yaml prices models "
                       "in.")
    assert said[1].startswith("The budget for the assistant becomes GBP 300 a month, instead of 300")
    whole = approvals.described(after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert any(line.startswith("The budget for the assistant is GBP 300 a month") for line in whole)
    plain = approvals.described(before, stack.gateway.definitions, stack.gateway.scenario.person)
    assert any("in the currency models.yaml prices models in" in line for line in plain)


def test_what_runs_cost_goes_to_their_agent_and_instance_with_a_forecast(priced):
    stack = priced
    assert not stack.settle(parts=["billing", "orders"], signers=("ana", "omar", "priya"),
                            spending={"agents": {"assistant": 5}}).refused
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    stack.say("which questions mention an invoice?")
    stack.model.reply("Hello.")
    stack.say("hello", person="ben")  # his own conversation: given no run's records (round 14)
    first, second = runs(stack)
    assert first["records"] and all(k.startswith("Q-") for k in first["records"])
    assert not second["records"]
    now = second["opened_at"] + timedelta(seconds=1)
    found = report(stack, "ana", now)
    assert found["current"] and found["currency"] is None  # the caller names it
    [agent] = [a for a in found["agents"] if a["key"] == "assistant"]
    total = first["cost"] + second["cost"]
    assert agent["spent"] == pytest.approx(total) and agent["budget"] == 5
    assert (agent["runs"], agent["answered"], agent["unpriced"]) == (2, 2, 0)
    assert agent["per_answer"] == pytest.approx(total / 2)
    # The rest of the month at the last week's pace
    left = (spending.month_of(now)[1] - now).total_seconds() / 86400
    assert agent["pace"] == pytest.approx(total / spending.PACE)
    assert agent["forecast"] == pytest.approx(total + total / spending.PACE * left)
    [inst] = found["instances"]
    assert (inst["key"], inst["agent"], inst["parts"]) == ("assistant-finance", "assistant",
                                                           ["billing", "orders"])
    assert inst["spent"] == pytest.approx(total)
    # A month that's over has no pace or forecast; one that hasn't begun, or isn't one, is refused
    gone = report(stack, "ana", now + timedelta(days=40), month=now.strftime("%Y-%m"))
    assert gone["current"] is False
    [then] = [a for a in gone["agents"] if a["key"] == "assistant"]
    assert then["spent"] == pytest.approx(total) and (then["pace"], then["forecast"]) == (None, None)
    for wrong in ("2099-01", "11-2026", "0000-01"):  # the year 0000 is none
        with pytest.raises(spending.Refused):
            report(stack, "ana", now, month=wrong)
    # A model whose prices aren't known is counted apart, never as costing nothing
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"], prices=None)
    unpriced = {a["key"]: a for a in report(stack, "ana", now)["agents"]}["assistant"]
    assert (unpriced["spent"], unpriced["unpriced"]) == (0, 2)


def test_each_sees_only_what_is_theirs_to_watch(priced, approving, provider):
    stack = priced
    both_parts(stack)
    stack.model.reply("Hello.")
    stack.say("hello")
    seen = {}
    for person in ("ana", "omar", "priya", "ben"):
        answer = as_person(approving, provider, person, "/studio/api/spending")
        assert answer.status_code == 200, answer.text
        seen[person] = answer.json()
    assert seen["ana"]["currency"] == "GBP"  # from models.yaml
    # Ana approves instances: every agent; Priya owns the agents; Omar owns orders, so sees the
    # instance at work there, as Ben, its deputy, does, and no agent's totals
    assert [a["key"] for a in seen["ana"]["agents"]] == ["assistant"]
    assert [a["key"] for a in seen["priya"]["agents"]] == ["assistant"]
    for person in ("omar", "ben"):
        assert not seen[person]["agents"]
        assert [i["key"] for i in seen[person]["instances"]] == ["assistant-finance"]
    chen = as_person(approving, provider, "chen", "/studio/api/spending")
    assert chen.status_code == 403 and "own a part or an agent" in chen.json()["detail"]
    wrong = as_person(approving, provider, "ana", "/studio/api/spending?month=2099-01")
    assert wrong.status_code == 400 and "hasn't begun" in wrong.json()["detail"]
    none = as_person(approving, provider, "ana", "/studio/api/spending?month=0000-01")
    assert none.status_code == 400 and "such as 2026-11" in none.json()["detail"]


def test_an_owner_is_told_on_their_home_once_the_month_passes_its_budget(priced, approving,
                                                                          provider):
    stack = priced  # Priya owns the assistant
    assert not stack.settle(spending={"agents": {"assistant": 0.05}}, signers=("ana", "priya")).refused
    home = as_person(approving, provider, "priya", "/studio/api/home").json()
    assert not [w for w in home["waiting"] if w["kind"] == "spending"]  # nothing spent yet
    stack.model.reply("Hello.")
    stack.say("hello")  # a call of 10 tokens in and 5 out, 0.06, past 0.05
    cost = sum(r["cost"] for r in runs(stack))
    home = as_person(approving, provider, "priya", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == (f"The assistant has spent GBP {cost:,.2f} this month, past its "
                            "budget of GBP 0.05"), told
    assert told["why"] == ["you own the assistant"]
    assert told["go"] == "/studio/spending#agent-assistant"
    for person in ("ana", "ben"):  # it's neither's budget
        home = as_person(approving, provider, person, "/studio/api/home").json()
        assert not [w for w in home["waiting"] if w["kind"] == "spending"]


def test_budgets_in_another_currency_than_prices_are_compared_with_nothing(priced, approving,
                                                                             provider):
    stack = priced  # models.yaml prices models in pounds
    assert not stack.settle(spending={"agents": {"assistant": 0.05}, "currency": "USD"},
                            signers=("ana", "priya")).refused
    stack.model.reply("Hello.")
    stack.say("hello")  # 0.06 in pounds, which no budget in dollars is past
    found = report(stack, "ana", currency="GBP")
    assert (found["budget_currency"], found["compared"]) == ("USD", False)
    [assistant] = [a for a in found["agents"] if a["key"] == "assistant"]
    assert assistant["budget"] is None and assistant["spent"] > 0.05
    home = as_person(approving, provider, "priya", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == ("Budgets are in USD, and models.yaml prices models in GBP, so a5s "
                            "compares neither"), told
    assert not stack.settle(spending={"agents": {"assistant": 0.05}, "currency": "GBP"},
                            signers=("ana", "priya")).refused
    assert report(stack, "ana", currency="GBP")["compared"] is True


def test_an_owner_is_told_of_runs_on_a_model_whose_prices_arent_known(priced, approving,
                                                                        provider):
    stack = priced
    assert not stack.settle(spending={"agents": {"assistant": 100}}, signers=("ana", "priya")).refused
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"], prices=None)
    stack.model.reply("Hello.")
    stack.say("hello")  # it costs nothing that a5s knows of, so its budget is never past
    home = as_person(approving, provider, "priya", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == ("The assistant ran 1 times this month on a model whose prices aren't "
                            "known, which count for nothing against its budget"), told
    assert told["go"] == "/studio/spending#agent-assistant"


def test_the_spending_page_shows_each_budget_as_ocean_draws_cost_against_plan(priced, approving,
                                                                               provider, browser):
    stack = priced
    assert not stack.settle(spending={"agents": {"assistant": 0.05}},
                            signers=("ana", "priya")).refused
    stack.model.reply("Hello.")
    stack.say("hello")
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/spending")
    page.wait_for_selector("#agent-assistant .cost-bars", timeout=30000)
    assistant = page.inner_text("#agent-assistant")
    assert "Spent" in assistant and "Budget" in assistant and "Forecast" in assistant
    assert "over budget" in page.inner_text("#agent-assistant .cost-over")
    assert page.get_attribute("#agent-assistant", "data-over") == "true"
    assert "£" in assistant  # the currency models.yaml names
    assert page.locator("[id^='part-']").count() == 0  # no part has a share of a run
    assert page.locator("#instances tr[data-instance=assistant-finance]").count() == 1
    assert page.locator("#instances caption").count() == 0  # what it is, above its frame
    assert "What each instance you may watch spent" in page.inner_text("#instances-about")
    accessible(page)
    # The month before, which spent nothing, has no forecast: chosen with the keyboard, which
    # steps through the months until asked to show one (round 14, E-L1)
    page.focus("#month")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    assert "month=" not in page.url  # chosen, not yet shown
    page.keyboard.press("Enter")
    page.wait_for_url("**/studio/spending?month=*", timeout=30000)
    page.wait_for_selector("#agent-assistant .cost-bars", timeout=30000)
    expect(page.locator("#month")).to_be_focused(timeout=10000)
    assert "Forecast" not in page.inner_text("#agent-assistant")
    # The settings' forms set each agent's budget, and none of a part
    page.goto(f"{approving}/studio/settings")
    page.wait_for_selector("#budgets [data-budget='agents:assistant']", timeout=30000)
    assert page.input_value("#budgets [data-budget='agents:assistant']") == "0.05"
    assert page.locator("#budgets [data-budget^='parts:']").count() == 0
    page.fill("#budgets [data-budget='agents:assistant']", "0.07")  # in pounds, as models.yaml says
    page.click("#review")
    page.wait_for_selector("#reviewed-changes li", timeout=30000)
    changes = page.locator("#reviewed-changes li").all_inner_texts()
    assert any(c.startswith("Budgets are in GBP") for c in changes), changes
    assert any("The budget for the assistant becomes GBP 0.07 a month" in c for c in changes), changes


def test_models_yaml_names_the_currency_it_prices_in(tmp_path):
    named = tmp_path / "models.yaml"
    named.write_text("currency: THB\nmodels: {}\n")
    assert load_currency(named) == "THB"
    named.write_text("models: {}\n")
    assert load_currency(named) is None
    named.write_text("currency: baht\nmodels: {}\n")
    with pytest.raises(ValueError, match="a code such as GBP"):
        load_currency(named)


def test_budgets_in_another_currency_need_each_budgets_owner(stack):
    """Round 14 (D9): the same amounts in another currency are other budgets, so a version
    that changes only their currency needs each budget's owner, as one that changes an amount
    does."""
    budgets = {"agents": {"assistant": 300}}
    assert not stack.settle(spending=budgets, signers=("ana", "priya")).refused
    refused = stack.settle(spending={**budgets, "currency": "THB"}, signers=("ana",)).refused
    assert any("owner of the assistant hasn't approved its budget" in why for why in refused)
    assert not stack.settle(spending={**budgets, "currency": "THB"},
                            signers=("ana", "priya")).refused


def test_what_each_message_cost_is_said_only_where_every_runs_cost_is_known(stack):
    """Round 14 (D10): a run on a model whose prices aren't known costs nothing in the figures,
    so what each message cost isn't said while one is among them, never a part of it."""
    stack.model.reply("Hello.")
    stack.say("hello")
    [agent] = [a for a in report(stack, "ana")["agents"] if a["key"] == "assistant"]
    assert (agent["answered"], agent["unpriced"], agent["per_answer"]) == (1, 1, None)
