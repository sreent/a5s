"""Postgres access: connections, transactions, migrations and the roles each part uses.

Each transaction takes a connection from its part's pool and gives it back, rather than
connecting afresh: a soak test counted some 28 connections for each message, and against a
managed Postgres each is a TLS handshake, a password exchange and a new server process. A
pooled connection is checked before it's used, so one a database's failover broke is replaced
rather than failing the work, and carries nothing from one transaction to the next: no
prepared statements, which a migration could leave stale, and only `set local`. A
transaction that can't have a pooled connection at once, because every one is in use or none
can connect, connects afresh, as before: so it never waits on the pool for long, and while
the database is down it fails at once. Only as many connect afresh at once as the pool holds:
past that, a transaction waits for the pool, and then fails, so a stall slows a5s rather than
spending every connection the database allows.
"""

from __future__ import annotations

import atexit
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from typing import LiteralString, cast
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

# The role each part of a5s connects as. Setup runs as the database's administrator.
ROLES = {"gateway": "a5s_gateway", "channels": "a5s_channels", "scheduler": "a5s_scheduler",
         "anchor": "a5s_anchor"}
_LOCK = 0x0A5_5C4E  # one migrator at a time


POOL_SIZE = int(os.environ.get("A5S_DB_POOL_SIZE", "10"))  # connections each part keeps [TBC]
WAIT = 0.5  # seconds a transaction waits for a pooled connection before connecting afresh
BUSY = 10.0  # seconds it waits for the pool when as many have connected afresh as it holds
CONNECT = int(os.environ.get("A5S_DB_CONNECT_TIMEOUT", "2"))  # seconds before failing

# Every connection a5s makes gives each row as a dict, by its columns' names
Connection = psycopg.Connection[DictRow]

_pools: dict[str, ConnectionPool[Connection]] = {}
_spares: dict[str, threading.BoundedSemaphore] = {}  # connections of their own, beyond the pool
_pooling = threading.Lock()


def connect(url: str) -> Connection:
    """A connection of its own, for what outlives a transaction, such as listening, or a
    session's lock, and for migrations."""
    return Connection.connect(url, row_factory=dict_row, connect_timeout=CONNECT)


def _spare(url: str) -> threading.BoundedSemaphore:
    with _pooling:
        return _spares.setdefault(url, threading.BoundedSemaphore(max(1, POOL_SIZE)))


def _pool(url: str) -> ConnectionPool[Connection]:
    with _pooling:
        if (pool := _pools.get(url)) is None:
            pool = _pools[url] = ConnectionPool(
                url, connection_class=Connection, open=True, min_size=1,
                max_size=max(1, POOL_SIZE), max_idle=300, max_lifetime=3600,
                check=ConnectionPool[Connection].check_connection,
                kwargs={"row_factory": dict_row, "prepare_threshold": None,
                        "connect_timeout": CONNECT},
                name=f"a5s-{urlsplit(url).username or 'pool'}")
        return pool


def close_pools() -> None:
    """Close every pooled connection, such as before the database is dropped."""
    with _pooling:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


atexit.register(close_pools)


@contextmanager
def transaction(url: str) -> Iterator[Connection]:
    """One transaction: committed if the block succeeds, rolled back if it raises. On a
    pooled connection, or on one of its own if none is free at once."""
    pool = _pool(url)
    try:
        conn = pool.getconn(timeout=WAIT)
    except PoolTimeout:  # all in use, or the database is down: which, connecting says at once
        spare = _spare(url)
        if spare.acquire(blocking=False):
            try:
                with connect(url) as own:
                    yield own
            finally:
                spare.release()
            return
        conn = pool.getconn(timeout=BUSY)  # as many of their own as the pool holds: it waits
    try:
        yield conn
    except BaseException:
        try:
            conn.rollback()
        except psycopg.Error:  # a broken connection, which the pool replaces
            pass
        raise
    else:
        conn.commit()
    finally:
        pool.putconn(conn)


def migrations() -> list[tuple[int, str, str]]:
    """The numbered migrations, in order."""
    found = []
    for entry in files("a5s").joinpath("migrations").iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.name, entry.read_text()))
    return sorted(found)


class NewerSchema(RuntimeError):
    """The database has migrations this a5s doesn't know: a later release made it."""


def known(url: str) -> None:
    """Refuse to serve a database a later release of a5s migrated, such as after rolling a5s
    back: this code doesn't know what those migrations mean, such as a message for a group."""
    with transaction(url) as conn:
        found = conn.execute("select max(version) as v from schema_migrations").fetchone()["v"]
    if found is not None and found > max(v for v, _, _ in migrations()):
        raise NewerSchema(f"the database is at migration {found}, from a later release of a5s "
                          "than this one: run that release, or restore the database from before "
                          "it (docs/runbooks.md)")


def migrate(url: str, tries: int = 3) -> list[str]:
    """Apply each migration the database hasn't had, in one transaction, and say which ran.
    It waits for the tables' locks a while at most, as a5s serves meanwhile, and tries again."""
    for attempt in range(1, tries + 1):
        try:
            return _migrate(url)
        except psycopg.errors.LockNotAvailable:
            if attempt == tries:
                raise
            time.sleep(2 * attempt)
    return []


def _migrate(url: str) -> list[str]:
    with connect(url) as conn:
        conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK,))
        conn.execute("set local lock_timeout = '15s'")
        if conn.info.server_version >= 160000:  # a managed Postgres's administrator, such as
            # Azure's, isn't a superuser: it takes the parts' roles as it makes them, so it may
            # give their tables to the owner role
            conn.execute("set local createrole_self_grant = 'set, inherit'")
        conn.execute("create table if not exists schema_migrations (version int primary key, "
                     "name text not null, applied_at timestamptz not null default now())")
        done = {r["version"] for r in conn.execute("select version from schema_migrations")}
        ran = []
        for version, name, statements in migrations():
            if version not in done:  # a5s's own SQL, from its package: nobody's input
                conn.execute(cast(LiteralString, statements))
                conn.execute("insert into schema_migrations (version, name) values (%s, %s)",
                             (version, name))
                ran.append(name)
        return ran


def set_passwords(url: str, passwords: dict[str, str]) -> None:
    """Give the parts' roles their passwords, as the database's administrator."""
    with connect(url) as conn:
        for part, password in passwords.items():
            conn.execute(sql.SQL("alter role {} password {}").format(
                sql.Identifier(ROLES[part]), sql.Literal(password)))


def as_role(url: str, part: str, password: str | None = None) -> str:
    """The same database, connecting as a part's own role."""
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    user = ROLES[part] + (f":{password}" if password else "")
    return urlunsplit(parts._replace(netloc=f"{user}@{host}"))
