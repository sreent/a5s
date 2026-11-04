"""Pooled connections. Each transaction takes a connection from its part's pool rather than
connecting afresh, as a soak test counted some 28 for each message. A pooled connection is
checked before it's used, carries nothing from one transaction to the next, and a database
that's down fails a transaction at once rather than after a wait."""

import time

import psycopg
import pytest

from a5s import db
from conftest import free_port


def backend(url: str) -> int:
    with db.transaction(url) as conn:
        return conn.execute("select pg_backend_pid() as pid").fetchone()["pid"]


def test_transactions_reuse_pooled_connections(database):
    seen = {backend(database) for _ in range(20)}
    assert len(seen) <= 2  # a connection or two, used again, not twenty


def test_connections_the_server_dropped_are_replaced_before_theyre_used(database):
    used = {backend(database) for _ in range(5)}
    with psycopg.connect(database, autocommit=True) as admin:  # every one, as a failover would
        dropped = {r[0] for r in admin.execute(
            "select pid from pg_stat_activity where datname = current_database() and "
            "backend_type = 'client backend' and pid <> pg_backend_pid()").fetchall()}
        admin.execute("select pg_terminate_backend(pid) from pg_stat_activity where "
                      "pid = any(%s)", (list(dropped),))
    assert used <= dropped
    time.sleep(0.2)
    assert backend(database) not in dropped  # the work still runs, on a new connection


def test_a_failed_block_is_rolled_back_and_its_connection_reused(database):
    with db.transaction(database) as conn:
        conn.execute("create table if not exists pool_probe (n int)")
    with pytest.raises(RuntimeError), db.transaction(database) as conn:
        conn.execute("insert into pool_probe values (1)")
        raise RuntimeError("the block failed")
    with db.transaction(database) as conn:
        assert conn.execute("select count(*) as n from pool_probe").fetchone()["n"] == 0
        assert conn.execute("show transaction isolation level").fetchone()  # usable
        conn.execute("drop table pool_probe")


def test_settings_made_in_one_transaction_dont_reach_the_next(database):
    with db.transaction(database) as conn:
        conn.execute("set local statement_timeout = '1234ms'")
    with db.transaction(database) as conn:
        assert conn.execute("show statement_timeout").fetchone()["statement_timeout"] != "1234ms"


def test_while_the_database_is_down_a_transaction_fails_at_once():
    down = f"postgresql://a5s@127.0.0.1:{free_port()}/postgres"
    started = time.monotonic()
    try:
        with pytest.raises(psycopg.OperationalError), db.transaction(down):
            pass
        assert time.monotonic() - started < 3  # not after a long wait for the pool
    finally:
        db.close_pools()  # its pool, which would go on trying to connect
