"""Round 9, reviewer A: the studio's need-to-know for runs (core/studio.py).

The studio shows a viewer an instance's runs "whose every record they may see". It learns which
records a run read from `run_reads`, which retention deletes an hour after the run closes, and
it counts only what tools returned ("<tool> about <key>"), never what a5s's brief told the run.
"""

import hashlib
from datetime import date, timedelta

import httpx
import yaml

from a5s import db
from conftest import SERVICE_TOKEN

OPS = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
       "owner": "omar"}


def with_ops(stack) -> None:
    """A second assistant, in orders, which Omar owns and runs, serving Chen (as in
    tests/test_studio_pages.py)."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    assert not stack.settle(instances={**settings["instances"], "assistant-ops": OPS},
                            signers=("ana", "omar")).refused


def signed_in(url: str, provider):
    def api(path: str, person: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        return httpx.get(f"{url}{path}", headers=headers, timeout=30)
    return api


def an_hour_on(stack) -> None:
    """Every run closed over an hour ago, and the core's hourly retention sweep."""
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set closed_at = now() - interval '2 hours' "
                     "where closed_at is not null")
    with httpx.Client(base_url=stack.url, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
                      timeout=60) as core:
        assert core.post("/retention/sweep").json()["deleted"].get("reads")


def chen_searches(stack) -> None:
    """Chen asks about deliveries without naming a record; the assistant searches, and finds
    Q-1003, in orders, which Ana (finance) may not see."""
    stack.model.reply(None, ("search_records", {"query": "delivery"}))
    stack.model.reply("Q-1003 is waiting on the warehouse.")
    stack.say("Is anything waiting on the warehouse?", person="chen")
    scenario = stack.gateway.scenario
    assert scenario.sees("chen", "Q-1003") and not scenario.sees("ana", "Q-1003")


def test_a_run_that_read_a_record_shows_to_someone_who_may_not_see_it_an_hour_later(
        stack, approving, provider):
    with_ops(stack)
    chen_searches(stack)
    api = signed_in(approving, provider)
    ana = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert (ana["runs"], ana["hidden"]) == ([], 1)  # at first, hidden: she may not see Q-1003

    an_hour_on(stack)  # retention lets go of what the run read, as it does every hour
    ana = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    # FAILS NOW: the run that read Q-1003 is listed for Ana, by whom it acted for
    assert ana["hidden"] == 1 and ana["runs"] == [], ana
    [ran] = api("/studio/api/instances/assistant-ops/runs", "omar").json()["runs"]
    assert api(f"/studio/api/runs/{ran['run']}", "ana").status_code == 404


def test_a_report_about_a_record_shows_at_once_to_someone_who_may_not_see_it(
        stack, approving, provider):
    """The watcher's report run learns its records from a5s's brief, not a tool, so the studio
    never counts them: Ana sees Chen's report about Q-1003 at once."""
    stack.with_watcher(serves=("chen",), parts=["orders"], signers=("ana", "omar"),
                       owner="omar", deputy="chen")
    stack.at("2026-10-29T01:30:00+00:00")  # 09:30 in Singapore
    stack.model.reply("Chen, you have Q-1003 open, due on Monday.")
    assert stack.scheduler().work_due() == 1
    api = signed_in(approving, provider)
    [told] = api("/studio/api/instances/watcher-finance/runs", "omar").json()["runs"]
    assert told["trigger"] == "report" and told["acts_for"][0]["name"] == "Chen Wei"
    ana = api("/studio/api/instances/watcher-finance/runs", "ana").json()
    # FAILS NOW: the report that told Chen of Q-1003 is listed for Ana, and its page opens
    assert (ana["runs"], ana["hidden"]) == ([], 1), ana
    assert api(f"/studio/api/runs/{told['run']}", "ana").status_code == 404


def test_the_runs_list_ignores_the_records_its_ledger_entries_name(stack, approving, provider):
    """The page hides a run whose ledger entries name a record the viewer may not see; the list
    still shows it, with whom it acted for."""
    stack.model.reply(None, ("get_record", {"key": "Q-1003"}))  # Ana's run asks for an orders
    stack.model.reply("I can't see that one.")  # record, which policy keeps from her
    stack.say("Where's the Fabrikam delivery?", person="ana")
    api = signed_in(approving, provider)
    [ran] = api("/studio/api/instances/assistant-finance/runs", "ana").json()["runs"] or [None]
    assert ran is None or api(f"/studio/api/runs/{ran['run']}", "ben").status_code == 404
    page = api("/studio/api/instances/assistant-finance/runs", "ben").json()
    # FAILS NOW: listed for Ben, with whom it acted for, though its page names Q-1003, which
    # he may not see, and is refused him
    assert (page["runs"], page["hidden"]) == ([], 1), page


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_what_was_said_by_hash_alone_is_read_back_by_guessing(stack, approving, provider):
    """The run's page shows the ledger's unsalted SHA-256 of each argument with its length: a
    watcher recovers short ones, such as what was searched for and the date asked for."""
    stack.model.reply(None, ("search_records", {"query": "refund"}),
                      ("change_due_date", {"key": "Q-1002", "due": "2026-12-18"}))
    stack.model.reply("I've asked for Q-1002's due date to move.")
    stack.say("Can you push back the date on the duplicate payment one?", person="ben")
    api = signed_in(approving, provider)
    [ran] = api("/studio/api/instances/assistant-finance/runs", "ana").json()["runs"]
    entries = api(f"/studio/api/runs/{ran['run']}", "ana").json()["entries"]
    hashed = {(e["action"], k): v for e in entries if e.get("kind") == "tool" and "args" in e
              for k, v in e["args"].items() if isinstance(v, dict) and "sha256" in v}
    words = {w.strip(".,").lower() for r in yaml.safe_load(
        (stack.cfg.scenario_dir / "data.yaml").read_text())["records"]
        for w in f"{r['title']} {r['status']}".split()} | {"refund", "invoice", "delivery"}
    query = hashed[("search_records", "query")]
    found = [w for w in words if len(w) == query["chars"] and sha(w) == query["sha256"]]
    assert found == ["refund"]  # what Ben's question was about, from its hash
    due = hashed[("change_due_date", "due")]
    days = (str(date(2026, 1, 1) + timedelta(days=n)) for n in range(731))
    assert next(d for d in days if sha(d) == due["sha256"]) == "2026-12-18"
    # FAILS NOW: the studio promises what was said appears only by its hash
    assert not found, "a watcher read back what was searched for and asked, from the hashes"


def test_once_someone_is_erased_every_watcher_still_reads_their_runs_by_name(
        stack, approving, provider):
    """R9 accepted that runs kept as evidence name whom they acted for, for whoever reads them:
    the team and the officer. The studio now shows them to every watcher, by name, with what
    was searched for still recoverable from its hash."""
    from a5s.core import erasure
    stack.model.reply(None, ("search_records", {"query": "refund"}))
    stack.model.reply("Q-1002 is waiting on finance.")
    stack.say("Where's my refund?", person="ben")
    with db.transaction(stack.admin) as conn:  # the officer erases Ben, at his request
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone.get("turns")
    api = signed_in(approving, provider)
    runs = api("/studio/api/instances/assistant-finance/runs", "ana").json()["runs"]
    shown = api(f"/studio/api/runs/{runs[0]['run']}", "ana").json()
    query = next(e["args"]["query"] for e in shown["entries"] if e.get("action") == "search_records"
                 and "args" in e)
    # FAILS NOW: Ana, a watcher, sees Ben's erased conversation's run by his name, and what
    # he asked about from its hash
    assert shown["acts_for"][0]["name"] != "Ben Okafor" and query["sha256"] != sha("refund"), (
        shown["acts_for"], query)


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
