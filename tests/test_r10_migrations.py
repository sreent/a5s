"""Round 10: migrations 0046 to 0050 on a database that already holds tasks, as an
upgrade finds it: they keep each task, and number it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg

from a5s import db


def fresh(database_url: str) -> None:
    db.close_pools()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade")
        conn.execute("drop schema if exists sample cascade")
        conn.execute("create schema public")


def test_an_upgrade_keeps_the_tasks_it_finds_and_numbers_them(database_url, monkeypatch):
    fresh(database_url)
    every = db.migrations()
    monkeypatch.setattr(db, "migrations", lambda: [m for m in every if m[0] <= 45])
    db.migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("insert into instances (id, definition, release, model, owner, status) "
                     "values ('i-1', 'assistant', 'r', 'fake', 'ana', 'active')")
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for n, task_id in enumerate(ids):
            conn.execute(
                "insert into tasks (id, instance_id, owner, audience, task, status, token_budget, "
                "deadline, root, created_at) values (%s, 'i-1', 'ana', '{ana}', 'go through', "
                "%s, 1000, %s, %s, %s)",
                (task_id, ("queued", "running", "done")[n],
                 datetime.now(UTC) + timedelta(days=1), task_id,
                 datetime.now(UTC) - timedelta(minutes=10 - n)))
    monkeypatch.setattr(db, "migrations", lambda: every)
    ran = db.migrate(database_url)
    assert [name for name in ran if name.startswith(("0046", "0047", "0048", "0049", "0050"))]
    with psycopg.connect(database_url, autocommit=True) as conn:
        rows = conn.execute("select id::text, number, status, read_outside, repeat "
                            "from tasks order by created_at").fetchall()
    assert [r[0] for r in rows] == ids and all(r[1] is not None for r in rows)
    assert len({r[1] for r in rows}) == 3 and [r[2] for r in rows] == ["queued", "running", "done"]
    fresh(database_url)
