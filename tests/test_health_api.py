"""The health page's data (core/health_api.py): each model's day from the ledger, with its
canary scores, measured rather than argued about."""

from a5s import db
from a5s.core import health, health_api


def test_the_health_page_shows_each_models_day(stack):
    with db.transaction(stack.admin) as conn:
        for i in range(5):
            health.record(conn, stack.gateway.scenario.name, "fake", 200 if i < 4 else 503, 0.4)
        conn.execute("insert into canary_scores (scenario, canary, model, passed, answered, "
                     "seconds) values (%s, %s, %s, %s, %s, %s)",
                     (stack.gateway.scenario.name, "echo", "fake", True, "hello", 0.2))
    now = health_api.health_now(stack.gateway)
    [model] = now["models"]
    assert (model["model"], model["calls"], model["failed"], model["stalls"],
            model["canary_passed"]) == ("fake", 5, 1, 1, 1)
    assert model["gated_at"] is None  # under its SLO, it may answer


def test_a_gated_model_says_so_on_the_page(stack):
    with db.transaction(stack.admin) as conn:
        for i in range(20):
            health.record(conn, stack.gateway.scenario.name, "fake", 503 if i < 11 else 200, 0.4)
    with db.transaction(stack.admin) as conn:
        health.gated(conn, stack.gateway.scenario.name, "fake")
    [model] = health_api.health_now(stack.gateway)["models"]
    assert model["gated_at"] is not None