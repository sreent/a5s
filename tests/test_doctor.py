"""`a5s doctor`: whether a5s can work where it runs, and what to fix first.

It reads what a part would start with, the core's settings, and checks, in order, the settings,
the database and its schema, the release and whether this deployment approved it, the settings
in force, the core and its token, how people sign in, each model's key and the ledger's copies.
Each line says what it found, and where something's wrong, what fixes it; what needs a check
before it says it wasn't checked; and it exits 1 if anything needs fixing (docs/runbooks.md)."""

from __future__ import annotations

import json
import socket
from dataclasses import replace

import pytest

import conftest
from a5s import cli, db, doctor
from conftest import PROVIDER_KEY

# The core's service token as long as a deployment's: the doctor checks what a part would start
# with, which refuses a shorter one
LONG = "doctor-service-token-" + "t" * 32


@pytest.fixture
def long_token(monkeypatch):
    """The stack's core started with LONG: ask for it before the stack."""
    monkeypatch.setattr(conftest, "SERVICE_TOKEN", LONG)
    return LONG


def deployed(monkeypatch, stack, **env: str | None) -> None:
    """The environment the core runs with, as the stack has it, for `a5s doctor` to read:
    with `env` set on top, or, for a value of None, unset."""
    for name in ("A5S_OPERATOR_TOKEN", "A5S_OIDC_ISSUER", "A5S_OIDC_MFA", "A5S_ANCHOR_STORE",
                 "A5S_EXPIRES", "A5S_ENVIRONMENT", "A5S_ENVIRONMENT_NAME"):
        monkeypatch.delenv(name, raising=False)
    given = {"A5S_DATABASE_URL": stack.cfg.database_url, "A5S_GATEWAY_URL": stack.url,
             "A5S_SERVICE_TOKEN": LONG, "A5S_ROOT": str(stack.cfg.root),
             "A5S_LIBRARY_ROOT": str(stack.cfg.library_root), "A5S_DEVELOPMENT": "1",
             "A5S_SEAL_KEYS": "s" * 43, "A5S_TEST_PROVIDER_KEY": PROVIDER_KEY, **env}
    for name, value in given.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def found(check: str) -> list[doctor.Found]:
    return [f for f in doctor.checked() if f.check == check]


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_working_deployment_has_nothing_to_fix(long_token, stack, monkeypatch, capsys):
    deployed(monkeypatch, stack)
    cli.main(["doctor"])  # no exit: nothing to fix
    said = capsys.readouterr().out
    assert said.startswith(f"a5s doctor, for the core at {stack.url}\n")
    states = {f.check: f.state for f in doctor.checked()}
    assert states == {"Settings": "ok", "The database": "ok", "The release": "look",
                      "The settings in force": "ok", "The core": "ok", "Signing in": "look",
                      "The models": "ok", "The ledger's copies": "look", "The core's status": "ok",
                      "Credentials": "ok", "This deployment": "ok"}, said
    assert "The database: The database at a5s_gateway@" in said and "as a5s_gateway" in said
    assert "with 1 instance active" in said
    assert "The models: Each model the agents at work use has its key here: fake " \
           "(A5S_TEST_PROVIDER_KEY)." in said
    assert "In development, a5s runs it anyway." in said
    assert said.rstrip().endswith("Nothing to fix, and 3 to look at.")


def test_a_models_key_never_set_is_named_with_whom_it_stops(long_token, stack, monkeypatch):
    deployed(monkeypatch, stack, A5S_TEST_PROVIDER_KEY=None)
    [models] = found("The models")
    assert models.state == "fix"
    assert models.said.startswith("A5S_TEST_PROVIDER_KEY isn't set, so a5s can't call test's "
                                  "fake-1, which the assistant uses: set it to the provider's "
                                  "API key where the core runs")


def test_beside_a5s_dev_it_learns_from_the_core_that_its_development(long_token, stack,
                                                                    monkeypatch):
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None)  # as in a shell beside `a5s dev`
    [release] = found("The release")
    assert release.state == "look" and release.said.endswith("In development, a5s runs it anyway.")
    assert [f.state for f in found("Signing in")] == ["look"]


def test_outside_development_a_release_nobody_approved_is_to_fix(long_token, stack, monkeypatch,
                                                                 capsys):
    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None)
    [release] = found("The release")
    assert release.state == "fix" and "isn't approved here" in release.said
    assert "so the core runs nothing" in release.said and "`a5s release sign`" in release.said
    [copies] = found("The ledger's copies")  # which a deployment keeps
    assert copies.state == "fix" and copies.said.startswith("No copier has run here")
    assert "`a5s anchor --every` with A5S_ANCHOR_STORE" in copies.said
    with pytest.raises(SystemExit) as stopped:
        cli.main(["doctor"])
    assert stopped.value.code == 1
    assert "to fix" in capsys.readouterr().out


def test_with_nothing_running_it_says_what_to_start_and_skips_what_follows(monkeypatch, capsys):
    monkeypatch.setenv("A5S_DATABASE_URL", f"postgresql://a5s:hunter2@127.0.0.1:{closed_port()}/a5s")
    monkeypatch.setenv("A5S_GATEWAY_URL", f"http://127.0.0.1:{closed_port()}")
    monkeypatch.setenv("A5S_SERVICE_TOKEN", LONG)
    monkeypatch.delenv("A5S_OPERATOR_TOKEN", raising=False)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["doctor"])
    said = capsys.readouterr().out
    assert stopped.value.code == 1 and "hunter2" not in said and "Traceback" not in said
    lines = {line.split(":", 1)[0].split("  ")[-1].strip(): line for line in said.splitlines()
             if ": " in line and line[:1] in "flno"}
    assert lines["The database"].startswith("fix") and "`a5s up`" in lines["The database"]
    assert lines["The release"].startswith("not checked")
    assert lines["The settings in force"].startswith("not checked")
    assert lines["The ledger's copies"].startswith("not checked")
    assert lines["The core"].startswith("fix") and "A5S_GATEWAY_URL" in lines["The core"]


def test_as_json_for_a_script(long_token, stack, monkeypatch, capsys):
    deployed(monkeypatch, stack)
    cli.main(["doctor", "--json"])
    listed = json.loads(capsys.readouterr().out)
    assert {"check": "The core", "state": "ok",
            "said": f"The core answers at {stack.url}, and takes the token given here."} in listed
    assert all(set(f) == {"check", "state", "said"} for f in listed)


def test_a_token_the_core_doesnt_take_is_named(long_token, stack, monkeypatch):
    deployed(monkeypatch, stack, A5S_SERVICE_TOKEN="not-the-cores-" + "x" * 32)
    [core] = found("The core")
    assert core.state == "fix" and "refuses the token in A5S_SERVICE_TOKEN" in core.said


def test_an_issuer_set_otherwise_than_the_provider_names_itself(long_token, stack, provider,
                                                                monkeypatch):
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None, A5S_OIDC_ISSUER=provider.url + "/")
    [signing] = found("Signing in")
    assert signing.state == "fix"
    assert f"names its issuer '{provider.url}', and A5S_OIDC_ISSUER is '{provider.url}/'" \
        in signing.said
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None, A5S_OIDC_ISSUER=provider.url)
    assert [(f.state, f.said[:40]) for f in found("Signing in")] == [
        ("ok", f"The identity provider at {provider.url}"[:40]),
        ("look", "A5S_OIDC_MFA isn't set, so a5s asks no s")]


def test_a_database_with_no_settings_in_force_says_how_to_apply_them(database, monkeypatch):
    monkeypatch.setenv("A5S_DATABASE_URL", database)  # its administrator, and so a superuser
    [reached] = found("The database")
    assert reached.state == "look" and "a superuser, whom none of a5s's grants binds" in reached.said
    [in_force] = found("The settings in force")
    assert in_force.state == "fix" and "`a5s apply`" in in_force.said
    with db.transaction(database) as conn:  # as though a later release had migrated it
        conn.execute("insert into schema_migrations (version, name) values (9999, 'later')")
    [reached] = found("The database")
    assert reached.state == "fix" and "from a later release of a5s" in reached.said
    assert [f.state for f in found("The release")] == ["skip"]


def test_the_copiers_record_is_read_where_the_store_isnt_named_as_the_charts_core_has_it(
        long_token, stack, monkeypatch):
    from a5s.core import anchor

    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None)  # and no A5S_ANCHOR_STORE, as the chart
    with db.transaction(stack.admin) as conn:  # gives the core: the copier, which has it,
        anchor.went(conn, 0)  # records that it copied
    [copies] = found("The ledger's copies")
    assert copies.state == "ok" and copies.said.startswith("The copier is at work, copied 0 minutes")
    anchor.stuck(stack.admin, "the store refused to lock entry 7", stopped=True)
    [copies] = found("The ledger's copies")
    assert copies.state == "fix" and "the store refused to lock entry 7" in copies.said


def test_settings_in_force_that_stop_counting_are_to_fix(long_token, stack, monkeypatch):
    """The core refuses every run with a version of the settings whose approval no longer
    counts, such as once its only approver moves on: the doctor says so, from the core's own
    answer, rather than that a version is in force (round 17, A1)."""
    deployed(monkeypatch, stack)
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=()))
    [in_force] = found("The settings in force")
    assert in_force.state == "fix" and "refuses every run with it" in in_force.said
    assert "aren't approved" in in_force.said


def test_the_copies_are_judged_as_the_status_judges_them(long_token, stack, monkeypatch):
    """What pages in the status, such as the copier's daily check finding the history
    changed, or its last try failing, is to fix here too, never all right (round 17, A2)."""
    from a5s.core import anchor

    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None)
    with db.transaction(stack.admin) as conn:
        anchor.went(conn, 0)  # the copier copies, each minute
        anchor.checked(conn, 0, ["the ledger's chain breaks at entry 3"])  # and its daily check
    [copies] = found("The ledger's copies")
    assert copies.state == "fix" and "chain breaks at entry 3" in copies.said
    with db.transaction(stack.admin) as conn:
        anchor.checked(conn, 0, [])
    anchor.stuck(stack.admin, "ConnectionError, as the copier's log says", stopped=False)
    [copies] = found("The ledger's copies")
    assert copies.state == "fix" and copies.said.startswith("The copier's last try failed")


def test_what_else_the_cores_status_needs_is_said_too(long_token, stack, monkeypatch):
    """The core's status says what needs someone beyond what the doctor reads for itself, such
    as a scheduler that never asked the core to record it: so the doctor never says nothing
    is wrong where the status and the alerts say something is (round 17, A2)."""
    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    deployed(monkeypatch, stack, A5S_DEVELOPMENT=None)
    [needs] = found("The core's status")
    assert needs.state == "look" and needs.said.startswith("The scheduler has never asked")
    assert needs.said.endswith("(docs/runbooks.md#messages-are-waiting)")
    stack.scheduler().seen()
    assert [f.state for f in found("The core's status")] == ["ok"]


def test_the_models_are_those_the_settings_in_force_put_instances_on(long_token, stack,
                                                                     monkeypatch):
    """An approved version may put an instance on another model than the image's file says:
    the doctor reads the instances at work, so a model they use with no key is to fix
    (round 17, A8)."""
    deployed(monkeypatch, stack)
    with db.transaction(stack.admin) as conn:  # as a version approved since put it there
        conn.execute("update instances set model = 'nowhere' where id = 'assistant-finance'")
    said = [f.said for f in found("The models") if f.state == "fix"]
    assert any(s.startswith("nowhere, which the assistant uses, isn't one config/models.yaml "
                            "approves") for s in said), said
