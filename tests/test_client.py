"""The client for the core's API, which code, CI and the command line use (a5s/client.py)."""

import pytest

from a5s.client import Client, Refused
from conftest import SERVICE_TOKEN


def asked(stack, times: int) -> None:
    for n in range(times):
        stack.model.reply(f"Answer {n}.")
        stack.say(f"Question {n}?", person="ana")


def test_it_reads_the_agents_their_figures_and_their_runs(stack):
    asked(stack, 1)
    with Client(stack.url, SERVICE_TOKEN) as core:
        assert "assistant" in {a["id"] for a in core.agents()}
        assert core.agent("assistant")["instructions"]
        one = core.measures(7, instance="assistant-finance")
        assert one["instances"] == ["assistant-finance"] and one["days"] == 7
        assert core.measures(agent="assistant")["runs"] == one["runs"]
        assert core.measures()["runs"] == one["runs"] and core.status()["queue"]["waiting"] == 0
        [ran] = core.runs("assistant-finance")["runs"]
        assert core.run(ran["run"])["agent"] == "assistant"
        with pytest.raises(ValueError):
            core.measures(agent="assistant", instance="assistant-finance")


def test_it_pages_through_every_run(stack):
    asked(stack, 3)
    with Client(stack.url, SERVICE_TOKEN) as core:
        first = core.runs("assistant-finance", limit=2)
        assert len(first["runs"]) == 2
        rest = core.runs("assistant-finance", before=first["before"], limit=2)["runs"]
        assert len(rest) == 1
        every = list(core.each_run("assistant-finance", page=2))
    assert [r["run"] for r in every] == [r["run"] for r in first["runs"] + rest]


def test_a_refusal_says_why(stack):
    with Client(stack.url, "not-the-token") as core, pytest.raises(Refused) as refused:
        core.agents()
    assert refused.value.status == 401
    with Client(stack.url, SERVICE_TOKEN) as core, pytest.raises(Refused) as refused:
        core.agent("nobody")
    assert refused.value.status == 404 and "no agent nobody" in refused.value.detail


def test_it_finds_the_core_as_the_command_line_does(stack, monkeypatch):
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    with Client.from_env() as core:
        assert core.agents()
