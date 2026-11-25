"""Backups and keys (docs/runbooks.md#backing-up-and-a-restore-drill).

A restore drill shows a backup can bring a5s back without touching what runs: `a5s restore
--dry-run` does all a restore would, rolls it back, and says what it would have done, so it can
run against a backup restored beside the database. A rotation of the seal key can be weighed
first the same way: `a5s seal-again --dry-run`, with --leaked or without, says what it would seal
again or what would stop counting, and changes nothing.

And a5s can't see when most of the credentials it holds expire, so whoever makes one notes the
day in A5S_EXPIRES: from 30 days before, the status and `a5s doctor` say so, and once it's past,
that whatever a5s reaches with it refuses it (docs/runbooks.md#credentials-that-expire)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from a5s import cli, config, db, doctor
from a5s.core import delegation, rotation, status
from conftest import SEAL_KEY
from test_configuration import containers, rendered
from test_r15_restore import backed_up
from test_r15_rotation import NEW, TOKENS, keyed
from test_samples import graded, weigh


def ledger_length(url: str) -> int:
    with db.transaction(url) as conn:
        return (conn.execute("select count(*) as n from ledger").fetchone() or {})["n"]


def test_a_restores_dry_run_says_what_it_would_put_back_and_does_none_of_it(database, tmp_path,
                                                                            monkeypatch, capsys):
    store = backed_up(database, tmp_path)  # entries 6 to 9 copied since the backup
    monkeypatch.setenv("A5S_DATABASE_URL", db.as_role(database, "gateway"))
    monkeypatch.setenv("A5S_ANCHOR_STORE", store.path.as_uri())
    before = ledger_length(database)
    cli.main(["restore", "--dry-run"])
    said = capsys.readouterr().out
    assert said.startswith("A dry run, so nothing has changed. Without --dry-run, it would say:\n"
                           "Put back 4 entries of the ledger from its copies, through 9.")
    assert ledger_length(database) == before  # nor its own entry
    cli.main(["restore"])  # and the restore it rehearsed then does it
    assert capsys.readouterr().out.startswith("Put back 4 entries of the ledger")
    assert ledger_length(database) == before + 5


def seal_again(stack, *, leaked: bool = False) -> None:
    """`a5s seal-again --dry-run` where the core runs, with its settings: the new key first."""
    cli._seal_again(replace(stack.cfg, seal_keys=(NEW, SEAL_KEY)), leaked, dry_run=True)


def test_a_rotations_dry_run_says_what_it_would_seal_again_and_seals_nothing(stack, capsys):
    graded(stack, 224)
    weigh(stack)
    keyed(stack, NEW, SEAL_KEY)  # the core at work seals with the new key
    with db.transaction(stack.cfg.database_url) as conn:
        waiting = rotation.waiting(conn, (NEW, SEAL_KEY))
    before = ledger_length(stack.admin)
    seal_again(stack)
    said = capsys.readouterr().out
    assert said.startswith("A dry run, so nothing has changed. Without --dry-run, it would say:\n"
                           "Sealed again with the first key: ")
    assert f"Retired: {rotation.fingerprint(SEAL_KEY)}." in said
    with db.transaction(stack.cfg.database_url) as conn:
        assert rotation.waiting(conn, (NEW, SEAL_KEY)) == waiting  # nothing sealed again
        assert (conn.execute("select retired_at from seal_keys where fingerprint = %s",
                             (rotation.fingerprint(SEAL_KEY),)).fetchone() or {})["retired_at"] is None
    assert ledger_length(stack.admin) == before


def test_a_leaks_dry_run_says_what_would_stop_counting_and_lets_go_of_nothing(stack, capsys):
    graded(stack, 224)
    weigh(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into delegations (person, system, sealed) values ('ben', 'records', "
                     "%s)", (delegation.seal((SEAL_KEY,), "ben", "records", TOKENS),))
    keyed(stack, NEW, SEAL_KEY)
    seal_again(stack, leaked=True)
    said = capsys.readouterr().out
    assert said.startswith("A dry run, so nothing has changed.")
    assert "These stop counting: " in said and "caps" in said
    assert "Let go of 1 connected accounts" in said
    assert keyed(stack, NEW, SEAL_KEY)[2] == 2  # level 2 still counts, and the key isn't retired
    with db.transaction(stack.admin) as conn:
        assert (conn.execute("select count(*) as n from delegations").fetchone() or {})["n"] == 1


# Credentials that expire

TODAY = date(2027, 4, 20)


def test_the_days_credentials_expire_are_read_as_noted():
    assert config.EXPIRES.read({"A5S_EXPIRES": "registry-secret=2027-05-01, mcp-token-tickets="
                                               "2027-01-31"}) == {
        "registry-secret": date(2027, 5, 1), "mcp-token-tickets": date(2027, 1, 31)}
    assert config.EXPIRES.read({}) is None
    for wrong in ("registry-secret", "registry-secret=May 2027", "=2027-05-01"):
        with pytest.raises(config.ConfigError, match="isn't a credential and the day it expires"):
            config.EXPIRES.read({"A5S_EXPIRES": wrong})


def test_the_status_says_a_credential_expires_from_30_days_before_and_once_its_past():
    noted = {"registry-secret": TODAY + timedelta(days=11), "mail-secret": TODAY - timedelta(days=2),
             "mcp-token-tickets": TODAY + timedelta(days=31), "teams-secret-assistant": TODAY}
    found = status.expiring(noted, TODAY)
    assert [(c["credential"], c["days"]) for c in found] == [
        ("mail-secret", -2), ("teams-secret-assistant", 0), ("registry-secret", 11)]  # soonest first
    said = [n for n in status.needs({**quiet(), "expiring": found})]
    assert [n["when"] for n in said] == [status.LATER] * 3  # it waits for working hours
    assert said[0]["said"].startswith("mail-secret expired on 2027-04-18, as A5S_EXPIRES notes, "
                                      "so whatever a5s reaches with it refuses it")
    assert said[1]["said"].startswith("teams-secret-assistant expires on 2027-04-20, today")
    assert said[2]["said"].startswith("registry-secret expires on 2027-05-01, in 11 days")
    assert {n["runbook"] for n in said} == {"docs/runbooks.md#credentials-that-expire"}


def quiet() -> dict:
    """A status with nothing in it that needs anyone."""
    return {"configuration": {"development": True}, "copies": None,
            "changes": {"stuck": 0}, "queue": {"waiting": 0, "oldest_seconds": None},
            "deliveries": {"left_in_inbox": 0}, "samples": {"lapsed": 0},
            "objectives": {"replies": {"met": None}, "chases": {"met": None}}}


def test_the_core_names_the_credentials_noted_to_expire_in_its_status(stack, monkeypatch):
    soon = date.today() + timedelta(days=5)
    monkeypatch.setenv("A5S_EXPIRES", f"registry-secret={soon.isoformat()},mail-secret=2999-01-01")
    with stack.client() as core:
        found = core.get("/status").json()
    assert found["expiring"] == [{"credential": "registry-secret", "on": soon.isoformat(),
                                  "days": 5}]
    assert any(n["said"].startswith(f"registry-secret expires on {soon.isoformat()}, in 5 days")
               for n in found["needs"])


def test_the_doctor_says_whats_expired_to_fix_and_whats_soon_to_look_at(monkeypatch):
    monkeypatch.delenv("A5S_EXPIRES", raising=False)
    [none] = doctor._credentials(TODAY)
    assert none.state == "ok" and none.said.startswith("None is noted to expire in A5S_EXPIRES")
    monkeypatch.setenv("A5S_EXPIRES", "registry-secret=2027-05-01,mail-secret=2027-04-01,"
                                      "mcp-token-tickets=2028-01-01")
    assert [(f.state, f.said[:30]) for f in doctor._credentials(TODAY)] == [
        ("fix", "mail-secret expired on 2027-04"), ("look", "registry-secret expires on 202")]
    monkeypatch.setenv("A5S_EXPIRES", "mcp-token-tickets=2028-01-01")
    [later] = doctor._credentials(TODAY)
    assert later.state == "ok" and "the first, mcp-token-tickets, on 2028-01-01" in later.said


def test_the_chart_gives_the_core_the_days_its_credentials_expire():
    held = {doc["metadata"]["name"]: env.get("value")
            for doc in rendered("ci-values.yaml", sets=("expires.registry-secret=2027-05-01",
                                                        "expires.mail-secret=2027-04-01"))
            for container in containers(doc) for env in container.get("env") or []
            if env["name"] == "A5S_EXPIRES"}
    both = "mail-secret=2027-04-01,registry-secret=2027-05-01"  # the core's status says so,
    assert held == {"a5s-gateway": both, "a5s-doctor": both}  # and helm test's doctor
    assert not [doc for doc in rendered("ci-values.yaml") for container in containers(doc)
                for env in container.get("env") or [] if env["name"] == "A5S_EXPIRES"]
