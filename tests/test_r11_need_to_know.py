"""Round 11, reviewer D: need-to-know in the lists around the layers of what someone may know
of an agent (core/studio.py). The chat named every agent to anyone, without sign-in, and a
message to an agent that didn't serve its sender named the owners of the parts it works in."""

import httpx
import yaml

from a5s import db
from a5s.services.scheduler import NO_SUCH
from test_webchat import channels


def test_the_chats_config_names_no_agent(stack):  # D-1
    with channels(stack) as url:
        config = httpx.get(f"{url}/chat/config").json()
        assert "agents" not in config
        mine = httpx.get(f"{url}/channels/local/agents", params={"person": "ana"}).json()
        theirs = httpx.get(f"{url}/channels/local/agents", params={"person": "chen"}).json()
    assert mine == {"agents": ["assistant"]}  # the one that serves her
    assert theirs == {"agents": []}  # Chen: none serves him


def test_an_agent_its_sender_may_not_know_of_is_answered_as_one_there_isnt(stack):  # D-1
    unlisted = stack.say("hi", person="chen", agent="watcher")  # none of his, and unlisted
    made_up = stack.say("hi", person="chen", agent="made-up")
    assert unlisted == NO_SUCH.format(agent="watcher") and made_up == NO_SUCH.format(agent="made-up")
    assert "Ana" not in unlisted + made_up and not stack.model.requests


def test_someone_who_may_know_of_an_agent_is_told_to_ask_for_it_naming_nobody(stack):  # D-1
    said = stack.say("hi", person="priya")  # she owns the assistant, which doesn't serve her
    assert said == "There's no assistant for you yet. Ask for it on its page in the studio."
    assert "Ana" not in said and "billing" not in said


def test_the_admin_page_shows_only_the_agents_its_viewer_may_know_of(  # D-2, B-4
        stack, approving, provider, monkeypatch):
    from test_agent_asks import listed, send
    listed(stack, monkeypatch)  # the assistant, for Lena to ask for
    asked = send(approving, provider, "lena", "POST", "/studio/api/agents/assistant/ask")
    assert asked.status_code == 200, asked.text
    started = send(approving, provider, "priya", "POST", "/studio/api/drafts",
                   {"name": "redundancy-planning", "template": "assistant"})
    assert started.status_code == 200, started.text  # a new agent's draft: Priya's alone
    found = send(approving, provider, "omar", "GET", "/admin/api").json()  # he owns orders
    roles = [r["role"] for r in found["roles"]]
    assert "agent-owner:watcher" not in roles  # an unlisted agent he may not know of
    acts = [(a["action"], a["by"], a["about"]) for a in found["latest"]]
    assert not any(about.get("agent") == "redundancy-planning" for _, _, about in acts)
    [ask] = [(by, about) for action, by, about in acts if action == "ask for agent"]
    assert ask[0] is None and ask[1]["asker"].startswith("person-")  # a stand-in, not Lena
    mine = send(approving, provider, "priya", "GET", "/admin/api").json()
    assert "agent-owner:watcher" in [r["role"] for r in mine["roles"]]  # hers to know


def test_each_administrative_act_is_said_as_what_it_was():  # B-6
    from a5s.core import audit
    assert audit.ADMIN["request"] == "asked for a version of the settings"
    assert audit.ADMIN["ask"] == "asked as the data protection officer"


def test_an_instance_serving_fewer_than_the_officer_chose_shows_no_run_alone(  # D-3
        stack, approving, provider):
    from conftest import listed_runs
    from test_studio_pages import signed_in
    ops = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
           "owner": "omar"}  # Chen's own assistant, which Omar runs
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    assert not stack.settle(instances={**settings["instances"], "assistant-ops": ops},
                            signers=("ana", "omar")).refused
    stack.model.reply("Q-1003 is due on Monday.")
    stack.say("When is Q-1003 due?", person="chen")
    api = signed_in(approving, provider)
    catalogue = api("/studio/api", "omar").json()
    [shown] = [i for a in catalogue["agents"] for i in a["instances"] if i["id"] == "assistant-ops"]
    assert "serves" not in shown and shown["people"] == 1  # how many, never whom
    page = api("/studio/api/instances/assistant-ops/runs", "omar").json()
    assert (page["runs"], page["fewer"]) == ([], 5)  # its daily figures say what it did
    with db.transaction(stack.admin) as conn:
        run = conn.execute("select id::text as id from runs where instance_id = 'assistant-ops'"
                           ).fetchone()["id"]
    assert api(f"/studio/api/runs/{run}", "omar").status_code == 404
    listed_runs(stack)  # and finance's assistant, serving three, lists its runs, unnamed
    stack.model.reply("Hello, Dana.")
    stack.say("Hello", person="dana")
    page = api("/studio/api/instances/assistant-finance/runs", "ana").json()
    assert page["fewer"] is None and [r["acts_for"] for r in page["runs"]] == [[]]


def test_where_the_next_page_of_runs_starts_says_nothing_of_the_run(stack, approving, provider):  # D-5
    from conftest import listed_runs
    from test_studio_pages import signed_in
    listed_runs(stack)
    for _ in range(2):
        stack.model.reply("Noted.")
        stack.say("Note this", person="ana")
    api = signed_in(approving, provider)
    page = api("/studio/api/instances/assistant-finance/runs?limit=1", "ben").json()
    assert page["before"] and "|" not in page["before"]  # sealed: no moment, no id
    older = api("/studio/api/instances/assistant-finance/runs?limit=1&before="
                + page["before"], "ben").json()
    assert older["runs"] and older["runs"][0]["run"] != page["runs"][0]["run"]
    forged = api("/studio/api/instances/assistant-finance/runs?before=2026-01-01T00:00:00%2B00:00|"
                 "00000000-0000-0000-0000-000000000000", "ben")
    assert forged.status_code == 400


def test_figures_are_asked_for_over_a_year_at_most(stack, approving, provider):  # D-6
    from test_studio_pages import signed_in
    api = signed_in(approving, provider)
    assert api("/studio/api/instances/assistant-finance?days=200000", "ben").status_code == 422
    assert api("/studio/api/agents/assistant/measures?days=0", "priya").status_code == 422
    assert api("/studio/api/instances/assistant-finance?days=366", "ben").status_code == 200
    with stack.client() as c:
        assert c.get("/studio/instances/assistant-finance/measures?days=200000").status_code == 422
        assert c.get("/studio/agents/assistant/measures?days=367").status_code == 422


def test_what_waits_for_a_decision_is_counted_by_who_may_decide_it_now(  # D-7
        stack, approving, provider, monkeypatch):
    from dataclasses import replace

    from test_admin_page import admin
    from test_proposals import asked, held
    from test_studio_home import api
    asked(stack)
    [p] = held(stack)
    assert p["deciders"] == ["ana"]
    people = stack.gateway.scenario._people  # Ana hands billing to Dana
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=("instance-approver",)))
    monkeypatch.setitem(people, "dana", replace(people["dana"],
                                                roles=("grader", "part-owner:billing")))
    homes = {who: [w["what"] for w in api(approving, provider, who, "home").json()["waiting"]
                   if w["kind"] == "decide"] for who in ("ana", "dana")}
    assert homes == {"ana": [], "dana": ["1 change an agent asked for waits for your decision"]}
    [changes] = admin(approving, provider, "kofi").json()["waiting"]["held_changes"]
    assert (changes["part"], changes["deciders"]) == ("billing", ["dana"])


def test_an_agents_figures_on_peoples_pages_keep_its_retired_instances_runs(  # D-8
        stack, approving, provider):
    from test_studio_pages import OPS, signed_in
    stack.model.reply("Nothing's open for you.")
    stack.say("What's open?", person="ana")  # a run of assistant-finance
    assert not stack.settle(instances={"assistant-ops": OPS}, signers=("ana", "omar")).refused
    api = signed_in(approving, provider)  # assistant-finance has retired
    people = api("/studio/api/agents/assistant/measures", "priya").json()  # its owner's
    with stack.client() as c:
        core = c.get("/studio/agents/assistant/measures").json()
    assert "assistant-finance" in people["instances"] and people["instances"] == core["instances"]
    assert sum(r["runs"] for r in people["runs"]) == sum(r["runs"] for r in core["runs"]) >= 1


def test_an_ask_for_an_agent_with_no_instance_waits_on_its_owners_alone(  # D-4
        stack, approving, provider):
    from test_agent_asks import send, waiting
    from test_studio_pages import signed_in
    api = signed_in(approving, provider)
    assert api("/studio/api/agents/watcher", "ana").status_code == 404  # unlisted, no instance
    asked = send(approving, provider, "rosa", "POST", "/studio/api/agents/watcher/ask")
    assert asked.status_code == 200, asked.text  # a release approver sees how it's built
    assert waiting(approving, provider, "ana") == []  # who approves instances, and may not know it
    [theirs] = waiting(approving, provider, "priya")  # its owner
    assert theirs["what"] == "Rosa Mendes asks for the watcher"
    assert api(theirs["go"].replace("/studio/", "/studio/api/"), "priya").status_code == 200
