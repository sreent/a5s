"""Postgres access: connections, transactions and the schema."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files

import psycopg
from psycopg.rows import dict_row


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def transaction(url: str) -> Iterator[psycopg.Connection]:
    """One transaction: committed if the block succeeds, rolled back if it raises."""
    with connect(url) as conn:
        yield conn


def migrate(url: str) -> None:
    sql = files("a5s").joinpath("schema.sql").read_text()
    with connect(url) as conn:
        conn.execute(sql)
