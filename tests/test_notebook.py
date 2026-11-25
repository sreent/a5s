"""The notebook (critique C1). An agent notes what it learns from records, only in a run that
acts for nobody, on its schedule, which hears nobody's words, and never once it has read content
from outside. Code keeps a note only if every record it names was read with a tool and holds
every key, amount and date in it. Runs are given the notes whose every record their people may
see; a note lapses once its records change, as code reads them again each day; the agent's owner,
or whoever runs its instance, reads and removes notes on the core's page."""

import os
from datetime import timedelta

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.config import load_models
from a5s.core import notebook, parts, provenance
from conftest import ROOT, FakeModel, build_root, live_image, running

LEARN = {"name": "learn", "at": "09:00", "days": "weekdays",
         "task": "Look through the questions in your parts with search_records and get_record, "
                 "and note one thing you learn from them with note_learned, naming them. Don't "
                 "read customers' messages: a run that has read them notes nothing."}
NOTED = "Q-1001 is Northwind's question about an invoice."


def with_notebook(stack) -> None:
    """A new release of the assistant, with a schedule and a notebook, applied."""
    spec = stack.cfg.agents_dir / "assistant" / "agent.yaml"
    data = yaml.safe_load(spec.read_text(encoding="utf-8"))
    data["schedules"] = [LEARN]
    data["context"]["notebook"] = True
    spec.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
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
    assert seen["names"][shown["instance"]] == "the assistant in billing"  # as people say it
    assert api("/notebook/api", person="chen").status_code == 403  # nobody's notebook of hers
    assert api(f"/notebook/api/{shown['entry']}/remove", person="ben", method="POST").json() == {
        "removed": shown["entry"]}  # Ben, its deputy
    assert entries(stack) == []
    [removed] = [e for e in stack.ledger() if e["kind"] == "notebook"]
    assert (removed["action"], removed["args"]["by"]) == ("remove", "ben")
    went = httpx.get(f"{approving}/notebook/", timeout=30)  # in the studio, now
    assert (went.status_code, went.headers["location"]) == (303, "/studio/notebook")


def test_its_keeper_reads_and_removes_notes_in_the_studio(stack, approving, provider, browser):
    """Ana runs the assistant in billing: she finds its note on her instance's page, opens the
    notebook in the studio, and removes it, asked first, since it can't be undone."""
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    from conftest import accessible

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/instances/assistant-finance")
    page.click("#instance-waiting a:has-text('note it keeps')")  # within the studio
    page.wait_for_selector("#entries li", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/notebook"
    assert page.inner_text("#entries h2") == "Kept by the assistant in billing"
    note = page.locator("#entries li").first
    assert NOTED in note.inner_text() and note.locator("a:has-text('Q-1001')").count() == 1
    assert page.locator("#pages a[aria-current=page]").get_attribute("href") == "/studio/notebook"
    accessible(page)
    note.locator("button:text-is('Remove')").click()
    page.locator("dialog[open] button:has-text('Remove it')").click()
    page.wait_for_selector("#status >> text=Removed N-", timeout=30000)
    assert entries(stack) == [] and page.locator("#entries li").count() == 0


@pytest.mark.live
def test_a_real_model_notes_what_records_show_on_its_schedule(database, tmp_path):
    release = definitions.load(ROOT / "agents" / "assistant")
    model = load_models(ROOT / "config" / "models.yaml")[release.model]
    if model.key_env and not os.environ.get(model.key_env):
        if os.environ.get("A5S_REGRESSION") == "required":
            pytest.fail(f"{model.key_env} isn't set, and a release needs its agents' suites")
        pytest.skip(f"{model.key_env} isn't set")
    root = build_root(tmp_path, release.model, (ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
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


def test_a_note_on_another_parts_record_is_refused_as_one_on_a_record_there_isnt(stack):
    """A record the run read may name others, one in a part the agent doesn't work in or one
    there isn't: a note on either is refused in the same words, and the ledger keeps which
    (round 15, A14)."""
    with_notebook(stack)

    def named(n: int) -> None:  # as if a record it read named both
        if n == 1:
            with db.transaction(stack.admin) as conn:
                [run] = conn.execute("select id::text from runs where closed_at is null")
                provenance.read_records(conn, run["id"], "get_record", "key",
                                        [{"key": "Q-1003"}, {"key": "Q-9999"}],
                                        stack.gateway.scenario.record_pattern)

    stack.model.on_request = named
    learn(stack, ("note_learned", {"note": "Q-1003 is late.", "sources": ["Q-1003"]}),
          ("note_learned", {"note": "Q-9999 is late.", "sources": ["Q-9999"]}))
    elsewhere, none = [e["outcome"] for e in stack.ledger()
                       if e["action"] == "note_learned" and e["decision"] == "record"]
    assert elsewhere["reason"] == f"Q-1003: {parts.NOWHERE}"
    assert none["reason"] == f"Q-9999: {parts.NOWHERE}"
    assert (elsewhere["why"], none["why"]) == ("Q-1003 isn't in a part this agent works in",
                                               "the records have no Q-9999")
    assert entries(stack) == []
