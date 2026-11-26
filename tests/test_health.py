"""The reliability ledger and the SLO gate (core/health.py): per model, per day, how its
calls went, and a model that fails too much is stopped until the release approver puts it
back, signed in, through the core, which records who did in the ledger."""

import pytest

from a5s import db
from a5s.core import audit, health

REACHES = ("assistant-finance calls it again from its next run, for the 2 people it "
           "serves.")  # whom putting the sample's model back reaches: the watcher runs on another


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


def test_a5s_health_measures_this_environments_models_unless_told_otherwise(database,
                                                                            monkeypatch, capsys):
    """Where the core runs, `a5s health` reads that deployment's database and the scenario it
    serves, as its help says, rather than the development database and the sample's."""
    from a5s import cli

    with db.transaction(database) as conn:
        fill(conn, "master-data", "served", 3, stalls=1)
        fill(conn, "sample", "elsewhere", 2, stalls=0)
    monkeypatch.setenv("A5S_DATABASE_URL", database)
    monkeypatch.setenv("A5S_SCENARIO", "a5s.master_data:MasterDataScenario")
    cli.main(["health"])
    said = capsys.readouterr().out
    assert said.startswith("served 3 calls, 1 failed, 1 stalls") and "elsewhere" not in said
    cli.main(["health", "--scenario", "sample"])  # and another's, when asked
    said = capsys.readouterr().out
    assert said.startswith("elsewhere 2 calls") and "served" not in said


def stopped(conn, scenario, alias="fake"):
    """A model the gate stopped: more than half of 20 calls stalled."""
    fill(conn, scenario, alias, 20, stalls=11)
    assert health.gated(conn, scenario, alias)


def test_a_stop_outlasts_its_day_until_a_person_puts_it_back(database):
    """A new day doesn't put a stopped model back by itself: putting it back loosens a5s, so a
    person does it, and it's listed for them although a5s calls it no more."""
    with db.transaction(database) as conn:
        stopped(conn, "sample", "fake")
        conn.execute("update model_health set day = current_date - 1")  # midnight passed
        assert health.gated(conn, "sample", "fake") == ("fake failed too much, and a person "
                                                        "hasn't put it back")
    [row] = health.report(database, "sample")  # no calls today, as a5s calls it no more
    assert (row["model"], row["calls"], row["gated_at"] is not None) == ("fake", 0, True)
    with db.transaction(database) as conn:
        health.restore(conn, "sample", "fake")
        assert health.gated(conn, "sample", "fake") is None
    assert health.report(database, "sample") == []  # nothing today, and nothing stopped


def test_only_the_release_approver_puts_a_stopped_model_back_and_the_ledger_says_who(stack):
    with db.transaction(stack.admin) as conn:
        stopped(conn, stack.gateway.scenario.name)
    with stack.client() as c:
        refused = c.post("/models/fake/restore", json={"by": "ana"})
        assert refused.status_code == 403 and "release approver" in refused.json()["detail"]
        assert c.post("/models/elsewhere/restore", json={"by": "rosa"}).status_code == 404
        put = c.post("/models/fake/restore", json={"by": "rosa"})
        assert put.status_code == 200 and put.json() == {"restored": "fake", "by": "rosa",
                                                          "reaches": REACHES}
        again = c.post("/models/fake/restore", json={"by": "rosa"})
        assert again.status_code == 409  # it isn't stopped now
    with db.transaction(stack.admin) as conn:
        assert health.gated(conn, stack.gateway.scenario.name, "fake") is None
    [entry] = [e for e in stack.ledger() if e.get("action") == "restore-model"]
    assert (entry["kind"], entry["decision"], entry["args"]) == (
        "admin", "record", {"by": "rosa", "identity": "unverified (development)", "model": "fake"})
    with db.transaction(stack.admin) as conn:  # and the auditors' report says so
        acts = audit.report(conn, stack.gateway.scenario, [])["acts"]
    assert [(a["what"], a["by"], a["about"]) for a in acts if a["action"] == "restore-model"] == [
        ("put back a model the health gate stopped", "rosa", {"model": "fake"})]


def test_putting_a_model_back_asks_for_a_sign_in_with_a_second_factor(stack, approving,
                                                                       provider):
    from test_mfa import PASSWORD, WITH_MFA, asking

    asking(stack)
    with db.transaction(stack.admin) as conn:
        stopped(conn, stack.gateway.scenario.name)
    plain, strong = (provider.id_token(person="rosa", **claims) for claims in (PASSWORD, WITH_MFA))
    with stack.client() as c:
        assert c.post("/models/fake/restore", json={"by": "rosa"}).status_code == 401  # no token
        refused = c.post("/models/fake/restore", json={"identity": plain})
        assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
        posing = c.post("/models/fake/restore", json={"by": "ana", "identity": strong})
        assert posing.status_code == 403  # signed in as rosa, not ana
        put = c.post("/models/fake/restore", json={"identity": strong})
        assert put.status_code == 200 and put.json()["by"] == "rosa"
    [entry] = [e for e in stack.ledger() if e.get("action") == "restore-model"]
    assert entry["args"]["identity"] == "verified"


def test_a5s_health_puts_a_model_back_through_the_core_as_the_release_approver(
        stack, monkeypatch, capsys):
    """The command line doesn't write to the database itself: the core checks who asks, and
    the ledger records it, as for suspending and resuming."""
    from a5s import cli
    from conftest import SERVICE_TOKEN

    with db.transaction(stack.admin) as conn:
        stopped(conn, stack.gateway.scenario.name)
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    with pytest.raises(SystemExit, match="403"):
        cli.main(["health", "--restore", "fake", "--by", "ana"])
    cli.main(["health", "--restore", "fake", "--by", "rosa"])
    assert capsys.readouterr().out == f"fake is back, put there by rosa. {REACHES}\n"
    assert [e["args"]["by"] for e in stack.ledger() if e.get("action") == "restore-model"] == [
        "rosa"]


def test_an_operator_puts_a_model_back_with_their_token_as_the_release_approver(
        stack, monkeypatch, capsys):
    """Round 16, A5 and D5: the command line sends the operators' token where one is set, as
    it is on the chart, and the core refused it on this route alone, so only the scheduler's
    token could put a model back. Now it's an operator's route, and the release approver who
    asks must be from outside the team that runs a5s, as for resuming."""
    from dataclasses import replace

    from a5s import cli
    from test_r15_credentials import OPERATOR

    with db.transaction(stack.admin) as conn:
        stopped(conn, stack.gateway.scenario.name)
    stack.gateway.cfg = replace(stack.gateway.cfg, operator_token=OPERATOR, team="risk")
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_OPERATOR_TOKEN", OPERATOR)
    with pytest.raises(SystemExit, match="outside the team"):  # Rosa's in the team, here
        cli.main(["health", "--restore", "fake", "--by", "rosa"])
    stack.gateway.cfg = replace(stack.gateway.cfg, team="platform")
    cli.main(["health", "--restore", "fake", "--by", "rosa"])
    assert capsys.readouterr().out.endswith(f"fake is back, put there by rosa. {REACHES}\n")


# Whom putting it back reaches, said before it's done and once it is (docs/design.md)

def test_the_health_report_and_page_say_whom_putting_a_stopped_model_back_reaches(
        stack, approving, provider, monkeypatch, capsys):
    from dataclasses import replace

    from a5s import cli
    from test_agent_asks import send

    with db.transaction(stack.admin) as conn:
        stopped(conn, stack.gateway.scenario.name)
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_DATABASE_URL", stack.admin)
    cli.main(["health"])
    said = capsys.readouterr().out.splitlines()
    assert said[0].startswith("fake ") and said[0].endswith(": stopped")
    assert said[1] == ("  Putting it back, as the release approver, with a5s health --restore fake, "
                       "reaches assistant-finance, which calls it again from its next run.")
    [model] = send(approving, provider, "rosa", "GET", "/health/api").json()["models"]
    assert model["reaches"] == REACHES  # on the page the release approver reads first
    people = dict(stack.gateway.scenario._people)  # an engineer may read the page, not whom
    people["tomas"] = replace(people["tomas"], roles=("engineer",))  # putting it back reaches
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    [seen] = send(approving, provider, "tomas", "GET", "/health/api").json()["models"]
    assert seen["gated_at"] and "reaches" not in seen
    with db.transaction(stack.admin) as conn:
        health.restore(conn, stack.gateway.scenario.name, "fake")
    models = send(approving, provider, "rosa", "GET", "/health/api").json()["models"]
    assert all("reaches" not in m for m in models)  # answering again: nothing to put back


def test_whom_putting_a_model_back_reaches_reads_as_a_sentence():
    assert health.reached([], 0).startswith("No instance at work runs on it")
    assert health.reached(["assistant-finance"], 1) == (
        "assistant-finance calls it again from its next run, for the one person it serves.")
    assert health.reached(["a", "b", "c"], 12) == (
        "a, b and c call it again from their next run, for the 12 people they serve.")


def test_a_key_never_set_is_a_skipped_call_never_the_models_stall(stack, monkeypatch):
    """A model whose key nobody set was never called: each such call is in the ledger as
    skipped, as one an open breaker skips, never counted against how the model did, so setting
    the key, as a5s says to, is all it takes (round 17, A4)."""
    import conftest

    monkeypatch.setattr(stack.gateway.breakers, "allow", lambda model: True)  # no breaker skips
    monkeypatch.delenv("A5S_TEST_PROVIDER_KEY")  # nobody set the key yet
    for n in range(11):
        stack.say(f"Hello {n}")
    with db.transaction(stack.admin) as conn:
        kept = conn.execute("select coalesce(sum(calls), 0) as calls, coalesce(bool_or(gated_at "
                            "is not null), false) as gated from model_health where model = "
                            "'fake'").fetchone()
        skipped = conn.execute("select count(*) as n from ledger where kind = 'model' and "
                               "(entry::jsonb) -> 'outcome' ->> 'skipped' = 'no key'").fetchone()
    assert (kept["calls"], kept["gated"]) == (0, False) and skipped["n"] >= 11
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", conftest.PROVIDER_KEY)  # the named fix
    stack.model.reply("Hello, Ana.")
    assert stack.say("Are you there now?") == "Hello, Ana."
