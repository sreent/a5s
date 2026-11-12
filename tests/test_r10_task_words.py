"""Round 10: what tasks and reads of the audit trail keep, and who may read or change it.

A slice's run keeps only what it said the slice came to, once the slice ends: what it found
and what it needed are the task's, and go with it (core/tasking.py's end). The agent's list of
someone's tasks and repeats, and their page's list of repeats, show only how one stands when
its words name a record they may no longer see. The channels app's role only cancels a task
and stops a repeat, and reads nothing a repeat's offer read (migration 0054_task_words.sql).
A read of the trail says through what it came, and whom it asked about only as a stand-in."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import psycopg
import pytest

from a5s import db
from a5s.core import audit, erasure, export, retention
from a5s.core.tasks import TaskService, TaskSpec
from test_task_page import signed_in
from test_task_repeats import THURSDAY, asked_for, repeats_of
from test_task_runs import ASKED, a_task, tasks_of

FOUND = "Ana's refund for her daughter's school trip waits on finance"
NEEDS = "Ana, which of your two bank accounts should the refund go to?"
UNSEEN = "Chase Q-1003 for me, and its delivery date for order 7781"  # orders: not Ana's to see
AUDITOR = "kofi"


def slices_said(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return [r["task_result"] for r in conn.execute(
            "select task_result from runs where task_result is not null order by opened_at")]


def worked_on(stack) -> dict:
    """Ana's task: blocked on her, she says what it needs, and then done."""
    task = a_task(stack)
    stack.model.reply(None, ("finish_task", {"status": "blocked", "reason": NEEDS,
                                             "partial": FOUND}))
    stack.model.reply("Ana, I need to know which account the refund goes to.")
    assert stack.scheduler().work_due() == 1
    stack.model.reply(None, ("resume_task", {"task": f"T-{task['number']}",
                                             "answer": "the one ending 42"}))
    stack.model.reply("Thanks, I'll go on with it.")
    stack.say("Use the one ending 42")
    stack.model.reply(None, ("finish_task", {"status": "done", "result": FOUND}))
    stack.model.reply("Ana, your task is done.")
    assert stack.scheduler().work_due() == 1
    return task


# A2/C3: a slice's run keeps what the slice came to, and none of its words

def test_a_slices_run_keeps_only_what_the_slice_came_to(stack):
    task = worked_on(stack)
    assert slices_said(stack) == [{"status": "blocked"}, {"status": "done"}]
    with db.transaction(stack.admin) as conn:
        given = export.gather(conn, "ana")
    [mine] = given["tasks"]  # what it found is the task's, in her export
    assert (mine["number"], mine["result"]) == (task["number"], FOUND)


def test_erasing_someone_or_retention_leaves_none_of_what_their_tasks_runs_said(stack):
    worked_on(stack)
    with db.transaction(stack.admin) as conn:
        gone, _ = erasure.erase(conn, "ana", stack.gateway.clock())
    assert gone.get("tasks") == 1 and tasks_of(stack) == []
    assert FOUND not in str(slices_said(stack)) and NEEDS not in str(slices_said(stack))


def test_retention_lets_go_of_a_task_and_its_runs_keep_none_of_its_words(stack):
    worked_on(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("update tasks set updated_at = now() - interval '13 months', "
                     "deadline = now() - interval '13 months'")
        gone = retention.sweep(conn, stack.gateway.clock() + timedelta(days=400),
                               stack.gateway.scenario.name)
    assert gone.get("tasks") == 1 and tasks_of(stack) == []
    assert all(set(said) == {"status"} for said in slices_said(stack))


def test_her_export_says_why_a_task_stopped(stack):
    a_task(stack, days=1)
    stack.at((stack.gateway.clock() + timedelta(days=2)).isoformat())
    stack.scheduler().work_due()  # past its deadline, it ends
    with db.transaction(stack.admin) as conn:
        [mine] = export.gather(conn, "ana")["tasks"]
    assert (mine["status"], mine["last_error"]) == ("failed", "its deadline passed")


# A9/C12: a task or repeat whose words name a record they may not see shows how it stands alone

def test_the_agent_lists_a_task_naming_a_record_they_may_not_see_as_it_stands_alone(stack):
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task=UNSEEN,
                          token_budget=40_000, deadline=stack.gateway.clock() + timedelta(days=1)))
    with db.transaction(stack.admin) as conn:  # and a repeat of the same words
        conn.execute("insert into task_repeats (id, instance_id, owner, task, days, at, "
                     "status) values (%s, 'assistant-finance', 'ana', %s, '{mon}', '{09:00}', "
                     "'active')", (str(uuid.uuid4()), UNSEEN))
    stack.model.reply(None, ("list_tasks", {}))
    stack.model.reply("You have one task, and one that repeats.")
    stack.say("What tasks do I have?")
    listed = str(stack.model.requests[-1]["body"]["messages"][-1]["content"])
    assert '"tasks"' in listed and '"repeats"' in listed and "withheld" in listed
    assert "Q-1003" not in listed and "7781" not in listed


def test_her_page_shows_a_repeat_naming_a_record_she_may_not_see_as_it_stands_alone(
        stack, approving, provider):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into task_repeats (id, instance_id, owner, task, days, at, "
                     "status) values (%s, 'assistant-finance', 'ana', %s, '{mon}', '{09:00}', "
                     "'active')", (str(uuid.uuid4()), UNSEEN))
    [repeat] = signed_in(approving, provider)("/tasks/api").json()["repeats"]
    assert repeat["withheld"] is True and "Q-1003" not in str(repeat)
    assert repeat["status"] == "active" and repeat["when"]  # how it stands


# A6/C13: the channels app's role cancels a task and stops a repeat, and nothing else

def as_channels(stack, sql: str, params: tuple = ()) -> int | None:
    """What the channels app's role does: how many rows it changed, or None if refused."""
    try:
        with db.transaction(db.as_role(stack.admin, "channels")) as conn:
            return conn.execute(sql, params).rowcount
    except psycopg.errors.InsufficientPrivilege:
        return None


def test_the_channels_role_cant_set_an_offer_going(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED}))
    stack.model.reply("I can take that on as a task: shall I start it?")
    stack.say("Could you go through all my open questions and say what each waits on?")
    assert as_channels(stack, "update tasks set status = 'queued' where status = 'offered'") \
        is None
    assert tasks_of(stack)[0]["status"] == "offered"


def test_the_channels_role_cant_lapse_a_lease_or_put_a_task_off(stack):
    a_task(stack)
    assert as_channels(stack, "update tasks set lease_expires_at = now() - interval '1 hour'") \
        is None
    assert as_channels(stack, "update tasks set not_before = now() + interval '1 year'") is None
    assert as_channels(stack, "update tasks set status = 'cancelled'") == 1  # what it may do


def test_the_channels_role_cant_set_a_stopped_repeat_going_again(stack):
    asked_for(stack)
    stack.model.reply(None, ("cancel_task", {"task": "E-1"}))
    stack.model.reply("I've stopped E-1.")
    stack.say("Stop E-1 please")
    assert repeats_of(stack)[0]["status"] == "stopped"
    assert as_channels(stack, "update task_repeats set status = 'active'") is None
    stack.at(THURSDAY)
    stack.scheduler().work_due()
    assert tasks_of(stack) == []


def test_the_channels_role_reads_none_of_what_a_repeats_offer_read(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}),
                      ("offer_task", {"task": "Chase Q-1001 for me", "days": ["monday"]}))
    stack.model.reply("Shall I chase Q-1001 every Monday?")
    stack.say("Could you chase Q-1001 every Monday?")
    assert repeats_of(stack)[0]["reads"]  # kept with the repeat, for its tasks
    with (pytest.raises(psycopg.errors.InsufficientPrivilege),
          db.transaction(db.as_role(stack.admin, "channels")) as conn):
        conn.execute("select reads from task_repeats").fetchall()


# A4/C9: a read of the trail says through what it came, and whom it asked about as a stand-in

def test_a_read_through_the_service_token_says_so(stack):
    with stack.client() as c:  # the team's token, naming the auditor
        assert c.get("/audit/entries", params={"by": AUDITOR, "person": "ben"}).status_code == 200
    [read] = [e for e in stack.ledger() if e["kind"] == "audit"]
    assert (read["args"]["by"], read["args"]["through"]) == (AUDITOR, "the service token")
    hashed = {hashlib.sha256(p.encode()).hexdigest() for p in ("ana", "ben", "kofi", "priya")}
    assert read["args"]["person"].startswith(audit.STAND_IN)  # no hash of an id finds whom
    assert not any(h in str(read["args"]) for h in hashed)


def test_a_read_with_the_auditors_own_sign_in_is_theirs(stack, approving, provider):
    token = provider.id_token(person=AUDITOR)
    with stack.client() as c:
        mine = c.get("/audit/entries", params={"by": "priya"},  # whom it names doesn't count
                     headers={"X-A5S-Identity": token})
        refused = c.get("/audit/entries", params={"by": AUDITOR},
                        headers={"X-A5S-Identity": provider.id_token(person="chen")})
    assert mine.status_code == 200 and refused.status_code == 403
    [read] = [e for e in stack.ledger() if e["kind"] == "audit"]
    assert (read["args"]["by"], read["args"]["through"]) == (AUDITOR, "their sign-in")


# C8: a decider refused for want of a second factor is told whom to ask, and a5s counts it

def test_a_decider_refused_for_a_second_factor_is_told_whom_to_ask_and_its_counted(
        stack, approving, provider):
    from a5s.core import status
    from test_mfa import PASSWORD, asking
    from test_proposals import asked, decide, held

    asking(stack)  # amr:mfa, as the chart asks of Entra ID
    asked(stack)
    [p] = held(stack)
    provider.claims = PASSWORD  # the organisation's policy didn't ask her for one
    refusals = [decide(approving, provider, [p["digest"]]) for _ in range(2)]
    assert all(r.status_code == 401 for r in refusals)
    said = refusals[0].json()["detail"]
    assert "signing in again won't change that" in said and "your IT team" in said
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["sign_ins"]["refused"] == {"approve": 2}
    assert "Refused for want of a second factor: approve 2" in status.told(now)


def test_pages_ask_the_provider_for_the_level_what_counts_needs(stack, approving):
    from dataclasses import replace

    import httpx

    assert "acr_values" not in httpx.get(f"{approving}/approve/config", timeout=30).json()[
        "signin"]  # amr's, which only the provider's own policy asks for
    stack.gateway.identity.cfg = replace(stack.gateway.identity.cfg, mfa=("acr", ("gold",)))
    signin = httpx.get(f"{approving}/approve/config", timeout=30).json()["signin"]
    assert signin["acr_values"] == "gold"


def test_the_status_counts_tasks(stack):
    from a5s.core import status
    from test_task_runs import a_task

    a_task(stack)
    a_task(stack)
    with stack.client() as c:
        now = c.get("/status").json()
    assert (now["tasks"]["due"], now["tasks"]["at_work"], now["tasks"]["blocked"]) == (2, 0, 0)
    assert "Tasks: 0 at work, 2 due" in status.told(now)
