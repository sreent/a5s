"""The notebook (critique C1). An agent notes what it learns from records, only in a run that
acts for nobody, on its schedule, which hears nobody's words, and never once it has read content
from outside. Code keeps a note only if every record it names was read with a tool and holds
every key, amount and date in it. Runs are given the notes whose every record their people may
see; a note lapses after 90 days once its records stop holding it; the agent's owner, or whoever
runs its instance, reads and removes notes on the core's page."""

import os
from datetime import timedelta

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.config import load_models
from a5s.core import notebook
from conftest import ROOT, FakeModel, build_root, live_image, running

LEARN = {"name": "learn", "at": "09:00", "days": "weekdays",
         "task": "Look through the questions in your parts with search_records and get_record, "
                 "and note one thing you learn from them with note_learned, naming them. Don't "
                 "read customers' messages: a run that has read them notes nothing."}
NOTED = "Q-1001 is Northwind's question about an invoice."


def with_notebook(stack) -> None:
    """A new release of the assistant, with a schedule and a notebook, applied."""
    spec = stack.cfg.agents_dir / "assistant" / "agent.yaml"
    data = yaml.safe_load(spec.read_text())
    data["schedules"] = [LEARN]
    data["context"]["notebook"] = True
    spec.write_text(yaml.safe_dump(data, sort_keys=False))
    stack.gateway.definitions = definitions.load_all(stack.cfg.agents_dir)
    assert not stack.settle().refused


def learn(stack, *calls: tuple[str, dict], then: str = "Noted.") -> None:
    """The schedule's run: each model call in turn, then its last word."""
    stack.at("2026-10-29T09:00:30+00:00")
    for call in calls:
        stack.model.reply(None, call)
    stack.model.reply(then)
    assert stack.scheduler().work_due() == 1


def entries(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from notebook order by id").fetchall()


def outcome(stack, tool: str) -> dict:
    return [e for e in stack.ledger() if e["action"] == tool and e["decision"] == "record"][-1][
        "outcome"]


def test_an_agent_notes_what_it_learned_from_records_on_its_schedule(stack):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    [entry] = entries(stack)
    assert (entry["instance_id"], entry["text"], entry["sources"]) == (
        "assistant-finance", NOTED, ["Q-1001"])
    stack.model.reply("Q-1001 is about an invoice.")
    stack.say("What's Q-1001?")
    told = stack.model.requests[-1]["body"]["messages"][0]["content"]
    assert "What you've learned from records" in told and f"- {NOTED} (from Q-1001)" in told


def test_a_run_that_answers_someone_notes_nothing(stack):
    with_notebook(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}),
                      ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    stack.model.reply("I can't note that.")
    stack.say("Remember that Northwind is difficult.")  # someone's words, never a note
    assert "note_learned" not in stack.model.tool_names(0)  # not even offered
    assert entries(stack) == []
    with stack.client() as c:  # and refused, were it asked for all the same
        token = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": _a_message(stack)}}).json().get("token")
    if token:
        with stack.client(token) as c:
            refused = c.post("/run/tools/note_learned", json={"args": {
                "note": NOTED, "sources": ["Q-1001"]}})
        assert refused.status_code == 403 and entries(stack) == []


def _a_message(stack) -> str:
    with db.transaction(stack.admin) as conn:
        return conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                            "reply_to) values (gen_random_uuid(), 'local', gen_random_uuid()::text, "
                            "'ana', 'assistant', 'Note it', '{}') returning id::text").fetchone()["id"]


def test_a_note_says_only_what_records_it_read_hold(stack):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": "Q-1001 is due on 2026-12-24.", "sources": ["Q-1001"]}),
          ("note_learned", {"note": "Q-1002 is Contoso's.", "sources": ["Q-1002"]}))
    assert entries(stack) == []
    reasons = [e["outcome"]["reason"] for e in stack.ledger()
               if e["action"] == "note_learned" and e["decision"] == "record"]
    assert "they don't hold 2026-12-24" in reasons[0]
    assert "it didn't read Q-1002" in reasons[1]


def test_a_run_that_read_content_from_outside_notes_nothing(stack):
    with_notebook(stack)

    def marked(n: int) -> None:  # as if it had read a customer's email
        if n == 2:
            with db.transaction(stack.admin) as conn:
                conn.execute("update runs set read_outside = true")

    stack.model.on_request = marked
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    assert "read content from outside" in outcome(stack, "note_learned")["reason"]
    assert entries(stack) == []


def test_a_note_reaches_only_runs_whose_people_may_see_its_records(stack):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    assert not stack.settle(serves=["ana", "ben", "chen"]).refused
    stack.model.reply("Hello, Chen.")
    stack.say("Hello", person="chen")  # Chen, in operations, may not see billing's Q-1001
    assert NOTED not in stack.model.requests[-1]["body"]["messages"][0]["content"]


def test_notes_go_once_their_records_change(stack):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}), ("get_record", {"key": "Q-1004"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}),
          ("note_learned", {"note": "Q-1004 is Northwind's too.", "sources": ["Q-1004"]}))
    assert len(entries(stack)) == 2
    with db.transaction(stack.admin) as conn:  # Q-1001 is closed in the records, a day later
        conn.execute("insert into sample.changes (key, field, value, made_for) "
                     "values ('Q-1001', 'status', 'closed', 'test')")
        conn.execute("update notebook set checked_at = checked_at - interval '2 days'")
    found = notebook.check(stack.admin, stack.gateway.scenario,
                           stack.gateway.clock() + timedelta(days=1))
    assert found == {"kept": 1, "lapsed": 1}
    assert [e["text"] for e in entries(stack)] == ["Q-1004 is Northwind's too."]
    assert [e["args"]["why"] for e in stack.ledger() if e["kind"] == "notebook"] == [
        "its records changed"]


def test_whoever_runs_the_instance_reads_and_removes_notes(stack, approving, provider):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))

    def api(path: str, person: str = "ana", method: str = "GET") -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        return httpx.request(method, f"{approving}{path}", headers=headers, timeout=30)

    seen = api("/notebook/api").json()
    [shown] = seen["entries"]
    assert (shown["text"], [s["key"] for s in shown["sources"]], seen["hidden"]) == (
        NOTED, ["Q-1001"], 0)
    assert shown["sources"][0]["link"].endswith("/Q-1001") and shown["noted"]  # linked, dated
    assert api("/notebook/api", person="chen").status_code == 403  # nobody's notebook of hers
    assert api(f"/notebook/api/{shown['entry']}/remove", person="ben", method="POST").json() == {
        "removed": shown["entry"]}  # Ben, its deputy
    assert entries(stack) == []
    [removed] = [e for e in stack.ledger() if e["kind"] == "notebook"]
    assert (removed["action"], removed["args"]["by"]) == ("remove", "ben")
    assert httpx.get(f"{approving}/notebook/", timeout=30).status_code == 200


@pytest.mark.live
def test_a_real_model_notes_what_records_show_on_its_schedule(database, tmp_path):
    release = definitions.load(ROOT / "agents" / "assistant")
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel(), worker_image=live_image()) as stack:
        with_notebook(stack)
        stack.at("2026-10-29T09:00:30+00:00")
        assert stack.scheduler().work_due() == 1
        noted = [e for e in stack.ledger() if e["action"] == "note_learned"
                 and e["decision"] == "record"]
        print(f"--> {[n['outcome'] for n in noted]}")
        print(f"--> {[(e['text'], e['sources']) for e in entries(stack)]}")
        assert entries(stack), "it noted nothing that its records hold"
        assert stack.verify().ok
