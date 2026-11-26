"""Status: how a5s is doing, for the team that runs it, from the core's own records: the
queue, runs, denials, tokens, instances that aren't active, open breakers, and objectives."""

from a5s import db
from a5s.core import status


def test_the_team_sees_how_a5s_is_doing(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    stack.suspend(by="ben")
    assert stack.say("Hello again").startswith("The assistant is suspended")
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["queue"] == {"waiting": 0, "oldest_seconds": None}
    assert {(r["kind"], r["outcome"], r["n"]) for r in now["runs"]} == {("message", "done", 1)}
    assert {(d["kind"], d["action"]) for d in now["denied"]} == {("run", "open")}
    assert now["tokens"] == [{"instance": "assistant-finance", "tokens": 15, "budget_warnings": 0}]
    assert now["not_active"] == [{"id": "assistant-finance", "status": "suspended",
                                  "suspended_by": "ben"}]
    replies = now["objectives"]["replies"]
    assert replies["answered"] == 1 and replies["met"] and replies["p90_seconds"] < 120
    told = status.told(now)
    assert "Runs: 1 (message 1), ended done 1." in told
    assert "Not active: assistant-finance, suspended by ben." in told


def test_an_objective_missed_says_so(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:  # as if she waited ten minutes for it
        conn.execute("update inbound set received_at = received_at - interval '10 minutes'")
    with stack.client() as c:
        now = c.get("/status").json()
    assert not now["objectives"]["replies"]["met"]
    assert "(objective: nine in ten within 120s, missed)" in status.told(now)


def test_only_the_team_sees_it(stack):
    with stack.client("not the service token") as c:
        assert c.get("/status").status_code == 401


def test_nothing_to_measure_is_not_known_rather_than_met(stack):
    """With no answers, a5s can't say its replies are quick: every run may have failed."""
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["objectives"]["replies"]["met"] is None
    assert now["objectives"]["chases"]["met"] is None
    told = status.told(now)
    assert "Replies: none yet (objective: nine in ten within 120s, not known yet)." in told
    assert "Deliveries a chat didn't take: none." in told


def test_deliveries_a_chat_didnt_take_and_budget_warnings_show(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into outbox (person, channel, text, attempts, problem) values "
                     "('ana', 'teams', 'one', 2, 'teams said 502'), "
                     "('ana', 'local', 'two', 5, 'teams said 502')")
        conn.execute("insert into runs (id, instance_id, token_hash, trigger, acts_for, "
                     "expires_at, tokens) values (gen_random_uuid(), 'assistant-finance', 'x', "
                     "'{\"kind\": \"message\"}', '{ana}', now(), 900)")
        conn.execute("insert into spend (instance_id, person, day, tokens, warned_at) values "
                     "('assistant-finance', 'ana', current_date, 900, now())")
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["deliveries"] == {"retrying": 1, "left_in_inbox": 1, "kept_back": 0}
    assert now["tokens"] == [{"instance": "assistant-finance", "tokens": 900, "budget_warnings": 1}]
    told = status.told(now)
    assert ("Deliveries a chat didn't take: 1 being tried again, 1 left in people's local "
            "inbox.") in told
    assert "assistant-finance 900, 1 past four fifths" in told


# The verdict: what needs someone now, out of hours too, then what can wait for working hours,
# each with its runbook section, and the release a5s is, before the last day's lines

def test_a_calm_day_needs_nobody(stack):
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["needs"] == [] and now["models_stopped"] == []
    told = status.told(now)
    assert told.startswith("a5s: Nothing needs anyone.\n")
    assert "\na5s over the last day:\n" in told


def test_what_pages_comes_first_then_what_waits_for_working_hours(stack, monkeypatch):
    from dataclasses import replace

    from a5s.core import anchor, releases

    stack.suspend(by="ben")
    stack.scheduler().seen()  # the scheduler at work, as it is
    with db.transaction(stack.admin) as conn:  # a model the health gate stopped
        conn.execute("insert into model_health (scenario, model, day, calls, stalls, gated_at) "
                     "values ('sample', 'fake', current_date, 20, 11, now())")
    anchor.stuck(stack.admin, "the store refused to lock entry 7", stopped=True)
    current = releases.running(stack.cfg.root, stack.cfg.scenario_dir, stack.cfg.agents_dir)
    monkeypatch.setattr(stack.gateway, "releases", releases.Releases(current))
    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    with stack.client() as c:
        now = c.get("/status").json()
    assert [(n["when"], n["runbook"]) for n in now["needs"]] == [
        ("now", "docs/runbooks.md#the-ledgers-copies-stop"),
        ("working hours", "docs/runbooks.md#settings-or-the-release-dont-check-out"),
        ("working hours", "docs/runbooks.md#runs-fail-or-a-model-isnt-answering"),
        ("working hours", "docs/runbooks.md#an-instance-isnt-active")]
    assert now["release"]["approved"] is False and now["models_stopped"] == ["fake"]
    told = status.told(now).splitlines()
    assert told[0] == "a5s: 1 needs someone now, out of hours too and 3 can wait for working hours."
    assert told[1] == ("  Now: The ledger's copies have stopped until someone acts: the store "
                       "refused to lock entry 7. (docs/runbooks.md#the-ledgers-copies-stop)")
    assert told[2].startswith(f"  In working hours: Release {current.version} of a5s isn't "
                              "approved here:") and "So the core opens no run." in told[2]
    assert "`a5s health --restore fake`" in told[3]
    assert told[4].startswith("  In working hours: assistant-finance is suspended by ben")
    assert told[5] == (f"  Release {current.version} of a5s ({current.digest[:12]}), "
                       "not approved here.")
    assert "  Models the health gate stopped: fake." in told


def test_a_scheduler_that_stopped_asking_is_heard_of(stack):
    """The scheduler asks the core to record its status each minute (core/status_api.py): how
    long since it last did is in the status, as a figure too, and past three minutes, it may be
    away, which waits for working hours."""
    from a5s.core import metrics

    stack.scheduler().seen()
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["scheduler_seen_seconds"] < 60 and now["needs"] == []
    assert metrics.figures(now)["a5s.scheduler.seen.age"][0][0] < 60
    with db.transaction(stack.admin) as conn:
        conn.execute("update status_seen set at = now() - interval '7 minutes'")
    with stack.client() as c:
        now = c.get("/status").json()
    [late] = now["needs"]
    assert late["when"] == "working hours" and late["runbook"] == "docs/runbooks.md#messages-are-waiting"
    assert late["said"].startswith("The scheduler last asked the core to record how a5s is doing 7 minutes ago")


def test_settings_in_force_that_stop_counting_need_someone(stack, monkeypatch):
    """Once the settings in force stop counting, such as when their only approver moves on, the
    core refuses every run: the status says so too, where it said nothing (round 17, A1)."""
    from dataclasses import replace

    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=()))
    with stack.client() as c:
        now = c.get("/status").json()
    [need] = [n for n in now["needs"]
              if n["runbook"] == "docs/runbooks.md#settings-or-the-release-dont-check-out"]
    assert "aren't approved" in need["said"] and need["said"].endswith("So the core opens no run.")
    assert status.verdict(now) != "Nothing needs anyone."


def test_a_scheduler_that_never_asked_is_heard_of_and_its_record_never_runs_ahead(stack,
                                                                                monkeypatch):
    """A scheduler that never reached the core, such as with another token, leaves no record,
    which outside development needs someone too; and the record is never ahead of the
    database's clock, so nobody hides the scheduler's being away (round 17, D5)."""
    from dataclasses import replace

    monkeypatch.setattr(stack.gateway, "cfg", replace(stack.gateway.cfg, development=False))
    with stack.client() as c:
        now = c.get("/status").json()
    assert any(n["runbook"] == "docs/runbooks.md#messages-are-waiting"
               and n["said"].startswith("The scheduler has never asked") for n in now["needs"])
    stack.scheduler().seen()
    with db.transaction(stack.admin) as conn:
        conn.execute("update status_seen set at = now() + interval '10 years'")
        assert conn.execute("select at <= now() as held from status_seen").fetchone()["held"]


def test_an_expiry_note_mistyped_stops_nothing_and_is_said(stack, monkeypatch):
    """A5S_EXPIRES is only a note of when credentials expire: one mistyped is a warning as a
    part starts, and a line in the status, never a core that won't start (round 17, A12)."""
    from a5s import config

    monkeypatch.setenv("A5S_EXPIRES", "teams-secret-assistant=2027-5-1")
    problems, warnings = config.check()
    assert not [p for p in problems if "A5S_EXPIRES" in p]
    assert [w for w in warnings if "A5S_EXPIRES" in w]
    with stack.client() as c:
        now = c.get("/status").json()
    assert [n["runbook"] for n in now["needs"]] == ["docs/runbooks.md#credentials-that-expire"]
