"""Round 7: running a5s through phase 3.

A busy pool slows a5s rather than spending every connection the database allows, a release
never serves a database a later one migrated, and the status shows on-call what phase 3 adds:
questions, the notebook, answers kept back from a group chat, and chats turned away, apart from
what's denied. Each test failed before round 7's fixes.
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest

from a5s import db
from a5s.core import status


def test_a_busy_pool_opens_no_more_connections_than_twice_its_size(database, monkeypatch):
    """Thirty transactions waiting at once, on a pool of two: four connections, not thirty
    (B7)."""
    monkeypatch.setenv("A5S_DB_POOL_SIZE", "2")  # as a deployment sets it
    db.close_pools()
    db._spares.clear()
    with db.transaction(database) as conn:
        conn.execute("select 1")
    peak, stop = [0], threading.Event()

    def watch() -> None:
        with psycopg.connect(database, autocommit=True) as admin:
            while not stop.is_set():
                n = admin.execute("select count(*) from pg_stat_activity where datname = "
                                  "current_database() and backend_type = 'client backend'"
                                  ).fetchone()[0] - 1
                peak[0] = max(peak[0], n)
                time.sleep(0.05)

    def work() -> None:
        with db.transaction(database) as conn:
            conn.execute("select pg_sleep(0.3)")

    watcher = threading.Thread(target=watch)
    watcher.start()
    threads = [threading.Thread(target=work) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    watcher.join()
    db.close_pools()
    db._spares.clear()
    assert peak[0] <= 4


def test_a_release_never_serves_a_database_a_later_one_migrated(stack):
    """Such as after rolling a5s back, when this code doesn't know what a later migration's
    columns mean, such as a message for a group (B14)."""
    db.known(stack.cfg.database_url)  # as migrated: fine
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into schema_migrations (version, name) values (9999, '9999_later.sql')")
    with pytest.raises(db.NewerSchema, match="from a later release of a5s"):
        db.known(stack.cfg.database_url)


def test_a_migration_waiting_on_a_tables_lock_gives_up_and_tries_again(database, monkeypatch):
    """Rather than queue every query on the table behind it while a5s serves (B14)."""
    tries = []

    def locked(url: str) -> list[str]:
        tries.append(url)
        raise psycopg.errors.LockNotAvailable("lock timeout")

    monkeypatch.setattr(db, "_migrate", locked)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    with pytest.raises(psycopg.errors.LockNotAvailable):
        db.migrate(database)
    assert len(tries) == 3


def test_the_status_shows_questions_the_notebook_kept_back_answers_and_turn_aways(stack):
    """And leaves chats turned away out of what's denied, which can page someone (B9)."""
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into outbox (person, channel, text, problem) values "
                     "('ana', 'local', 'kept', 'someone joined the chat while it was answering')")
    from a5s.core import inbox, ledger
    with db.transaction(stack.admin) as conn:
        inbox.turned_away(conn, "matrix", "the group has more than 20 people", [], "")
        ledger.append(conn, {"kind": "notebook", "action": "lapse", "run": None, "instance":
                             "assistant-finance", "acts_for": [], "decision": "record",
                             "args": {"entry": "N-1", "why": "its records changed"}})
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["deliveries"]["kept_back"] == 1 and now["deliveries"]["left_in_inbox"] == 0
    assert now["turned_away"] == 1 and not [d for d in now["denied"] if d["kind"] == "inbound"]
    assert now["notebook"] == {"kept": 0, "lapsed": 1}
    assert now["questions"] == {"answered": 0, "unanswered": 0, "p90_seconds": None}
    told = status.told(now)
    assert "Chats turned away, such as a group too big or with strangers: 1." in told
    assert "Answers kept back from a group chat someone joined: 1." in told
