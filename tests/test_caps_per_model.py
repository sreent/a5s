"""Acting on its own is earned per model (core/samples.py, round 16, G3). a5s keeps its cap on
a release's type of action in a part for the release's behaviour, which names its model, and
what one model earned never counts for another: a run whose call fell back to another model,
or an instance its settings put on another, asks first there until graded samples on that
model raise its cap. A sample's grade is evidence of the model that answered its run last
before its change, and lowering a cap lowers it on every model."""

from __future__ import annotations

from datetime import timedelta

import yaml

from a5s import db
from a5s.core import registry, samples
from conftest import SEAL_KEY, deciding, seal_grades, signed
from test_levels import MOVE, decisions, due_of, levelled

SAID = "Please move Q-1002 to 2026-11-13."


def release_of(stack) -> str:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select release from instances where id = 'assistant-finance'"
                            ).fetchone()["release"]


def raised_on(stack, model: str, cap: int = 2) -> None:
    """a5s's cap for the assistant's due dates in billing on a model, as graded samples of
    its changes on that model raise it: sealed by the core, with its ledger entry."""
    with db.transaction(stack.admin) as conn:
        kind = samples.behaviour_of(conn, release_of(stack), "change-due-date", model)
        assert kind, f"no behaviour kept for the assistant on {model}"
        samples.set_cap(conn, (SEAL_KEY,), kind, "billing", "change-due-date", cap,
                        "samples passed", stack.gateway.clock(), threshold=0.98)


def put_on(stack, model: str) -> None:
    """A version of the settings that puts the assistant on another approved model, still
    acting on its own for due dates in billing, signed by Ana, who owns billing."""
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    settings["instances"]["assistant-finance"]["model"] = model
    signed(folder, settings, ("ana",))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        applied = registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                 scenario.tools(), scenario.person, scenario.name,
                                 models=stack.gateway.models)
        assert not applied.refused, applied.refused


def test_a_cap_one_model_earned_counts_for_no_other(fallback_stack):
    stack, _, _ = fallback_stack
    levelled(stack)  # earned on its own model, fake
    with db.transaction(stack.admin) as conn:
        keys, release = stack.gateway.cfg.seal_keys, release_of(stack)
        assert samples.caps(conn, keys, release) == {("billing", "change-due-date"): 2}
        assert samples.caps(conn, keys, release, ["fake"]) == {("billing", "change-due-date"): 2}
        assert samples.caps(conn, keys, release, ["spare"]) == {}  # nothing earned: 1
        assert samples.caps(conn, keys, release, ["fake", "spare"]) == {}  # the lower of the two
    raised_on(stack, "spare", cap=2)
    with db.transaction(stack.admin) as conn:
        assert samples.caps(conn, keys, release, ["fake", "spare"]) == {
            ("billing", "change-due-date"): 2}


def test_a_change_its_fallback_asked_for_waits_though_its_own_model_earned_it(
        fallback_stack, provider):
    stack, primary, spare = fallback_stack
    with deciding(stack, provider):  # where its decider decides
        levelled(stack)  # acting on its own for due dates in billing, earned on fake
        primary.failing = 2  # its first call goes to spare, which earned nothing
        spare.reply(None, MOVE)
        primary.reply("Done what I could.")
        stack.say(SAID, person="ben")
        assert due_of(stack) == "2026-11-06"  # not made: it waits for its decider
        assert decisions(stack) == [("hold", ["changes-wait-for-their-decider"])]


def test_once_its_fallback_earns_it_too_the_change_is_made(fallback_stack):
    stack, primary, spare = fallback_stack
    levelled(stack)
    raised_on(stack, "spare")  # graded samples on spare raised its cap too
    primary.failing = 2
    spare.reply(None, MOVE)
    primary.reply("Done what I could.")
    stack.say(SAID, person="ben")
    assert due_of(stack) == "2026-11-13"
    with db.transaction(stack.admin) as conn:  # drawn as a sample of spare's work
        drawn = [r["model"] for r in conn.execute("select model from samples")]
    assert drawn and set(drawn) == {"spare"}


def test_an_instance_its_settings_put_on_another_model_asks_first_there(fallback_stack,
                                                                        provider):
    stack, primary, spare = fallback_stack
    with deciding(stack, provider):
        levelled(stack)  # earned on fake, the release's own
        put_on(stack, "spare")
        spare.reply(None, MOVE)
        spare.reply("Done what I could.")
        stack.say(SAID, person="ben")
        assert due_of(stack) == "2026-11-06"
        assert decisions(stack) == [("hold", ["changes-wait-for-their-decider"])]
        assert not primary.requests  # fake never answered: it ran on spare


def test_there_it_acts_on_its_own_once_graded_samples_on_that_model_earn_it(fallback_stack):
    stack, _, spare = fallback_stack
    levelled(stack, cap=0)
    put_on(stack, "spare")
    raised_on(stack, "spare")
    spare.reply(None, MOVE)
    spare.reply("Done what I could.")
    stack.say(SAID, person="ben")
    assert due_of(stack) == "2026-11-13"


def test_a_grade_counts_for_the_model_its_change_was_made_on(fallback_stack):
    """A critical grade of a change spare made lowers spare's cap, and leaves fake's: each
    model's grades are its own evidence."""
    stack, _, _ = fallback_stack
    levelled(stack)
    raised_on(stack, "spare")
    now = stack.gateway.clock()
    with db.transaction(stack.admin) as conn:  # a change spare made on its own, drawn
        assert samples.draw(conn, (SEAL_KEY,), "sample", "action", release_of(stack),
                            "assistant", "assistant-finance",
                            "00000000-0000-0000-0000-000000000001", "billing",
                            "change-due-date", "a change", {"Q-1002": None}, ["ben"], now,
                            model="spare")
        row = conn.execute("select * from samples where model = 'spare' and twin_of is null"
                           ).fetchone()
    assert row is not None and samples.drawn_by_core((SEAL_KEY,), row)  # sealed with its model
    with db.transaction(stack.admin) as conn:  # graded critical, after its cap was raised
        conn.execute("update samples set grade = 'critical', graded_by = 'dana', "
                     "graded_at = %s where id = %s", (now + timedelta(minutes=1), row["id"]))
    seal_grades(stack)
    with stack.client() as c:
        changed = c.post("/samples/sweep").json()["changed"]
    with db.transaction(stack.admin) as conn:
        keys, release = stack.gateway.cfg.seal_keys, release_of(stack)
        assert samples.caps(conn, keys, release, ["spare"]) == {("billing", "change-due-date"): 1}
        assert samples.caps(conn, keys, release, ["fake"]) == {("billing", "change-due-date"): 2}
    assert [c["why"] for c in changed] == ["a critical error"]


def test_lowering_a_cap_lowers_it_on_every_model(fallback_stack):
    stack, _, _ = fallback_stack
    levelled(stack)
    raised_on(stack, "spare")
    with stack.client() as c:
        r = c.post("/caps/lower", json={"agent": "assistant", "part": "billing",
                                        "action": "change-due-date", "by": "ana"})
    assert r.status_code == 200 and r.json()["lowered"]
    with db.transaction(stack.admin) as conn:
        keys, release = stack.gateway.cfg.seal_keys, release_of(stack)
        for model in ("fake", "spare"):
            assert samples.caps(conn, keys, release, [model]) == {
                ("billing", "change-due-date"): 1}, model


def test_an_instance_runs_on_the_model_its_settings_chose(fallback_stack):
    """The core checks each instance's record against its signed settings before each run: an
    instance its settings put on another approved model is expected on that model, not its
    release's, so it runs there rather than being refused every time (round 16)."""
    stack, _, _ = fallback_stack
    put_on(stack, "spare")
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "spare"


def test_the_preview_says_a_move_to_another_model_asks_first_there(fallback_stack):
    """A version that moves an instance acting on its own to a model that earned nothing says,
    before anyone approves it, that a5s holds it to asking first there."""
    from a5s.contract import parse_settings
    from a5s.core import impact

    stack, _, _ = fallback_stack
    levelled(stack)  # earned on fake
    folder = stack.cfg.scenario_dir
    before = parse_settings((folder / "settings.yaml").read_bytes())
    moved = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    moved["instances"]["assistant-finance"]["model"] = "spare"
    after = parse_settings(yaml.safe_dump(moved).encode())
    with db.transaction(stack.admin) as conn:
        def caps_of(release, model):
            return samples.caps(conn, stack.gateway.cfg.seal_keys, release,
                                [model] if model else None)

        assert impact.capped(stack.gateway, before, before, caps_of) == []
        [said] = impact.capped(stack.gateway, before, after, caps_of)
    assert said == ("assistant-finance moves to spare, which hasn't earned acting on its own "
                    "for change-due-date in billing: a5s holds it to asking first there until "
                    "graded samples on that model show it's accurate enough.")


def test_a_behaviour_changed_in_the_database_earns_nothing(fallback_stack):
    """Round 16, A4: the gateway's role could update behaviours, so a row for spare given the
    digest fake earned counted as earned on spare. Now the gateway works each behaviour out
    from the release it loaded, ignoring a row that disagrees, and may update only a row's
    model, which a row kept before models were named needs."""
    stack, _, _ = fallback_stack
    levelled(stack)  # earned on its own model, fake
    release = release_of(stack)
    with db.transaction(stack.admin) as conn:
        earned = samples.behaviour_of(conn, release, "change-due-date", "fake")
        conn.execute("update behaviours set behaviour = %s where release = %s and model = "
                     "'spare'", (earned, release))
        assert stack.gateway.caps(conn, release, ["spare"]) == {}  # nothing earned on spare
        assert stack.gateway.caps(conn, release, ["fake"]) == {("billing", "change-due-date"): 2}
    with db.transaction(stack.cfg.database_url) as conn:  # as the gateway's role
        privileges = {r["column_name"] for r in conn.execute(
            "select column_name from information_schema.column_privileges where table_name = "
            "'behaviours' and privilege_type = 'UPDATE' and grantee = current_user")}
    assert privileges == {"model"}
