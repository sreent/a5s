"""Round 11, reviewer A: the visible configuration (A-5, A-7). With Teams on, showing its bots
raised, so the gateway and the channels stopped as they started; and a database address's
password showed wherever its shape escaped the mask."""

import pytest

from a5s import cli, config

BOTS = ('[{"agent": "assistant", "app_id": "11111111-2222-3333-4444-555555555555", '
        '"secret_env": "A5S_TEAMS_SECRET_ASSISTANT"}, {"agent": "watcher", "app_id": '
        '"11111111-2222-3333-4444-666666666666", "secret_env": "A5S_TEAMS_SECRET_WATCHER"}]')


def test_a_part_with_teams_bots_starts_and_shows_them_by_agent(monkeypatch):  # A-5
    for name, value in {"A5S_TEAMS_TENANT_ID": "tenant", "A5S_TEAMS_BOTS": BOTS,
                        "A5S_TEAMS_SECRET_ASSISTANT": "not-a-real-secret",
                        "A5S_TEAMS_SECRET_WATCHER": "not-a-real-secret"}.items():
        monkeypatch.setenv(name, value)
    assert config.check()[0] == []
    cli._checked("gateway")  # what `a5s gateway` and `a5s channels` do first
    cli._checked("channels")
    assert config.set_here()["A5S_TEAMS_BOTS"] == "assistant,watcher"
    assert "not-a-real-secret" not in config.described()


@pytest.mark.parametrize("url", [
    "postgresql://db:5432/postgres?user=a5s_gateway&password=Hunter2xyz",  # libpq's own form
    "postgresql://a5s_gateway:abc/def+Hunter2xyz=@db:5432/postgres",  # unescaped, as base64 is
    "postgresql://a5s_gateway:Hunter2xyz@db:5432/postgres",
    "host=db user=a5s_gateway password=Hunter2xyz dbname=postgres",  # a libpq string, unusable
    "postgresql+psycopg://a5s_gateway:Hunter2xyz@db:5432/postgres",  # one a5s can't use
])
def test_a_database_password_never_shows(url):  # A-7
    env = {"A5S_DATABASE_URL": url}
    shown, _ = config.shown(config.DATABASE_URL, env)
    problems, _ = config.check(env)
    said = [shown, *config.set_here(env).values(), *problems, config.described(env)]
    assert not any("Hunter2xyz" in s for s in said), said
