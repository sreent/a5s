"""What agents' model calls cost each month (core/spending.py): by part, agent and instance, at
the prices models.yaml gives, against the budgets the signed settings set, which their owners
approve, with a forecast to the month's end and what each message answered cost; who sees which;
the owners told on their home page; and the page."""

from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from a5s import db
from a5s.config import Prices, load_currency
from a5s.contract import parse_settings
from a5s.core import approvals, measures, spending
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
        return spending.report(conn, stack.gateway.scenario, stack.gateway.models,
                               stack.gateway.spending_in_force(conn), who, now, **more)


def test_a_budget_is_its_owners_to_approve_and_reads_in_words(stack):
    # A part's budget needs its owner, though no instance works there; an agent's, its owner
    refused = stack.settle(spending={"parts": {"orders": 250}}, signers=("ana",))
    assert any("owner of orders" in why for why in refused.refused), refused
    assert not stack.settle(spending={"parts": {"orders": 250}}, signers=("ana", "omar")).refused
    refused = stack.settle(spending={"parts": {"orders": 250}, "agents": {"assistant": 300}},
                           signers=("ana", "omar"))
    assert any("owner of the assistant hasn't approved its budget" in why
               for why in refused.refused), refused
    assert not stack.settle(spending={"parts": {"orders": 250}, "agents": {"assistant": 300}},
                            signers=("ana", "priya")).refused  # orders' budget as it was
    with db.transaction(stack.admin) as conn:
        assert stack.gateway.spending_in_force(conn).agents == {"assistant": 300.0}
    before = parse_settings(b"spending:\n  parts: {billing: 300}\n")
    after = parse_settings(b"spending:\n  parts: {billing: 400.5}\n  agents: {watcher: 20}\n")
    said = [c["text"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                 stack.gateway.scenario.person)]
    assert "The budget for billing becomes 400.50 a month, instead of 300" in said[0]
    assert "The budget for the watcher becomes 20 a month" in said[1]
    assert not any(c["widens"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                          stack.gateway.scenario.person))
    for wrong in (b"spending:\n  parts: {billing: 0}\n", b"spending:\n  parts: {billing: '4'}\n",
                  b"spending:\n  teams: {}\n",
                  b"spending:\n  parts: {billing: 400.505}\n",  # whole cents, as words say it
                  b"spending:\n  currency: pounds\n"):  # its ISO 4217 code
        with pytest.raises(ValueError):
            parse_settings(wrong)


def test_a_budget_says_the_currency_it_is_in(stack):
    before = parse_settings(b"spending:\n  parts: {billing: 300}\n")
    after = parse_settings(b"spending:\n  parts: {billing: 300}\n  currency: GBP\n")
    said = [c["text"] for c in approvals.changes(before, after, stack.gateway.definitions,
                                                 stack.gateway.scenario.person)]
    assert said[0] == ("Budgets are in GBP, instead of the currency models.yaml prices models "
                       "in.")
    assert said[1].startswith("The budget for billing becomes GBP 300 a month, instead of 300")
    whole = approvals.described(after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert any(line.startswith("The budget for billing is GBP 300 a month") for line in whole)
    plain = approvals.described(before, stack.gateway.definitions, stack.gateway.scenario.person)
    assert any("in the currency models.yaml prices models in" in line for line in plain)


def test_what_runs_cost_goes_to_their_parts_agent_and_instance_with_a_forecast(priced):
    stack = priced
    assert not stack.settle(parts=["billing", "orders"], signers=("ana", "omar", "priya"),
                            spending={"parts": {"billing": 0.1}, "agents": {"assistant": 5}}).refused
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
    parts = {p["key"]: p for p in found["parts"]}
    # The first handled billing's records alone; the second none, so it's shared by both parts
    assert parts["billing"]["spent"] == pytest.approx(first["cost"] + second["cost"] / 2)
    assert parts["orders"]["spent"] == pytest.approx(second["cost"] / 2)
    assert parts["billing"]["budget"] == 0.1 and parts["orders"]["budget"] is None
    # Each part counts the messages whose cost it shares, at its share
    assert (parts["billing"]["answered"], parts["orders"]["answered"]) == (2, 1)
    assert parts["billing"]["per_answer"] == pytest.approx((first["cost"] + second["cost"] / 2) / 2)
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
    # Ana approves instances: every part and agent; Omar owns orders; Priya owns the agents;
    # Ben deputises for the instance, so sees it alone
    assert [p["key"] for p in seen["ana"]["parts"]] == ["billing", "orders"]
    assert [p["key"] for p in seen["omar"]["parts"]] == ["orders"] and not seen["omar"]["agents"]
    assert not seen["priya"]["parts"] and [a["key"] for a in seen["priya"]["agents"]] == ["assistant"]
    assert not seen["ben"]["parts"] and not seen["ben"]["agents"]
    assert [i["key"] for i in seen["ben"]["instances"]] == ["assistant-finance"]
    chen = as_person(approving, provider, "chen", "/studio/api/spending")
    assert chen.status_code == 403 and "own a part or an agent" in chen.json()["detail"]
    wrong = as_person(approving, provider, "ana", "/studio/api/spending?month=2099-01")
    assert wrong.status_code == 400 and "hasn't begun" in wrong.json()["detail"]
    none = as_person(approving, provider, "ana", "/studio/api/spending?month=0000-01")
    assert none.status_code == 400 and "such as 2026-11" in none.json()["detail"]


def test_an_owner_is_told_on_their_home_once_the_month_passes_its_budget(priced, approving,
                                                                          provider):
    stack = priced
    assert not stack.settle(spending={"parts": {"billing": 0.05}}).refused  # Ana owns billing
    home = as_person(approving, provider, "ana", "/studio/api/home").json()
    assert not [w for w in home["waiting"] if w["kind"] == "spending"]  # nothing spent yet
    stack.model.reply("Hello.")
    stack.say("hello")  # a call of 10 tokens in and 5 out, 0.06, past 0.05
    cost = sum(r["cost"] for r in runs(stack))
    home = as_person(approving, provider, "ana", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == (f"billing has spent GBP {cost:,.2f} this month, past its budget of "
                            "GBP 0.05"), told
    assert told["why"] == ["you own billing"] and told["go"] == "/studio/spending#part-billing"
    ben = as_person(approving, provider, "ben", "/studio/api/home").json()
    assert not [w for w in ben["waiting"] if w["kind"] == "spending"]  # it isn't Ben's budget


def test_budgets_in_another_currency_than_prices_are_compared_with_nothing(priced, approving,
                                                                             provider):
    stack = priced  # models.yaml prices models in pounds
    assert not stack.settle(spending={"parts": {"billing": 0.05}, "currency": "USD"}).refused
    stack.model.reply("Hello.")
    stack.say("hello")  # 0.06 in pounds, which no budget in dollars is past
    found = report(stack, "ana", currency="GBP")
    assert (found["budget_currency"], found["compared"]) == ("USD", False)
    [billing] = [p for p in found["parts"] if p["key"] == "billing"]
    assert billing["budget"] is None and billing["spent"] > 0.05
    home = as_person(approving, provider, "ana", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == ("Budgets are in USD, and models.yaml prices models in GBP, so a5s "
                            "compares neither"), told
    assert not stack.settle(spending={"parts": {"billing": 0.05}, "currency": "GBP"}).refused
    assert report(stack, "ana", currency="GBP")["compared"] is True


def test_an_owner_is_told_of_runs_on_a_model_whose_prices_arent_known(priced, approving,
                                                                        provider):
    stack = priced
    assert not stack.settle(spending={"parts": {"billing": 100}}).refused
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"], prices=None)
    stack.model.reply("Hello.")
    stack.say("hello")  # it costs nothing that a5s knows of, so its budget is never past
    home = as_person(approving, provider, "ana", "/studio/api/home").json()
    [told] = [w for w in home["waiting"] if w["kind"] == "spending"]
    assert told["what"] == ("billing ran 1 times this month on a model whose prices aren't "
                            "known, which count for nothing against its budget"), told
    assert told["go"] == "/studio/spending#part-billing"


def test_the_spending_page_shows_each_budget_as_ocean_draws_cost_against_plan(priced, approving,
                                                                               provider, browser):
    stack = priced
    assert not stack.settle(spending={"parts": {"billing": 0.05}, "agents": {"assistant": 20}},
                            signers=("ana", "priya")).refused
    stack.model.reply("Hello.")
    stack.say("hello")
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/spending")
    page.wait_for_selector("#part-billing .cost-bars", timeout=30000)
    billing = page.inner_text("#part-billing")
    assert "Spent" in billing and "Budget" in billing and "Forecast" in billing
    assert "over budget" in page.inner_text("#part-billing .cost-over")
    assert page.get_attribute("#part-billing", "data-over") == "true"
    assert "under budget" in page.inner_text("#agent-assistant .cost-over")
    assert "£" in billing  # the currency models.yaml names
    assert page.locator("#instances tr[data-instance=assistant-finance]").count() == 1
    accessible(page)
    # The month before, which spent nothing, has no forecast
    page.select_option("#month", index=1)
    page.wait_for_url("**/studio/spending?month=*", timeout=30000)
    page.wait_for_selector("#part-billing .cost-bars", timeout=30000)
    assert "Forecast" not in page.inner_text("#part-billing")
    # The settings' forms set each budget
    page.goto(f"{approving}/studio/settings")
    page.wait_for_selector("#budgets [data-budget='parts:billing']", timeout=30000)
    assert page.input_value("#budgets [data-budget='parts:billing']") == "0.05"
    assert page.input_value("#budgets [data-budget='agents:assistant']") == "20"
    page.fill("#budgets [data-budget='parts:billing']", "0.07")  # in pounds, as models.yaml says
    page.click("#review")
    page.wait_for_selector("#reviewed-changes li", timeout=30000)
    changes = page.locator("#reviewed-changes li").all_inner_texts()
    assert any(c.startswith("Budgets are in GBP") for c in changes), changes
    assert any("The budget for billing becomes GBP 0.07 a month" in c for c in changes), changes


def test_models_yaml_names_the_currency_it_prices_in(tmp_path):
    named = tmp_path / "models.yaml"
    named.write_text("currency: THB\nmodels: {}\n")
    assert load_currency(named) == "THB"
    named.write_text("models: {}\n")
    assert load_currency(named) is None
    named.write_text("currency: baht\nmodels: {}\n")
    with pytest.raises(ValueError, match="a code such as GBP"):
        load_currency(named)
