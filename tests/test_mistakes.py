"""Every likely mistake names its fix.

Whoever sets a5s up, runs it or signs in to it makes the same few mistakes: a database nobody
started, one not yet migrated, a token that isn't the core's, a provider's key never set, an
issuer written without its last slash, someone the directory doesn't know. Each is said in a
line, never a traceback: what's wrong, what a5s saw against what it takes, and the command or
setting that puts it right, never a password (docs/runbooks.md)."""

from __future__ import annotations

import logging
import socket
import types

import httpx
import psycopg
import pytest

from a5s import cli, db, devdb
from a5s.config import ModelConfig
from a5s.core import models
from a5s.core.identity import (
    IdentityConfig,
    IdentityError,
    UnknownPerson,
    Verifier,
    whose,
)
from conftest import SERVICE_TOKEN, FakeIssuer
from test_webchat import channels


def closed_port() -> int:
    """A port nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stopped(argv: list[str]) -> str:
    """What the command line says as it stops, which is a line of words, never a traceback."""
    with pytest.raises(SystemExit) as stop:
        cli.main(argv)
    said = stop.value.code
    assert isinstance(said, str) and "Traceback" not in said, said
    return said


def other_database(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + f"/{name}"


# The command line

def test_a_database_nobody_started_names_a5s_up_and_the_setting(monkeypatch):
    port = closed_port()
    monkeypatch.setenv("A5S_DATABASE_URL", f"postgresql://a5s:hunter2@127.0.0.1:{port}/a5s")
    said = stopped(["apply"])
    assert f"a5s apply can't reach the database at a5s@127.0.0.1:{port}/a5s" in said
    assert "`a5s up` starts one for development" in said and "A5S_DATABASE_URL" in said
    assert "hunter2" not in said


def test_a_database_there_isnt_says_so(database_url, monkeypatch):
    monkeypatch.setenv("A5S_DATABASE_URL", other_database(database_url, "no_such_database"))
    said = stopped(["migrate"])
    assert "/no_such_database (database \"no_such_database\" does not exist)" in said
    assert "create it, or name the one a5s uses in A5S_DATABASE_URL" in said


def test_a_database_not_migrated_yet_names_a5s_migrate(database_url, monkeypatch):
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("drop database if exists a5s_unmigrated")
        conn.execute("create database a5s_unmigrated")
    monkeypatch.setenv("A5S_DATABASE_URL", other_database(database_url, "a5s_unmigrated"))
    try:
        said = stopped(["apply"])
    finally:
        db.close_pools()
    assert "a5s apply found none of a5s's tables in the database at" in said
    assert "run `a5s migrate` there first" in said and "`a5s setup`" in said


def test_a_password_postgres_refuses_names_the_setting_never_the_password(monkeypatch):
    monkeypatch.setenv("A5S_DATABASE_URL", "postgresql://a5s_gateway:hunter2@db.test:5432/a5s")
    refused = psycopg.OperationalError(
        'connection failed: connection to server at "10.0.0.9", port 5432 failed: FATAL:  '
        'password authentication failed for user "a5s_gateway"')
    said = db.refusal(refused, "postgresql://a5s_gateway:hunter2@db.test:5432/a5s", "a5s gateway")
    assert said.startswith("a5s gateway can't reach the database at a5s_gateway@db.test:5432/a5s")
    assert "Postgres won't take the password for a5s_gateway" in said
    assert "A5S_DATABASE_URL" in said and "A5S_DB_<PART>_PASSWORD" in said
    assert "hunter2" not in said


def test_a_schema_from_a_later_release_says_so_and_what_to_run(database, monkeypatch):
    with db.transaction(database) as conn:  # as though a later release of a5s had migrated it
        conn.execute("insert into schema_migrations (version, name) values (9999, 'later')")
    monkeypatch.setenv("A5S_DATABASE_URL", database)
    monkeypatch.setenv("A5S_SEAL_KEYS", "k" * 43)
    said = stopped(["seal-again"])
    assert said.startswith("a5s seal-again can't go on: the database is at migration 9999, "
                           "from a later release of a5s than this one: run that release")


def test_a_core_nobody_started_names_a5s_dev_and_the_setting(monkeypatch):
    monkeypatch.setenv("A5S_GATEWAY_URL", f"http://127.0.0.1:{closed_port()}")
    monkeypatch.setenv("A5S_SERVICE_TOKEN", "t")
    said = stopped(["status"])
    assert "can't be reached now" in said
    assert "`a5s dev` runs it for development" in said and "A5S_GATEWAY_URL" in said


def test_a_token_that_isnt_the_cores_names_the_setting(stack, monkeypatch):
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", "not-" + SERVICE_TOKEN)
    monkeypatch.delenv("A5S_OPERATOR_TOKEN", raising=False)
    said = stopped(["status"])
    assert said.startswith("401: ") and "To fix it, set A5S_SERVICE_TOKEN to the core's own." in said
    assert SERVICE_TOKEN not in said


def test_a5s_up_without_postgres_names_what_to_install_or_set(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(devdb.shutil, "which", lambda name: None)
    monkeypatch.setattr(devdb.glob, "glob", lambda pattern: [])
    monkeypatch.setattr(devdb, "_windows", lambda: False)
    said = stopped(["up"])
    assert "a5s up can't go on: `a5s up` runs Postgres from its own programs" in said
    assert "install Postgres 16" in said and "set A5S_DATABASE_URL to it" in said
    assert "run `a5s migrate` rather than `a5s up`" in said


def test_the_first_days_commands_say_what_they_do_and_what_comes_next(capsys):
    for command, said in (("up", "Next: `a5s apply`, then `a5s dev`."),
                          ("apply", "On a database of your own, run `a5s migrate` first."),
                          ("dev", "Run `a5s up` and `a5s apply` first"),
                          ("status", "A5S_OPERATOR_TOKEN")):
        with pytest.raises(SystemExit):
            cli.main([command, "--help"])
        shown = " ".join(capsys.readouterr().out.split())
        assert said in shown, (command, shown)


# Signing in

def test_a_token_from_another_issuer_names_both_and_the_setting():
    issuer = FakeIssuer()
    with pytest.raises(IdentityError) as refused:
        issuer.verifier().person(issuer.token("ana", iss="https://id.test/realms/other"))
    said = str(refused.value)
    assert "it's from the issuer 'https://id.test/realms/other'" in said
    assert f"a5s takes sign-ins from '{issuer.url}', as A5S_OIDC_ISSUER sets it" in said


def test_a_token_for_another_client_names_both_and_the_setting():
    issuer = FakeIssuer()
    with pytest.raises(IdentityError) as refused:
        issuer.verifier().person(issuer.token("ana", aud="another-app"))
    said = str(refused.value)
    assert "it's for 'another-app', and a5s takes tokens for 'a5s'" in said
    assert "A5S_OIDC_AUDIENCE" in said and "A5S_WEBCHAT_CLIENT_ID" in said


def test_an_expired_token_says_to_sign_in_again():
    issuer = FakeIssuer()
    with pytest.raises(IdentityError, match="it has expired: sign in again"):
        issuer.verifier().person(issuer.token("ana", exp=1_700_000_000, iat=1_699_999_000))


def test_a_token_naming_nobody_in_the_claim_names_the_setting_and_the_claims_it_holds():
    issuer = FakeIssuer()
    with pytest.raises(IdentityError) as refused:
        issuer.verifier().person(issuer.token(None, oid="0f6e-11"))
    said = str(refused.value)
    assert "it names nobody in preferred_username, the claim A5S_OIDC_PERSON_CLAIM" in said
    assert "it names someone in aud, iss, oid" in said and "such as oid for Entra ID" in said


def test_an_issuer_set_without_its_last_slash_names_both():
    issuer = FakeIssuer()
    slashed = Verifier(IdentityConfig(issuer=issuer.url + "/", audience="a5s"),
                       httpx.Client(transport=httpx.MockTransport(issuer.handler)))
    with pytest.raises(IdentityError) as refused:
        slashed.person(issuer.token("ana"))
    said = str(refused.value)
    assert f"names its issuer '{issuer.url}', and A5S_OIDC_ISSUER is '{issuer.url}/'" in said
    assert "set A5S_OIDC_ISSUER to exactly the provider's, to the last slash" in said


def test_a_provider_the_core_cant_reach_names_where_and_the_settings():
    def away(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    verifier = Verifier(IdentityConfig(issuer="https://id.test/realms/a5s", audience="a5s"),
                        httpx.Client(transport=httpx.MockTransport(away)))
    with pytest.raises(IdentityError) as refused:
        verifier.person(FakeIssuer().token("ana"))
    said = str(refused.value)
    assert "the identity provider at https://id.test/realms/a5s couldn't be reached" in said
    assert "A5S_OIDC_ISSUER, or A5S_OIDC_METADATA_URL" in said


def test_someone_the_directory_doesnt_know_hears_how_they_were_named_and_looked_for():
    issuer = FakeIssuer()
    verifier = Verifier(IdentityConfig(issuer=issuer.url, audience="a5s", person_claim="oid",
                                       directory_prefix="entra"),
                        httpx.Client(transport=httpx.MockTransport(issuer.handler)))
    nobody = types.SimpleNamespace(person=lambda _: None, find=lambda _: None)
    with pytest.raises(UnknownPerson) as refused:
        whose(verifier, nobody, verifier.claims(issuer.token(None, oid="0f6e-11")))
    said = str(refused.value)
    assert said.startswith("a5s doesn't know who you are: your sign-in names you '0f6e-11' in "
                           "oid, and a5s's directory has nobody as 'entra:0f6e-11'.")
    assert "Ask an instance approver, or whoever runs a5s, to add you to the directory" in said
    assert "A5S_OIDC_PERSON_CLAIM" in said and "A5S_OIDC_DIRECTORY_PREFIX" in said


# The models

def test_a_models_key_never_set_names_it_and_the_log_says_so_once(monkeypatch, caplog):
    monkeypatch.delenv("A5S_TEST_UNSET_KEY", raising=False)
    monkeypatch.setattr(models, "_UNSET_SAID", {})
    model = ModelConfig(alias="unkeyed", provider="deepseek", api="openai",
                        base_url="https://api.test", model="deepseek-chat",
                        key_env="A5S_TEST_UNSET_KEY")
    with caplog.at_level(logging.WARNING, logger="a5s.models"):
        for _ in range(3):  # every call fails for it, and the log says so once
            with pytest.raises(models.KeyMissing) as refused:
                models.forward(model, {"messages": []}, httpx.Client())
    said = str(refused.value)
    assert said.startswith("A5S_TEST_UNSET_KEY isn't set, so a5s can't call deepseek's "
                           "deepseek-chat: set it to the provider's API key")
    assert "config/models.yaml" in said
    assert [r.getMessage() for r in caplog.records if r.name == "a5s.models"] == [said]


# The chat, in development

def test_the_dev_chat_says_whom_the_directory_knows_and_when_nothing_is_at_work(stack):
    with channels(stack) as url:
        unknown = httpx.get(f"{url}/channels/local/agents", params={"person": "mallory"})
        assert unknown.status_code == 403
        assert "its directory has nobody as 'mallory'" in unknown.json()["detail"]
        assert "such as ana in the sample's" in unknown.json()["detail"]
        assert httpx.get(f"{url}/channels/local/agents", params={"person": "ana"}).json() == {
            "agents": ["assistant"]}
        with db.transaction(stack.admin) as conn:  # as before anyone applies the settings
            conn.execute("update instances set status = 'retired'")
        assert httpx.get(f"{url}/channels/local/agents", params={"person": "ana"}).json() == {
            "agents": [], "at_work": False}


def test_the_dev_chat_shows_why_and_lets_someone_say_who_they_are_again(stack, browser):
    with channels(stack) as url:
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        page.fill("#person", "mallory")
        page.click("#name button")
        page.wait_for_selector("#rename:visible", timeout=30000)
        assert "its directory has nobody as 'mallory'" in page.inner_text("#status")
        page.click("#rename")
        page.wait_for_selector("#person:visible", timeout=30000)
        page.fill("#person", "ana")
        page.click("#name button")
        page.wait_for_selector("#compose:visible", timeout=30000)
