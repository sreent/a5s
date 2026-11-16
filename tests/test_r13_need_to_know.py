"""Round 13, reviewer B: need-to-know in what the studio shows, once its plain pages were in it.

B1: the administrators' page kept every act whose entry named no agent, and those on an instance
name none: so anyone with a role, Omar among them, read the grades, the settings applied and the
suspensions of instances of agents he may not know of. An act on an instance is now an act of its
agent's, and what it did is shown only to those who may watch the instance.
B2: an instance page's ask to suspend or resume it read as "asked as the data protection
officer": it has its own words, and every administrative act the ledger records has words.
B3: the catalogue named the instances each instance may ask, which no page reads.
B4: the home offered a new agent to an agent's authors, who may not start one.
B5: where an instance's runs stay hidden, its page gave to the second when a change held for
someone else's decision began to wait: what waits on others gives no time.
B6: finding anything read the pages people may use once, not each time it opened."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import yaml

from a5s import db
from a5s.core import audit
from conftest import ROOT, WATCHER
from test_group_roles import approve, in_force, version
from test_proposals import asked, held, sweep
from test_samples import grade, release
from test_studio_home import api
from test_studio_suspension import act

SRC = ROOT / "src" / "a5s"


def a_sample(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
            "part, action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
            "gen_random_uuid(), 'assistant-finance', %s, 'assistant', 'billing', "
            "'change-due-date', 'a change', '{}', '{ben}', now()) returning id",
            (release(stack),)).fetchone()["id"]


def get(url, provider, person, path, *groups):
    token = provider.id_token(person=person, groups=list(groups))
    return httpx.get(f"{url}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30)


def test_the_admin_page_names_no_act_on_an_instance_of_an_agent_its_reader_may_not_know_of(
        stack, approving, provider):
    stack.with_watcher()  # Ana runs it, Ben is its deputy
    graded = grade(approving, provider, a_sample(stack), "critical")
    assert graded.status_code == 200, graded.text
    asked_to = act(approving, provider, "suspend", "ben", instance="watcher-finance")
    assert asked_to.status_code == 200, asked_to.text
    sweep(stack)
    assert api(approving, provider, "omar", "agents/assistant").status_code == 404
    latest = get(approving, provider, "omar", "/admin/api").json()["latest"]  # Omar owns orders
    assert not [a for a in latest if a["instance"] in ("assistant-finance", "watcher-finance")], latest
    anas = get(approving, provider, "ana", "/admin/api").json()["latest"]  # who watches both
    [graded_act] = [a for a in anas if a["action"] == "grade"]
    assert graded_act["about"]["grade"] == "critical"
    asks = [a for a in anas if a["action"] == "ask-status"]
    assert asks and asks[0]["what"] == "asked to suspend or resume an instance"


def test_every_administrative_act_has_words_of_its_own():
    recorded = set(re.findall(r'"kind": "admin", "action": "([a-z-]+)"',
                              "".join(p.read_text() for p in SRC.rglob("*.py"))))
    assert recorded <= set(audit.ADMIN), recorded - set(audit.ADMIN)
    assert len(set(audit.ADMIN.values())) == len(audit.ADMIN)


def test_the_catalogue_names_no_instance_another_may_ask(stack, approving, provider):
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    ops = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
           "owner": "omar", "deputy": "chen", "asks": ["watcher-finance"]}
    applied = stack.settle(instances={**settings["instances"], "watcher-finance": WATCHER,
                                      "assistant-ops": ops}, signers=("ana", "omar"))
    assert not applied.refused, applied.refused
    catalogue = get(approving, provider, "chen", "/studio/api").json()
    [inst] = [i for a in catalogue["agents"] for i in a["instances"] if i["id"] == "assistant-ops"]
    assert "asks" not in inst and "watcher-finance" not in str(catalogue)


def test_an_author_isnt_offered_a_new_agent_they_may_not_start(stack, approving, provider):
    asked_for = version(stack, {"assistant-authors": ["agent-author:assistant"]})
    approve(stack, approving, provider, asked_for["digest"], "ana")
    approve(stack, approving, provider, asked_for["digest"], "priya")
    assert in_force(stack) == (asked_for["serial"], None)
    home = get(approving, provider, "chen", "/studio/api/home", "assistant-authors").json()
    catalogue = get(approving, provider, "chen", "/studio/api", "assistant-authors").json()
    assert home["authoring"] is False and catalogue["authoring"]["new"] is False
    assert get(approving, provider, "priya", "/studio/api/home").json()["authoring"] is True


def test_what_waits_on_someone_else_gives_no_time(stack, approving, provider):
    asked(stack)  # held for Ana
    held(stack)
    runs = api(approving, provider, "priya", "instances/assistant-finance/runs").json()
    assert runs["runs"] == [] and runs["fewer"] == 5  # its runs stay hidden from Priya
    standing = api(approving, provider, "priya", "instances/assistant-finance/standing").json()
    [theirs] = [w for w in standing["waiting"] if w["kind"] == "held"]
    assert theirs.get("since") is None


def test_finding_anything_reads_the_pages_afresh_each_time_it_opens():
    script = (ROOT / "studio" / "src" / "Find.tsx").read_text()
    assert "shellOf(true)" in script and "shellOf()" not in script
    assert "afresh" in Path(ROOT / "studio" / "src" / "Sidebar.tsx").read_text()
