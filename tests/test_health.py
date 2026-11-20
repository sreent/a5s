"""The reliability ledger and the SLO gate (core/health.py): per model, per day, how its
calls went, and a model that fails too much is stopped until a person puts it back."""

from a5s import db
from a5s.core import health


def fill(conn, scenario, alias, calls, stalls, failed=0):
    for i in range(calls):
        status = 503 if i < stalls else (400 if i < stalls + failed else 200)
        health.record(conn, scenario, alias, status, 0.5)


def test_a_models_day_counts_its_calls(database):
    with db.transaction(database) as conn:
        fill(conn, "sample", "fake", 5, stalls=1, failed=1)
    [row] = health.report(database, "sample")
    assert (row["model"], row["calls"], row["failed"], row["stalls"], row["gated_at"]) == (
        "fake", 5, 2, 1, None)


def test_a_model_that_fails_too_much_is_gated_until_a_person_restores_it(database):
    with db.transaction(database) as conn:
        fill(conn, "sample", "fake", 20, stalls=11)  # more than half its calls failed
        assert health.gated(conn, "sample", "fake")  # now it's out
        health.restore(conn, "sample", "fake")  # a person puts it back
        assert health.gated(conn, "sample", "fake") is None


def test_a_model_under_its_slo_stays_answerable(database):
    with db.transaction(database) as conn:
        fill(conn, "sample", "fake", 20, stalls=5)
        assert health.gated(conn, "sample", "fake") is None
