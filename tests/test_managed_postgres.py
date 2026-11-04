"""a5s on a managed Postgres, such as Azure's, whose administrator may make roles and
databases but isn't a superuser: the migrations, the parts' passwords and the scenario's own
tables are set up by such an administrator, on a server where the parts' roles don't exist
yet, and the core's tables are left with the owner role."""

from urllib.parse import urlsplit, urlunsplit

import psycopg

from a5s import db
from a5s.sample import SampleScenario
from conftest import ROOT

PARTS = ["a5s_gateway", "a5s_channels", "a5s_scheduler", "a5s_anchor", "a5s_owner"]


def test_the_migrations_run_as_an_administrator_who_isnt_a_superuser(database_url):
    with psycopg.connect(database_url, autocommit=True) as conn:  # a new server's
        conn.execute("drop database if exists a5s_managed")
        conn.execute("drop schema if exists public cascade")
        conn.execute("drop schema if exists sample cascade")
        conn.execute("create schema public")
        for role in PARTS:  # no roles of a5s's yet
            if conn.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                conn.execute(f"drop owned by {role}")
                conn.execute(f"drop role {role}")
        if not conn.execute("select 1 from pg_roles where rolname = 'a5s_managed'").fetchone():
            conn.execute("create role a5s_managed login password 'managed' createrole createdb")
        conn.execute("create database a5s_managed owner a5s_managed")
    parts = urlsplit(database_url)
    url = urlunsplit(parts._replace(netloc=f"a5s_managed:managed@{parts.netloc.rsplit('@', 1)[-1]}",
                                    path="/a5s_managed"))
    try:
        ran = db.migrate(url)
        assert len(ran) == len(db.migrations())
        db.set_passwords(url, {part: "a-password" for part in db.ROLES})  # as setup does
        with db.transaction(url) as conn:  # and the sample scenario's own tables
            SampleScenario(ROOT / "scenarios" / "sample", url).setup(conn, db.ROLES["gateway"])
        with psycopg.connect(url) as conn:
            owner = conn.execute("select tableowner from pg_tables where tablename = 'ledger'"
                                 ).fetchone()[0]
            superuser = conn.execute("select rolsuper from pg_roles where rolname = current_user"
                                     ).fetchone()[0]
        assert owner == "a5s_owner" and not superuser
    finally:
        db.close_pools()  # pooled connections to it, which would hold the database open
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("drop database if exists a5s_managed")
