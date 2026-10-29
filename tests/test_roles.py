"""Each part connects as its own role, and only the core may write the core's records."""

import psycopg
import pytest

from a5s import db
from a5s.core import ledger

FORGED_INBOUND = ("insert into inbound (id, channel, source_id, person, agent, text, reply_to) "
                  "values (gen_random_uuid(), 'teams', 'x', 'ben', 'assistant', 'hi', '{}')")
FORGED_APPROVAL = ("insert into settings_approvals (scenario, digest, person, token, nonce, salt, "
                   "issuer, subject, seal) values ('sample', 'x', 'ana', 'x', 'x', 'x', 'x', 'x', 'x')")


def refused(url: str, statement: str) -> bool:
    with psycopg.connect(url) as conn:
        try:
            conn.execute(statement)
        except (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException):
            return True
    return False


@pytest.fixture
def ledgered(database):
    with db.transaction(database) as conn:
        ledger.append(conn, {"kind": "test", "action": "note", "decision": "allow"})
    return database


@pytest.mark.parametrize("statement", [
    FORGED_INBOUND,
    "update instances set level = 2",
    ("insert into runs (id, instance_id, token_hash, trigger) "
    "values (gen_random_uuid(), 'x', 'x', '{}')"),
    "insert into ledger (seq, entry, prev_hash, hash) values (99, '{}', 'x', 'x')",
    "update inbound set answered_at = now()",
    "truncate ledger",
    ("insert into obligations (scenario, source, record, person, title, opened_at, due_at) "
     "values ('sample', 'records', 'Q-9', 'ben', 'forged', now(), now())"),
    "update obligations set chased_at = null, escalations = 0",
    "insert into schedule_fires (instance_id, schedule, due_at, outcome) values ('x', 'x', now(), 'x')",
    "insert into outbox (person, channel, text) values ('ben', 'local', 'forged')",
    FORGED_APPROVAL,
    "update instances set serves = '{chen}'",
])
def test_the_scheduler_cant_write_the_cores_records(ledgered, statement):
    assert refused(db.as_role(ledgered, "scheduler"), statement)


@pytest.mark.parametrize("part", ["gateway", "channels", "scheduler", "anchor"])
@pytest.mark.parametrize("statement", [
    "update ledger set entry = '{}'", "delete from ledger", "truncate ledger"])
def test_no_part_can_change_or_remove_the_ledger(ledgered, part, statement):
    assert refused(db.as_role(ledgered, part), statement)


def test_not_even_the_administrator_truncates_the_ledger_without_disabling_its_guard(ledgered):
    assert refused(ledgered, "truncate ledger")
    assert refused(ledgered, "delete from ledger")


@pytest.mark.parametrize("part, statement", [
    ("anchor", "insert into ledger (seq, entry, prev_hash, hash) values (99, '{}', 'x', 'x')"),
    ("anchor", "select * from turns"),
    ("channels", "update instances set status = 'active'"),
    ("channels", "select * from turns"),
    ("gateway", "delete from instances"),
    ("gateway", "delete from obligations"),
    ("gateway", "delete from schedule_fires"),
    ("channels", "update obligations set done_at = now()"),
    ("channels", ("insert into settings_versions (scenario, serial, version, signers) "
                 "values ('sample', 99, 'forged', '{}')")),
    ("gateway", FORGED_APPROVAL),  # only the channels, where approvers sign in, record them
    ("gateway", "update settings_proposals set raw = 'forged'"),
    ("channels", "update settings_approvals set seal = 'forged'"),
    ("channels", "delete from settings_approvals"),
    ("channels", ("insert into settings_proposals (scenario, digest, version, serial, raw) "
                 "values ('sample', 'x', 'x', 99, 'x')")),
])
def test_each_part_has_only_the_rights_its_job_needs(ledgered, part, statement):
    assert refused(db.as_role(ledgered, part), statement)


def test_migrations_bring_an_older_database_up_to_date_once(database):
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("drop schema public cascade")
        conn.execute("create schema public")
        version, name, statements = db.migrations()[0]
        conn.execute(statements)  # a database from before the roles
        conn.execute("create table schema_migrations (version int primary key, name text not null, "
                     "applied_at timestamptz not null default now())")
        conn.execute("insert into schema_migrations (version, name) values (%s, %s)", (version, name))
    assert db.migrate(database) == [m[1] for m in db.migrations()[1:]]
    assert db.migrate(database) == []
    assert refused(db.as_role(database, "scheduler"), FORGED_INBOUND)
