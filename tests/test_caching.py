"""Prompt caching: providers cache what a run sends again, and price what a call reads from the
cache, and writes to it, apart. Deep Agents marks where an Anthropic model may cache, which a5s
lets through; a5s counts what each call read from the cache, in budgets and on its run, and the
measures price it."""

import json
from dataclasses import replace

from a5s import db
from a5s.config import Prices, load_models
from a5s.core import budgets, measures, models
from conftest import FAKE_MODELS


def test_each_api_says_what_a_call_read_from_the_cache_in_its_own_words():
    anthropic = {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 900,
                 "cache_creation_input_tokens": 50}  # counted apart from the rest
    openai = {"prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020,
              "prompt_tokens_details": {"cached_tokens": 900}}  # counted in
    deepseek = {"prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020,
                "prompt_cache_hit_tokens": 900, "prompt_cache_miss_tokens": 100}
    assert budgets.split(anthropic) == (1050, 900, 50, 20)
    assert budgets.split(openai) == budgets.split(deepseek) == (1000, 900, 0, 20)
    assert budgets.tokens_of(anthropic) == 1070  # a budget counts all it took
    assert budgets.split(None) == (0, 0, 0, 0)


def test_an_anthropic_model_may_be_told_where_to_cache_the_prompt():
    kept, left_out, refused = models.screen("anthropic", {
        "model": "m", "max_tokens": 10, "messages": [], "cache_control": {"type": "ephemeral"}})
    assert kept["cache_control"] == {"type": "ephemeral"} and left_out == [] and refused is None


def test_the_core_not_the_worker_says_how_long_a_provider_caches_a_run():
    hour = {"type": "ephemeral", "ttl": "1h"}  # as a worker might ask, anywhere it may
    schema = {"type": "object", "properties": {"cache_control": {"type": "string"}}}
    kept, _, refused = models.screen("anthropic", {
        "model": "m", "max_tokens": 10, "cache_control": hour,
        "system": [{"type": "text", "text": "Instructions", "cache_control": hour}],
        "tools": [{"name": "t", "input_schema": schema, "cache_control": hour}],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Ana's records", "cache_control": hour},
            {"type": "tool_result", "tool_use_id": "1", "cache_control": hour,
             "content": [{"type": "text", "text": "Q-1001", "cache_control": hour}]}]}]})
    assert refused is None and '"1h"' not in json.dumps(kept)  # a few minutes, as the officer
    minutes = {"type": "ephemeral"}  # is told (docs/data-protection.md)
    assert kept["cache_control"] == kept["system"][0]["cache_control"] == minutes
    [said, result] = kept["messages"][0]["content"]
    assert said["cache_control"] == result["content"][0]["cache_control"] == minutes
    assert kept["tools"][0]["input_schema"] == schema  # a tool's own fields are its own


def test_the_measures_price_what_runs_read_from_the_cache(stack):
    for said in ("Hello", "Hello again"):
        stack.model.reply("Hello, Ana.")
        stack.say(said)
    with db.transaction(stack.admin) as conn:  # of the 10 tokens each took in, 4 from the cache
        conn.execute("update runs set tokens_cached = 4")
        cheaper = Prices(3.0, 15.0, cached_input=0.3)
        found = measures.report(conn, "sample", {
            "fake": replace(stack.gateway.models["fake"], prices=cheaper)}, 7)
    [run] = found["runs"]
    assert run["cached_share"] == 0.4
    assert run["cost_per_run"] == (6 * 3.0 + 4 * 0.3 + 5 * 15.0) / 1_000_000
    assert "40% of what they took in from the cache" in measures.told(found)


def test_an_approved_model_may_say_what_its_cache_costs(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(FAKE_MODELS + "    prices: {input: 3, output: 15, cached_input: 0.3, "
                                  "cache_write: 3.75}\n")
    assert load_models(path)["fake"].prices == Prices(3.0, 15.0, 0.3, 3.75)
