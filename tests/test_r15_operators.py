"""Round 15, the operator's findings: the channels app never holds the core's seal keys (D5); a
part refuses a database older than it needs, as well as one newer (D11); one runs as its own
role, never a superuser's or another part's (D10); and settings that can't go together stop it
(D12), as do secrets anyone could guess (D16)."""

from __future__ import annotations

import pytest

from a5s import cli, config, db
from a5s.config import Config


def test_the_channels_app_never_holds_the_cores_seal_keys(tmp_path):
    """With them, it took itself for the core, and asked for the core's secrets (D5)."""
    cfg = Config(database_url="postgresql://nobody@127.0.0.1:1/none",
                 gateway_url="http://127.0.0.1:1", service_token="", root=tmp_path,
                 seal_keys=("k" * 40,))
    with pytest.raises(RuntimeError, match="A5S_SEAL_KEYS is the core's alone"):
        cli._service(cfg, "channels")


def test_a_part_refuses_a_database_older_than_it_needs(database):
    """A database nobody migrated to this release fails as the part starts, saying to run
    `a5s migrate`, rather than at the first column it lacks (D11)."""
    db.known(database)  # as migrated: it serves
    newest = max(v for v, _, _ in db.migrations())
    with db.transaction(database) as conn:
        conn.execute("delete from schema_migrations where version = %s", (newest,))
    with pytest.raises(db.OlderSchema, match="run `a5s migrate` first"):
        db.known(database)


def test_a_part_runs_as_its_own_role(database):
    """Never as a superuser, whom no grant or trigger binds, nor as another part's role (D10)."""
    db.own_role(db.as_role(database, "gateway"), "gateway")  # its own: it serves
    db.own_role(db.as_role(database, "channels"), "channels")
    with pytest.raises(db.WrongRole, match="another part's role"):
        db.own_role(db.as_role(database, "gateway"), "channels")
    with pytest.raises(db.WrongRole, match="a superuser"):
        db.own_role(database, "gateway")  # the tests' administrator is one


def test_settings_that_cant_go_together_stop_a_part():
    """Development, which takes people's word for who they are, with an identity provider set
    (D12)."""
    base = {"A5S_SERVICE_TOKEN": "t" * 40, "A5S_SEAL_KEYS": "k" * 40}
    problems, _ = config.check({**base, "A5S_DEVELOPMENT": "true",
                                "A5S_OIDC_ISSUER": "https://id.example/realms/a5s"})
    assert any("unset A5S_DEVELOPMENT" in p for p in problems), problems
    assert config.check(base) == ([], [])


def test_a_seal_key_or_service_token_anyone_could_guess_stops_a_part():
    """Each takes at least 32 characters, made at random: the token as a part that serves holds
    it (D16)."""
    base = {"A5S_SERVICE_TOKEN": "t" * 40, "A5S_SEAL_KEYS": "k" * 40}
    problems, _ = config.check({**base, "A5S_SEAL_KEYS": f"{'k' * 40},seal"})
    assert problems == [("A5S_SEAL_KEYS has a key of 4 characters: each takes at least 32, "
                         "made at random, as `a5s up` makes them")]
    problems, _ = config.check({**base, "A5S_SERVICE_TOKEN": "secret"})
    assert problems == [("A5S_SERVICE_TOKEN has 6 characters: it takes at least 32, made at "
                         "random, as `a5s up` makes it")]
    assert config.check({**base, "A5S_SERVICE_TOKEN": "secret"}, serving=False) == ([], [])
