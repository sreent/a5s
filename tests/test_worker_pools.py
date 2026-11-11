"""Worker pools (docs/architecture.md): each agent with a pool of its own runs there alone,
and every other agent in the shared pool. The scheduler sends each run to its agent's pool,
and gives each pool slots of its own, so no agent's runs, however slow, take the slots
another's need. Each pool refuses a run that isn't its own, so a run sent to the wrong one
fails, and says so, rather than run where it shouldn't."""

import signal
import threading
import time
from dataclasses import replace

import httpx
import pytest

from a5s import cli, worker
from a5s.config import names, pools
from a5s.services.scheduler import Slots, remote_worker
from conftest import free_port, serve


def test_each_agent_runs_in_its_own_pool_and_any_other_in_the_shared_one(stack):
    stack.model.reply("Hello from the assistant's own pool.")
    stack.model.reply("Hello from the shared pool.")
    own = worker.create_app(stack.url, agents=frozenset({"assistant"}))
    shared = worker.create_app(stack.url, pooled=frozenset({"assistant"}))  # it refuses the
    watchers = worker.create_app(stack.url, agents=frozenset({"watcher"}))  # assistant
    with serve(own, free_port()) as own, serve(shared, free_port()) as shared, \
            serve(watchers, free_port()) as watchers:
        pooled = stack.scheduler(worker=remote_worker(shared),
                                 pools={"assistant": remote_worker(own)})
        assert stack.say("Hi", scheduler=pooled) == "Hello from the assistant's own pool."
        elsewhere = stack.scheduler(worker=remote_worker(own),  # the assistant has no pool here
                                    pools={"watcher": remote_worker(watchers)})
        assert stack.say("Hi again", scheduler=elsewhere) == "Hello from the shared pool."


def test_a_pool_refuses_a_run_that_isnt_its_own(stack):
    _, token = stack.open_run()  # the assistant's
    for app, why in ((worker.create_app(stack.url, agents=frozenset({"watcher"})),
                      "this pool runs the watcher, not the assistant"),
                     (worker.create_app(stack.url, pooled=frozenset({"assistant"})),
                      "the assistant runs in a pool of its own, not the shared one")):
        with serve(app, free_port()) as url:
            r = httpx.post(f"{url}/work", json={"token": token, "history": []}, timeout=30)
        assert (r.status_code, r.json()) == (409, {"error": "wrong_pool", "detail": why})
    assert stack.model.requests == []  # neither ran it


def test_a_run_sent_to_the_wrong_pool_fails_and_says_so(stack):
    shared = worker.create_app(stack.url, pooled=frozenset({"assistant"}))
    with serve(shared, free_port()) as url:
        stack.say("Hi", scheduler=stack.scheduler(worker=remote_worker(url)))  # no pool for it
    closed = [e["outcome"] for e in stack.ledger() if e["kind"] == "run" and e["action"] == "close"]
    assert closed == ["failed"] and stack.model.requests == []


def test_each_pool_claims_only_its_own_agents_messages(stack):
    stack.send("Hello assistant")
    stack.send("Hello watcher", agent="watcher")
    scheduler = stack.scheduler()
    assert scheduler._claim("watcher")["agent"] == "watcher"
    assert scheduler._claim(None, frozenset({"assistant"})) is None  # the shared pool's: none
    assert scheduler._claim("assistant")["agent"] == "assistant"


def test_no_agent_takes_the_slots_another_needs():
    slots = Slots(2, {"assistant": 1})
    assert slots.pool("assistant") == "assistant" and slots.pool("watcher") is None
    assert slots.take("assistant") and not slots.take("assistant")  # its one slot is busy
    assert slots.take(None) and slots.take(None) and not slots.take(None)  # the others' are
    slots.give("assistant")  # theirs alone
    assert slots.take("assistant") and slots.total == 3 and slots.pools() == ["assistant", None]


def test_slots_hold_when_many_take_at_once():
    slots, taken = Slots(0, {"assistant": 5}), []

    def take() -> None:
        taken.append(slots.take("assistant"))

    threads = [threading.Thread(target=take) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert taken.count(True) == 5


def test_each_agents_pool_comes_from_the_environment():
    assert pools("assistant=http://a5s-worker-assistant:8702/, watcher=http://w:8702") == {
        "assistant": "http://a5s-worker-assistant:8702", "watcher": "http://w:8702"}
    assert pools("") == {} and names(" assistant, ,watcher ") == {"assistant", "watcher"}
    with pytest.raises(ValueError, match="isn't an agent and its pool's"):
        pools("assistant")


def test_an_agent_whose_runs_hang_never_holds_up_another_agents(stack):
    release, stop = threading.Event(), threading.Event()

    def hung(_url: str, _token: str, _history: list[dict]) -> str:  # the assistant's pool
        release.wait(30)
        return "Sorry for the wait."

    stack.with_watcher()
    stack.model.reply("Hello from the watcher.")
    scheduler = stack.scheduler(pools={"assistant": hung})  # the watcher runs in the shared one
    scheduler.cfg = replace(scheduler.cfg, worker_slots={"assistant": 1})
    first, second = stack.send("Hello", "ana"), stack.send("Hello", "ben")  # two of its runs
    asked = stack.send("Hello", "ana", agent="watcher")
    listening = threading.Thread(target=scheduler.listen, args=(stop,),
                                 kwargs={"workers": 2, "sweep_every": 3600}, daemon=True)
    listening.start()
    try:
        deadline = time.monotonic() + 30
        while not stack.answers(asked) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert stack.answers(asked) == ["Hello from the watcher."]  # while its pool is stuck,
        assert not stack.answers(first) and not stack.answers(second, "ben")  # one slot at a time
    finally:
        release.set()
        stop.set()
        listening.join(30)


def test_a_scheduler_asked_to_stop_finishes_its_runs_and_takes_no_more(stack):
    started, release = threading.Event(), threading.Event()

    def slow(_url: str, _token: str, _history: list[dict]) -> str:
        started.set()
        release.wait(30)
        return "Answered before it stopped."

    first = stack.send("Hello", "ana")
    scheduler, stop = stack.scheduler(worker=slow), cli._stopping()
    listening = threading.Thread(target=scheduler.listen, args=(stop,),
                                 kwargs={"workers": 2, "sweep_every": 3600}, daemon=True)
    try:
        listening.start()
        assert started.wait(30)
        signal.raise_signal(signal.SIGTERM)  # as Kubernetes asks a pod to stop
        assert stop.is_set()
        second = stack.send("Hello", "ben")  # for the next scheduler
        release.set()
        listening.join(30)
        assert not listening.is_alive()
        assert stack.answers(first) == ["Answered before it stopped."]
        assert stack.answers(second, "ben") == []
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        release.set()
        stop.set()
