"""Postgres access: connections, transactions, migrations and the roles each part uses."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

# The role each part of a5s connects as. Setup runs as the database's administrator.
ROLES = {"gateway": "a5s_gateway", "channels": "a5s_channels", "scheduler": "a5s_scheduler",
         "anchor": "a5s_anchor"}
_LOCK = 0x0A5_5C4E  # one migrator at a time


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def transaction(url: str) -> Iterator[psycopg.Connection]:
    """One transaction: committed if the block succeeds, rolled back if it raises."""
    with connect(url) as conn:
        yield conn


def migrations() -> list[tuple[int, str, str]]:
    """The numbered migrations, in order."""
    found = []
    for entry in files("a5s").joinpath("migrations").iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.name, entry.read_text()))
    return sorted(found)


def migrate(url: str) -> list[str]:
    """Apply each migration the database hasn't had, in one transaction, and say which ran."""
    with connect(url) as conn:
        conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK,))
        conn.execute("create table if not exists schema_migrations (version int primary key, "
                     "name text not null, applied_at timestamptz not null default now())")
        done = {r["version"] for r in conn.execute("select version from schema_migrations")}
        ran = []
        for version, name, statements in migrations():
            if version not in done:
                conn.execute(statements)
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
