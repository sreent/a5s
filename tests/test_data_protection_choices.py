"""What the data protection officer decides about people's data, in the signed settings
(contract.DataProtection, docs/data-protection.md): how long a5s keeps what's said, the fewest
people an instance serves before its own figures go out, and whether the studio, the
auditors' page and the status name people. Each starts private. A version that changes any
of them needs the officer the directory names, and none is the deployment's to set: a part
refuses the variables that used to set three of them, and says where they went."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from a5s import config, db
from a5s.contract import DataProtection, SettingsError, parse_settings
from a5s.core import metrics, registry, retention

OFFICER = "noor"  # the sample directory's data protection officer


def test_each_choice_starts_private_and_stays_in_bounds():
    assert parse_settings(b"serial: 1\n").data_protection == DataProtection(
        kept_for="12 months", fewest_people=5, studio_names=False, audit_names=False,
        flag_rubber_stamps=False)
    chosen = parse_settings(b"serial: 1\ndata_protection: {kept_for: 30 days, "
                            b"fewest_people: 10, studio_names: true}\n").data_protection
    assert (chosen.kept_for, chosen.fewest_people, chosen.studio_names) == (
        "30 days", 10, True)
    for wrong in (b"kept_for: 1 hour", b"kept_for: 121 months",
                  b"kept_for: 3651 days", b"kept_for: forever",
                  b"fewest_people: 1", b"studio_names: yes please", b"names_everyone: true"):
        with pytest.raises(SettingsError):
            parse_settings(b"serial: 1\ndata_protection: {" + wrong + b"}\n")


def test_a_version_that_changes_a_choice_needs_the_officer_the_directory_names(stack):
    refused = stack.settle(data_protection={"studio_names": True})  # Ana alone
    assert refused.refused and any("data-protection-officer named in the directory hasn't "
                                   "approved its choices for people's data" in why
                                   for why in refused.refused), refused
    assert not stack.settle(data_protection={"studio_names": True},
                            signers=("ana", OFFICER)).refused
    with db.transaction(stack.admin) as conn:
        assert stack.gateway.data_protection(conn).studio_names
    # and the next version, choosing nothing anew, needs the officer no more
    assert not stack.settle(data_protection={"studio_names": True}, level=0).refused


def test_the_officer_approves_settings_only_for_what_theirs(stack):
    noor = stack.gateway.scenario.person(OFFICER)
    assert registry.approves(noor)  # a signature that counts, towards what's theirs alone
    refused = stack.settle(level=0, signers=(OFFICER,))
    assert refused.refused, "the officer alone can't approve what an instance may do"


def test_the_sweep_keeps_conversations_as_long_as_the_officer_chose(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:  # said two months ago
        conn.execute("update turns set at = now() - interval '60 days'")
        conn.execute("update inbound set received_at = now() - interval '60 days'")
        conn.execute("update outbox set at = now() - interval '60 days'")
    with stack.client() as c:
        assert c.post("/retention/sweep").json().get("deleted", {}).get("turns") is None
    assert not stack.settle(data_protection={"kept_for": "30 days"},
                            signers=("ana", OFFICER)).refused
    with stack.client() as c:
        swept = c.post("/retention/sweep").json()
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from turns").fetchone()["n"] == 0, swept


def test_a_period_goes_to_postgres_as_a_value_never_as_sql(database):
    with (db.transaction(database) as conn,
          pytest.raises(ValueError, match="isn't a time to keep things for")):
        retention.sweep(conn, datetime.now(UTC), "sample", kept="1 day'; drop table turns; --")


def test_figures_go_out_by_instance_only_for_as_many_people_as_the_officer_chose():
    rows = [{"instance": "a", "tokens": 1, "budget_warnings": 0},
            {"instance": "b", "tokens": 2, "budget_warnings": 0}]
    serving = {"a": {f"p{i}" for i in range(6)}, "b": {f"q{i}" for i in range(8)}}
    assert [r["instance"] for r in metrics.by_instance(rows, serving, "tokens", fewest=5)] == [
        "a", "b"]
    assert [r["instance"] for r in metrics.by_instance(rows, serving, "tokens", fewest=7)] == [
        "b"]  # a's six go out with the smaller instances only once they're as many


def test_the_switches_are_no_longer_the_deployments(monkeypatch):
    problems, _ = config.check({"A5S_STUDIO_NAMES": "true"})
    assert problems == [(
        "A5S_STUDIO_NAMES has moved to the signed settings' data_protection.studio_names, which "
        "the data protection officer approves (docs/data-protection.md): unset it here")]
    assert "A5S_AUDIT_NAMES" in config.MOVED and "A5S_FLAG_RUBBER_STAMPS" in config.MOVED
    assert not hasattr(config.Config, "studio_names")


def test_the_ledgers_copies_are_kept_longer_here_and_shorter_only_by_a_release():
    assert config.ANCHOR_RETAIN_DAYS.read({"A5S_ANCHOR_RETAIN_DAYS": "3650"}) == 3650
    with pytest.raises(config.ConfigError, match="from 365 to 36,500"):
        config.ANCHOR_RETAIN_DAYS.read({"A5S_ANCHOR_RETAIN_DAYS": "30"})


def test_the_waits_nest_or_a_part_wont_start():
    problems, _ = config.check({"A5S_WORKER_WAIT": "120"})  # shorter than a worker's call
    assert problems == [("A5S_WORKER_TIMEOUT must be shorter than A5S_WORKER_WAIT, so it stops, "
                         "and says why, before the wait around it gives up: they're 240 and 120 "
                         "seconds")]
    problems, _ = config.check({"A5S_RUN_MINUTES": "5"})
    assert problems == [("A5S_WORKER_WAIT must be shorter than A5S_RUN_MINUTES, so it stops, "
                         "and says why, before the wait around it gives up: they're 600 and 300 "
                         "seconds")]


def test_a_runs_token_lives_as_long_as_the_deployment_says(stack, monkeypatch):
    monkeypatch.setenv("A5S_RUN_MINUTES", "20")
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:
        run = conn.execute("select opened_at, expires_at from runs order by opened_at desc "
                           "limit 1").fetchone()
    assert abs(run["expires_at"] - run["opened_at"] - timedelta(minutes=20)) < timedelta(seconds=5)


def test_the_data_protection_page_says_each_choice_as_a5s_starts_it():
    from dataclasses import fields

    from conftest import ROOT
    page = (ROOT / "docs" / "data-protection.md").read_text()
    for choice in fields(DataProtection):
        start = getattr(DataProtection, choice.name)
        shown = str(start).lower() if isinstance(start, bool) else str(start)
        assert f"| `{choice.name}` | {shown} |" in page, choice.name
