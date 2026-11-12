"""Round 10: the scheduler's slots in each worker pool, and its drain when asked to stop
(services/scheduler.py). A moment's database error costs a claim, never its pool's slot; a pool
keeps one of its slots for people's messages, which work that falls due never takes; and
asked to stop, the scheduler takes nothing more that falls due."""

from __future__ import annotations

import threading
import time
from dataclasses import replace

import psycopg

from test_task_runs import a_task


def until(check, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.2)
    return bool(check())


def listening(scheduler, stop: threading.Event, **kwargs) -> threading.Thread:
    thread = threading.Thread(target=scheduler.listen, args=(stop,), kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def test_a_claim_the_database_fails_gives_its_slot_back(stack):
    """A moment's database error as the scheduler claims a message, as in a failover or with
    every connection in use, costs that claim alone, and the slot goes back to its pool."""
    stack.model.reply("Hello, once the database was back.")
    scheduler = stack.scheduler()
    scheduler.due = list  # no sweeps, only messages
    real, failing = scheduler._claim, [1]

    def claim(*args, **kwargs):
        if failing:
            failing.pop()
            raise psycopg.OperationalError("the database went away for a moment")
        return real(*args, **kwargs)

    scheduler._claim = claim
    stop = threading.Event()
    thread = listening(scheduler, stop, workers=1, sweep_every=3600)
    try:
        assert until(lambda: not failing, 10)  # the one failed claim happened
        message = stack.send("Hello")
        assert until(lambda: stack.answers(message), 25), (
            "the message was never answered: the failed claim kept the pool's only slot")
    finally:
        stop.set()
        thread.join(30)


def test_a_due_item_whose_lease_the_database_fails_gives_its_slot_back(stack):
    """The same in the sweeps: a database error taking the lease of something due, such as
    a task's next slice, gives its slot back, so what falls due next is worked on."""
    worked: list[dict] = []
    scheduler = stack.scheduler()
    item = {"kind": "reminder", "reminder": 1, "person": "ana", "agent": "assistant",
            "instance": "assistant-finance"}
    scheduler.due = lambda: [dict(item)]
    real, failing = scheduler._take, [1]

    def take(claim):
        if failing:
            failing.pop()
            raise psycopg.OperationalError("the database went away for a moment")
        return real(claim)

    scheduler._take = take
    scheduler._answer = lambda claim: worked.append(claim)  # what it would work on
    stop = threading.Event()
    thread = listening(scheduler, stop, workers=1, sweep_every=0.5)
    try:
        assert until(lambda: worked, 10), (
            "nothing due was worked on again: the failed lease kept the pool's only slot")
    finally:
        stop.set()
        thread.join(30)


def test_a_scheduler_asked_to_stop_takes_nothing_more_that_falls_due(stack):
    """Asked to stop, as before an upgrade, the scheduler takes no more work, even what its
    sweep found due as it was asked, and only finishes what it has in flight."""
    worked: list[dict] = []
    stop = threading.Event()
    scheduler = stack.scheduler()

    def due():  # SIGTERM arrives while the sweeps ask the core what's due, as they often are
        stop.set()
        return [{"kind": "reminder", "reminder": 1, "person": "ana", "agent": "assistant",
                 "instance": "assistant-finance"}]

    scheduler.due = due
    scheduler._answer = lambda claim: worked.append(claim)
    thread = listening(scheduler, stop, workers=2, sweep_every=3600)
    thread.join(30)
    assert not thread.is_alive()
    assert worked == [], "it started new work after it was asked to stop"


def test_a_tasks_slices_never_hold_up_its_owners_own_chat(stack):
    """phase-4.md: "a task at work never holds up its owner's own chat". A pool keeps one of
    its slots for people's messages, which work that falls due never takes: so with two tasks'
    slices at work in the assistant's two slots, Ana's message is still answered. (A pool with
    one slot has none to keep, which the docs say.)"""
    a_task(stack)
    a_task(stack)
    release = threading.Event()
    stack.model.reply("Hello, Ana.")
    slices: list[str] = []

    def pool(url: str, token: str, history: list[dict]) -> str:
        if history and str(history[-1].get("content", "")).startswith("Work on "):
            slices.append(token)
            release.wait(30)  # a slice, at work for a while, as a long task's are
            return ""
        from a5s.worker import run_agent
        return run_agent(url, token, history)

    scheduler = stack.scheduler(pools={"assistant": pool})
    scheduler.cfg = replace(scheduler.cfg, worker_slots={"assistant": 2})
    stop = threading.Event()
    thread = listening(scheduler, stop, workers=2, sweep_every=3600)
    try:
        time.sleep(3)  # the first sweep takes a task's slice, and leaves the other slot
        assert len(slices) == 1, slices
        message = stack.send("Hello")
        answered = until(lambda: stack.answers(message), 10)
        assert answered, "Ana's own chat waited for her tasks' slices"
    finally:
        release.set()
        stop.set()
        thread.join(30)
