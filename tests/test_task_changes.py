"""A change a task's later slice asks for again is the same change (core/counts.py): a slice
that stopped part way, after asking for a change, leaves the next to ask for it again, and a5s
neither holds it twice nor makes it twice, and gives a system the same key for it each time."""

from a5s import db
from a5s.core import counts
from test_proposals import MOVE, held
from test_task_runs import a_task, tasks_of


def test_a_change_a_later_slice_asks_for_again_is_held_once(stack, approving):
    a_task(stack, owner="ben")  # Ben's task asks for a change to Q-1002, which Ana decides
    for _ in range(2):  # one slice asks, and the next asks again, as after a stop part way
        stack.model.reply(None, MOVE, ("finish_task", {"status": "waiting"}))
        stack.model.reply("Asked for it.")
        stack.scheduler().work_due()
    assert len(held(stack)) == 1 and tasks_of(stack)[0]["attempts"] == 2
    assert "Asked for already" in str(stack.model.requests[-1]["body"]["messages"])


def test_a_change_made_in_one_slice_is_made_already_for_the_next(stack):
    task = a_task(stack)
    trigger = {"kind": "task", "task": str(task["id"])}
    with stack.client() as c:  # two slices of the task, one after the other
        first = c.post("/runs", json={"instance": "assistant-finance", "trigger": trigger})
        c.post(f"/runs/{first.json()['run']}/close", json={"outcome": "done"}).raise_for_status()
        second = c.post("/runs", json={"instance": "assistant-finance", "trigger": trigger})
    first, second = first.json()["run"], second.json()["run"]
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into action_counts (run_id, instance_id, action, change, acts_for, "
                     "at, over, records, state) values (%s, 'assistant-finance', "
                     "'change-due-date', 'moved', '{ana}', now(), false, 1, 'made')", (first,))
        again = counts.before(conn, {"run": second, "trigger": trigger}, "change-due-date",
                              "moved")
        apart = counts.before(conn, {"run": second, "trigger": {"kind": "message"}},
                              "change-due-date", "moved")
    assert again["state"] == "made" and apart is None  # only its task's runs count
    keyed = [counts.key(counts.work({"run": r, "trigger": trigger}), "moved")
             for r in (first, second)]
    assert keyed[0] == keyed[1]  # one key for the task, whichever slice asks
    assert counts.key(counts.work({"run": first, "trigger": {}}), "moved") != counts.key(
        counts.work({"run": second, "trigger": {}}), "moved")  # a run of its own: its own
