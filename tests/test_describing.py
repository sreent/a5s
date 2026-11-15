"""Describe it (a5s/describing.py, docs/studio.md#describe-it): a new agent's first draft from its
author's words, given the least it needs. Whatever the model proposes, code makes the draft: only
what the scenario offers, each with a reason, at the lowest level that work needs, never 2; the
rest is left out, saying why. In the studio, the sandbox's model proposes, its stand-in included,
and the draft keeps its author's words and a note on each thing it was or wasn't given."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from a5s import authoring, db, definitions, describing
from a5s.connectors import mcp
from a5s.core import drafts
from a5s.service_desk import ServiceDeskScenario
from conftest import ROOT
from test_drafts import as_, recorded

DESK = ROOT / "scenarios" / "service-desk"


def desk_tools() -> dict:
    return mcp.served(ServiceDeskScenario(DESK, "postgresql://unused"), DESK).tools()


def blank(name: str = "joiner-coordinator") -> dict[str, str]:
    with tempfile.TemporaryDirectory() as there:
        made = authoring.new(authoring.templates(ROOT)[authoring.BLANK], name, Path(there), desk_tools(),
                             model="fake")
        return drafts.folder_files(made)


def given(notes: list[dict]) -> dict[str, str]:
    return {n["what"]: n["why"] for n in notes if n["given"]}


def left(notes: list[dict]) -> dict[str, str]:
    return {n["what"]: n["why"] for n in notes if not n["given"]}


def test_only_what_the_scenario_offers_each_with_a_reason_is_given():
    files, notes = describing.drafted(blank(), "joiner-coordinator", {
        "tools": [{"name": "search_records", "why": "to find a joiner's requests"},
                  {"name": "get_record", "why": ""},
                  {"name": "grant_admin", "why": "to set up their access"},
                  {"name": "search_records", "why": "again"}],
        "owed": [{"kind": "records", "why": "to chase what's owed by the start date"},
                 {"kind": "invoices", "why": "nothing here"}],
        "abilities": [{"name": "reminders", "why": "to remind the joiner"},
                      {"name": "agents", "why": "to ask the desk assistant"}],
        "autonomy": {"start": 2, "max": 2}, "schedules": [{"name": "nightly"}],
        "context": {"agents": True}, "works_for": "Hiring managers and new joiners",
        "does": "Tracks each joiner's requests against their start date.",
        "instructions": ["Chase what's owed.", "Answer the joiner's questions."]}, desk_tools(), ["records"])
    spec = yaml.safe_load(files["agent.yaml"])
    assert spec["tools"] == {"reads": ["search_records"]}
    assert spec["obligations"] == ["records"] and spec["reminders"] is True
    assert spec["autonomy"] == {"start": 1, "max": 1}  # what it writes needs 1, and never 2
    assert "schedules" not in spec or spec["schedules"] == [] and not spec["context"].get("agents")
    assert spec["works_for"] == "Hiring managers and new joiners"
    assert files["AGENTS.md"] == ("# joiner-coordinator\n\n- Chase what's owed.\n- Answer the joiner's "
                                  "questions.\n")
    assert given(notes)["search_records"] == "to find a joiner's requests"
    assert left(notes) == {"get_record": "the model gave no reason it needs it",
                           "grant_admin": "the scenario offers no such tool",
                           "invoices": "people owe nothing in such records here",
                           "agents": "it's no ability a description gives: add it by hand, if it needs it"}


def test_an_agent_that_only_reads_is_drafted_at_level_0():
    files, notes = describing.drafted(blank(), "reader", {
        "tools": [{"name": "get_record", "why": "to answer about a ticket"}]}, desk_tools(), ["records"])
    assert yaml.safe_load(files["agent.yaml"])["autonomy"] == {"start": 0, "max": 0}
    assert given(notes)["level 0 at most"].startswith("it only reads, which level 0 allows")


def test_a_change_it_asks_for_is_given_at_level_1_where_its_decider_decides_it():
    files, notes = describing.drafted(blank(), "replier", {
        "tools": [{"name": "reply_on_ticket", "why": "to post replies"}]}, desk_tools(), ["records"])
    spec = yaml.safe_load(files["agent.yaml"])
    assert spec["tools"] == {"changes": ["reply_on_ticket"]} and spec["autonomy"] == {"start": 1, "max": 1}
    assert "a change waits for its part's decider there" in given(notes)["level 1 at most"]
    assert "never 2" in given(notes)["level 1 at most"]


def test_what_it_drafts_passes_a5s_checks():
    files, _ = describing.drafted(blank(), "joiner-coordinator", {
        "tools": [{"name": "search_records", "why": "to find requests"},
                  {"name": "get_account", "why": "to see a joiner's account"}],
        "owed": [{"kind": "records", "why": "to chase"}]}, desk_tools(), ["records"])
    with tempfile.TemporaryDirectory() as there:
        folder = Path(there) / "joiner-coordinator"
        folder.mkdir()
        for path, text in files.items():
            (folder / path).write_text(text)
        tools = desk_tools()
        definitions.pin(folder, {n: t.schema_hash for n, t in tools.items()})
        assert authoring.check(folder, tools, {"fake": object()}) == []


def test_the_stand_in_thinks_nothing_and_gives_only_tools_that_read_whose_words_match():
    offered = describing.offer(desk_tools(), ["records"])
    body = describing.asked("openai", "stand-in", "Tracks new joiners' requests in the ITSM and answers "
                                                  "questions about their tickets.", offered)
    proposed = describing.stand_in(body)
    names = [t["name"] for t in proposed["tools"]]
    assert {"search_records", "get_record"} <= set(names)
    assert not {"reply_on_ticket", "reset_password", "reset_authenticators", "create_draft"} & set(names)
    assert all(t["why"].startswith("its words match yours:") for t in proposed["tools"])


def test_describing_it_in_the_studio_makes_a_draft_that_says_why(stack, with_sandbox, approving, provider):
    made = as_(approving, provider, "priya")("POST", "/studio/api/drafts", {
        "name": "question-finder", "describe": "Finds customer questions by what they mention, "
                                               "and answers about one.", "model": "stand-in"})
    assert made.status_code == 200, made.text
    draft = made.json()
    assert draft["based_on"] == "a description, on stand-in"
    assert draft["described"]["words"].startswith("Finds customer questions")
    names = {n["what"] for n in draft["described"]["notes"] if n["given"]}
    assert "search_records" in names and "change_due_date" not in names  # it changes due dates
    assert not draft["problems"], draft["problems"]
    [entry] = recorded(stack, "describe draft")
    assert entry["args"]["model"] == "stand-in" and "search_records" in entry["args"]["given"]
    with db.transaction(stack.admin) as conn:
        kept = conn.execute("select described from agent_drafts where id = %s::uuid", (draft["id"],)).fetchone()
    assert kept["described"]["notes"] == draft["described"]["notes"]
