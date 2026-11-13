"""Agent to agent. An instance's settings name the instances it may ask; a run asks one with
ask_agent, for the people it acts for. The core opens a run of the instance asked, acting for
the same people, within its own grant and what they may see, and writing to nobody: its answer
goes back to the run that asked, with its mark, and only what it had read counts as found. An
agent that's asked can't ask another (critique A9)."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.config import load_models
from a5s.contract import SettingsError, parse_settings
from a5s.core import approvals, asking
from conftest import ROOT, WATCHER, FakeModel, build_root, live_image, running

ASKED = "What changed on Q-1001 lately?"


def may_ask(stack, serves: tuple[str, ...] = ("ana", "ben"), asks: bool = True,
            watcher_serves: tuple[str, ...] | None = None) -> None:
    """The watcher, beside the assistant, which may ask it."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    instances = settings["instances"]
    instances["assistant-finance"]["serves"] = list(serves)
    if asks:
        instances["assistant-finance"]["asks"] = ["watcher-finance"]
    instances["watcher-finance"] = {**WATCHER, "serves": list(watcher_serves or serves)}
    assert not stack.settle(instances=instances).refused


@contextmanager
def questions_answered(stack) -> Iterator[None]:
    """Questions are answered by the worker that asks them, at once: nothing else runs."""
    yield


@pytest.fixture
def answering(stack):
    yield


def questions(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from questions order by asked_at").fetchall()


def runs(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select id::text, instance_id, acts_for, trigger, read_outside "
                            "from runs order by opened_at").fetchall()


def said(stack, request: int) -> str:
    """What the model was told last in a request: a tool's result, or why it failed."""
    return str(stack.model.requests[request]["body"]["messages"][-1]["content"])


def tool_result(stack, request: int) -> dict:
    return json.loads(said(stack, request))


def tools_offered(stack, request: int) -> list[str]:
    return [t["function"]["name"] for t in stack.model.requests[request]["body"].get("tools", [])]


def test_an_agent_asks_another_for_the_person_it_acts_for(stack, answering):
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Q-1001 hasn't changed since you were last told.")  # the watcher
    stack.model.reply("The watcher says Q-1001 hasn't changed lately.")
    assert stack.say(ASKED) == "The watcher says Q-1001 hasn't changed lately."
    [q] = questions(stack)
    assert (q["asker"], q["asked"], q["acts_for"], q["text"]) == (
        "assistant-finance", "watcher-finance", ["ana"], ASKED)
    assert q["answer"] == "Q-1001 hasn't changed since you were last told."
    task = asking.task(q)  # as an A2A task
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["history"][0]["parts"] == [{"text": ASKED}]
    assert task["artifacts"][0]["parts"] == [{"text": q["answer"]}]
    asker, asked = runs(stack)
    assert (asked["instance_id"], asked["acts_for"]) == ("watcher-finance", ["ana"])
    assert asked["trigger"]["by_run"] == asker["id"] == task["contextId"]
    assert tool_result(stack, 2) == {"agent": "watcher", "answer": q["answer"]}
    told = stack.model.requests[1]["body"]["messages"]  # what the watcher was asked
    assert "The assistant asks you this, for Ana Ortiz: " + ASKED in told[-1]["content"]
    assert "ask_agent" not in tools_offered(stack, 1)  # it can't ask on
    [answer] = [e for e in stack.ledger() if e["action"] == "answer"]
    assert answer["run"] == asked["id"] and answer["args"]["to_run"] == asker["id"]


def test_the_agent_asked_sees_only_what_the_people_asked_for_may_see(stack, answering):
    may_ask(stack, serves=("ana", "ben", "chen"))  # Chen, in operations, may not see billing
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": "Which questions "
                                                                           "mention an invoice?"}))
    stack.model.reply(None, ("search_records", {"query": "invoice"}))  # the watcher looks
    stack.model.reply("None that Chen may see.")
    stack.model.reply("The watcher found none.")
    stack.say("Which questions mention an invoice?", person="chen")
    found = tool_result(stack, 2)  # the watcher's search, for Chen
    assert "Q-1001" not in json.dumps(found)
    assert runs(stack)[-1]["acts_for"] == ["chen"]


def test_only_the_agents_the_settings_name_can_be_asked(stack, answering):
    may_ask(stack, asks=False)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("I can't ask it.")
    stack.say(ASKED)
    assert "ask_agent" not in tools_offered(stack, 0)  # it isn't offered: nothing reaches a5s
    assert "ask_agent is not a valid tool" in said(stack, 1) and questions(stack) == []


def test_an_agent_asked_must_work_for_everyone_the_question_is_for(stack, answering):
    may_ask(stack, serves=("ana", "ben", "chen"), watcher_serves=("ana", "ben"))
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("I can't ask it for you.")
    stack.say(ASKED, person="chen")
    assert "the watcher here doesn't work for everyone this run is for" in said(stack, 1)
    assert questions(stack) == []


def test_the_mark_follows_the_question_and_the_answer(stack, answering):
    may_ask(stack)

    def the_watcher_reads_outside(n: int) -> None:  # as if it had read a customer's email
        if n == 2:
            with db.transaction(stack.admin) as conn:
                conn.execute("update runs set read_outside = true "
                             "where trigger->>'kind' = 'question'")

    stack.model.on_request = the_watcher_reads_outside
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Nothing new.")
    stack.model.reply("Nothing new, says the watcher.")
    stack.say(ASKED)
    asker, asked = runs(stack)
    assert asked["read_outside"] and asker["read_outside"]  # its answer marks the asker
    assert "drew on content from outside" in tool_result(stack, 2)["note"]


def test_an_answer_goes_to_the_asking_agent_and_nobody_else(stack, answering):
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Nothing new.")
    stack.model.reply("Nothing new on Q-1001.")
    stack.say(ASKED)
    with db.transaction(stack.admin) as conn:
        sent = [r["text"] for r in conn.execute("select text from outbox order by id")]
    assert sent == ["Nothing new on Q-1001."]  # the assistant's answer, not the watcher's


def test_values_the_agent_asked_made_up_dont_count_as_found(stack, answering):
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Q-1001 is due on 2026-12-24.")  # without reading anything
    stack.model.reply("Q-1001 is due on 2026-12-24.")
    reply = stack.say(ASKED)
    assert "(a5s: " in reply and "2026-12-24" in reply.split("(a5s: ")[1]


def test_a_question_whose_run_fails_says_why_and_its_run_is_over(stack):
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.on_request = lambda n: setattr(stack.model, "failing", 1) if n == 2 else None
    stack.model.reply("The watcher didn't answer.")
    stack.say(ASKED)
    assert "the watcher didn't answer: its model isn't answering" in said(stack, -1)
    [q] = questions(stack)
    assert q["problem"] == "its model isn't answering"
    assert asking.task(q)["status"]["state"] == "TASK_STATE_FAILED"
    _, asked = runs(stack)
    with db.transaction(stack.admin) as conn:
        [closed] = conn.execute("select closed_at, outcome from runs where id = %s",
                                (asked["id"],)).fetchall()
    assert closed["closed_at"] is not None and closed["outcome"] == "model unavailable"


def test_settings_name_only_other_instances_to_ask_and_say_so_in_words(stack):
    raw = (stack.cfg.scenario_dir / "settings.yaml").read_text()
    settings = yaml.safe_load(raw)
    settings["instances"]["assistant-finance"]["asks"] = ["nobody-here"]
    with pytest.raises(SettingsError, match="isn't another instance"):
        parse_settings(yaml.safe_dump(settings).encode())
    before = parse_settings(raw.encode())
    settings["instances"]["assistant-finance"]["asks"] = ["watcher-finance"]
    settings["instances"]["watcher-finance"] = WATCHER
    after = parse_settings(yaml.safe_dump(settings).encode())
    said = approvals.changes(before, after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert {"text": "assistant-finance may ask the watcher (watcher-finance) questions, for the "
                    "people it acts for, which each answers from the records in its own parts "
                    "that those people may see.", "widens": True} in said


@pytest.mark.live
def test_a_real_model_asks_the_watcher_for_the_person(database, tmp_path):
    release = definitions.load(ROOT / "agents" / "assistant")
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel(), worker_image=live_image()) as stack:
        may_ask(stack)
        with questions_answered(stack):
            reply = stack.say("Ask the watcher whether anything changed on Q-1001 lately, and "
                              "tell me what it says.")
        print(f"--> {reply}")
        asked = [e for e in stack.ledger() if e["action"] == "ask_agent" and e["decision"] == "record"]
        assert asked and asked[-1]["outcome"]["status"] == "ok"
        [q] = questions(stack)
        assert q["answer"] and q["acts_for"] == ["ana"]
        assert stack.verify().ok
