"""Upgrading a5s safely (docs/runbooks.md#upgrading-and-rolling-back).

Migrations only go forward: a release won't start on a database a later release migrated, as it
doesn't know what those migrations mean. So rolling back past one means restoring the database,
and whoever upgrades learns first whether the release migrates: `a5s migrate --pending`, run
from the release they're upgrading to, names each migration it would run and what each does,
and runs none. `a5s release promote`, and the check on the pull request that deploys a
release, say the same where Flux deploys a5s (tests/test_gitops.py)."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from a5s import cli, db


def pending(capsys) -> str:
    cli.main(["migrate", "--pending"])
    return capsys.readouterr().out


def test_a_database_with_each_migration_has_nothing_to_migrate(database, monkeypatch, capsys):
    monkeypatch.setenv("A5S_DATABASE_URL", database)
    where, _ = db.where(database)
    newest = db.migrations()[-1][0]
    assert pending(capsys) == (f"Nothing to migrate: the database at {where} has each of this "
                               f"release's migrations, to {newest}.\n")


def test_the_migrations_a_database_lacks_are_named_with_what_each_does_and_none_runs(
        database, monkeypatch, capsys):
    newest = db.migrations()[-2:]
    with db.transaction(database) as conn:  # as the release before this one left it
        conn.execute("delete from schema_migrations where version = any(%s)",
                     ([version for version, _, _ in newest],))
    monkeypatch.setenv("A5S_DATABASE_URL", database)
    where, _ = db.where(database)
    said = pending(capsys).splitlines()
    assert said[0] == (f"`a5s migrate` would run 2 migrations on the database at {where}, in one "
                       "transaction:")
    for (_, name, statements), line in zip(newest, said[1:3], strict=True):
        assert line == f"- {Path(name).stem}: {db.described(statements)}"
        assert len(line) > len(name) + 20  # what it says it does, from its own first lines
    assert said[3].startswith("Once they've run, the release before won't start on the "
                              "database, so take a backup first")
    assert said[3].endswith("(docs/runbooks.md#upgrading-and-rolling-back).")
    assert not {version for version, _, _ in newest} & db.applied(database)  # it ran none


def test_a_database_nobody_migrated_is_made_by_every_migration(database_url, monkeypatch, capsys):
    db.close_pools()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade")
        conn.execute("drop schema if exists sample cascade")
        conn.execute("create schema public")
    monkeypatch.setenv("A5S_DATABASE_URL", database_url)
    where, _ = db.where(database_url)
    try:
        assert pending(capsys) == (f"The database at {where} has no schema yet: `a5s migrate` "
                                   f"makes it, with this release's {len(db.migrations())} "
                                   "migrations.\n")
        assert db.applied(database_url) == set()  # and it made nothing
    finally:
        db.close_pools()


def test_a_database_a_later_release_migrated_says_to_run_that_or_restore(database, monkeypatch):
    with db.transaction(database) as conn:  # as though a later release had migrated it
        conn.execute("insert into schema_migrations (version, name) values (9999, 'later')")
    monkeypatch.setenv("A5S_DATABASE_URL", database)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["migrate", "--pending"])
    said = str(stopped.value)
    assert "is at migration 9999, from a later release of a5s than this one" in said
    assert "run that release, or restore the database from before it" in said


def test_each_migration_says_what_it_does_in_its_first_lines():
    """`a5s migrate --pending` reads what a migration does from the comment it opens with."""
    for _, name, statements in db.migrations():
        assert statements.startswith("--"), name
        assert db.described(statements) != "it says nothing of itself", name
