"""Round 7: one agent asking another.

The worker that asks runs the run asked, so a question never waits on a worker another run
holds. The run asked sees no class of data the asking model may not see, its day is the
asker's, a run asks a few questions at most, and only what it read comes back as found, never
what it was asked, with outside staying outside. An agent that reports on records is given what
changed, and an agent knows what each it may ask does. Each test failed before round 7's fixes.
"""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest
import yaml

from a5s import db
from a5s.core import budgets, registry
from conftest import FAKE_MODELS, PROVIDER_KEY, QUIET, FakeModel, build_root, running, signed
from test_asking import ASKED, may_ask, questions
from test_groups import homeserver, mention  # noqa: F401  (a fixture)
from test_matrix import deliver


class RoleModel(FakeModel):
    """A model that answers by what it's asked, so runs can interleave: the agent asked answers
    at once; the asking agent asks, then words the answer once the tool comes back."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        msgs = body["messages"]
        if "asks you this" in json.dumps(msgs):  # the watcher, answering a question
            content, tools = "Nothing changed on Q-1001.", []
        elif msgs[-1]["role"] == "tool":
            content, tools = f"Told: {str(msgs[-1]['content'])[:80]}", []
        else:
            content, tools = None, [("ask_agent", {"agent": "watcher",
                                                   "question": "What changed on Q-1001?"})]
        message = {"role": "assistant", "content": content}
        if tools:
            message["tool_calls"] = [{"id": f"c{len(self.requests)}", "type": "function",
                                      "function": {"name": n, "arguments": json.dumps(a)}}
                                     for n, a in tools]
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if tools else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})


@pytest.fixture
def role_stack(database, tmp_path, monkeypatch):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = RoleModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def test_as_many_runs_asking_as_workers_still_get_their_answers(role_stack):
    """With one worker and one run that asks, or two and two, under the scheduler as deployed,
    every question is answered: the worker that asks runs the run asked (B1, A6, B4)."""
    stack = role_stack
    may_ask(stack)
    stack.scheduler().work_due()
    stop = threading.Event()
    loop = threading.Thread(target=stack.scheduler().listen, args=(stop,), daemon=True,
                            kwargs={"workers": 1, "sweep_every": 3600, "retain_every": 86400})
    loop.start()
    try:
        for person in ("ana", "ben"):
            stack.send("Ask the watcher what changed on Q-1001", person=person)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if len([q for q in questions(stack) if q["answered_at"]]) == 2:
                break
            time.sleep(0.2)
    finally:
        stop.set()
        loop.join(10)
    found = questions(stack)
    assert len(found) == 2 and all(q["answered_at"] and not q["problem"] for q in found)


@pytest.fixture
def two_models(database, tmp_path, monkeypatch):
    """The sample, with the watcher on a model approved for personal data, and the assistant
    on one that isn't, and customers' names classified as personal."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    models = FAKE_MODELS + (
        "  fake-personal:\n    provider: test\n    api: openai\n    base_url: https://fake.test/v1\n"
        "    model: fake-2\n    reported_model: fake-2\n    key_env: A5S_TEST_PROVIDER_KEY\n"
        "    data_classes: [synthetic, personal]\n")
    root = build_root(tmp_path, "fake", models)
    spec = root / "agents" / "watcher" / "agent.yaml"
    spec.write_text(spec.read_text().replace("model: fake\n", "model: fake-personal\n"))
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as stack:
        folder = stack.cfg.scenario_dir
        signed(folder, {**yaml.safe_load((folder / "settings.yaml").read_text()),
                        "classified": {"customer": "personal"}})
        scenario = stack.gateway.scenario
        with db.transaction(stack.admin) as conn:
            assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                      scenario.tools(), scenario.person, scenario.name).refused
        yield stack


def test_the_agent_asked_sees_nothing_the_asking_model_may_not(two_models):
    """The watcher's model may see customers' names, but its answer goes to the assistant's,
    which may not: so the watcher is given them as handles too (A2)."""
    stack = two_models
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": "Whose is Q-1001?"}))
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))  # the watcher reads it
    stack.model.reply("Q-1001 is a customer's question.")
    stack.model.reply("It's a customer's question.")
    stack.say("Whose is Q-1001?")
    [watched] = [r for r in stack.model.requests if r["body"]["model"] == "fake-2"
                 and r["body"]["messages"][-1]["role"] == "tool"]
    assert "Northwind" not in json.dumps(watched["body"]["messages"])


def test_a_value_the_asker_made_up_is_still_its_own_after_the_answer(stack):
    """The assistant puts its own date to the watcher, which repeats it: a5s still says the
    date is the assistant's own (A4)."""
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher",
                                           "question": "Is Q-1001 due on 2026-12-24?"}))
    stack.model.reply("Yes: Q-1001 is due on 2026-12-24.")  # the watcher, reading nothing
    stack.model.reply("Q-1001 is due on 2026-12-24.")
    reply = stack.say("When is Q-1001 due?")
    assert "(a5s: " in reply and "2026-12-24" in reply.split("(a5s: ")[1]


def test_a_decider_is_told_a_date_is_the_agents_own_though_it_asked_another(stack, approving):
    """The held change's flag isn't laundered away by asking first (A4)."""
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher",
                                           "question": "Can Q-1002 move to 2026-12-31?"}))
    stack.model.reply("Q-1002 can move to 2026-12-31.")
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-12-31"}))
    stack.model.reply("Asked for.")
    stack.say("Please push Q-1002 back a while.", person="ben")
    with db.transaction(stack.admin) as conn:
        [held] = conn.execute("select flags from proposals").fetchall()
    assert [f for f in held["flags"] if "2026-12-31 came from the assistant itself" in f]


def test_a_question_from_a_group_is_paid_for_by_whoever_asked_there(stack, homeserver):  # noqa: F811
    """Not by nobody, past everyone's spent day (A5, B5)."""
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": "What changed?"}))
    stack.model.reply("Nothing changed.")
    stack.model.reply("Nothing changed, says the watcher.")
    deliver(homeserver, mention("Ask the watcher what changed"))
    assert stack.scheduler().answer_waiting() == 1
    with db.transaction(stack.admin) as conn:
        spent = {r["person"]: r["tokens"] for r in conn.execute(
            "select person, tokens from spend where instance_id = 'watcher-finance'")}
    assert set(spent) == {"ana"}  # Ana asked, in the room
    assert budgets.payer(["ana", "ben"], {"kind": "question", "payer": "ana"}) == "ana"


def test_a_question_asked_when_its_askers_day_is_spent_is_refused(stack, homeserver):  # noqa: F811
    may_ask(stack)
    day = budgets.day_of(stack.gateway.scenario, "ana", QUIET)
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into spend (instance_id, person, day, tokens) values "
                     "('watcher-finance', 'ana', %s, 10000000)", (day,))
    stack.at(QUIET.isoformat())
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": "What changed?"}))
    stack.model.reply("The watcher can't answer today.")
    deliver(homeserver, mention("Ask the watcher what changed"))
    stack.scheduler().answer_waiting()
    [q] = questions(stack)
    assert q["answered_at"] is None and "budget" in q["problem"]


def test_a_run_asks_three_questions_at_most(stack):
    may_ask(stack)
    for n in range(4):
        stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": f"Question {n}?"}))
        if n < 3:
            stack.model.reply(f"Answer {n}.")
    stack.model.reply("Done.")
    stack.say(ASKED)
    assert len(questions(stack)) == 3
    assert "a run asks 3 questions at most" in json.dumps(stack.model.requests[-1]["body"])


def test_an_agent_that_reports_is_given_what_changed_when_its_asked(stack):
    """So "ask the watcher what changed" has something to answer from (C3)."""
    may_ask(stack)
    with stack.client() as c:  # what's open and due, from the records
        assert c.post("/obligations/sweep").status_code == 200
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Q-1001 is open, and due soon.")
    stack.model.reply("The watcher says Q-1001 is open, and due soon.")
    stack.say(ASKED)
    task = stack.model.requests[1]["body"]["messages"][-1]["content"]
    assert "What changed in their records since you last told them" in task
    assert "Q-1001" in task.split("worked out by code from the records:")[1]


def test_an_agent_knows_what_each_it_may_ask_does_and_only_those_that_work_for_them(stack):
    """And not one that doesn't work for everyone the run is for (C14)."""
    may_ask(stack, serves=("ana", "ben", "chen"), watcher_serves=("ana", "ben"))
    stack.model.reply("Hello.")
    stack.say("Hello")
    told = stack.model.requests[-1]["body"]["messages"][0]["content"]
    does = stack.gateway.definitions["watcher"].does.strip()
    assert f"- watcher: {does}" in told and "name the records it's about" in told
    stack.model.reply("Hello, Chen.")
    stack.say("Hello", person="chen")
    assert "Agents you may ask" not in stack.model.requests[-1]["body"]["messages"][0]["content"]
