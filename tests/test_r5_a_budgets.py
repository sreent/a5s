"""Round 5, reviewer a: the core checks a run's budget before each model call and counts the
call's tokens after it, with nothing reserved in between. Calls a run makes at once all pass
the check, so a run goes past its budget by as many calls as it makes at once. Deep Agents
makes calls at once whenever a model asks for several subagents together; a worker that's
been taken over makes as many as it likes. The same holds for each person's day.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from a5s import db
from test_budgets import budget


def test_calls_made_at_once_dont_take_a_run_far_past_its_budget(stack):
    budget(stack, per_run=1000)
    stack.model.tokens = 900  # each call: one is within the budget, two are past it
    stack.model.on_request = lambda _n: time.sleep(0.5)  # a model takes a while to answer
    run, token = stack.open_run(sender="ana")
    body = {"model": "fake", "messages": [{"role": "user", "content": "Hello"}]}

    def call(_: int) -> int:
        return httpx.post(f"{stack.url}/v1/chat/completions", json=body, timeout=60,
                          headers={"Authorization": f"Bearer {token}"}).status_code

    with ThreadPoolExecutor(8) as pool:
        answered = list(pool.map(call, range(8)))
    with db.transaction(stack.admin) as conn:
        used = conn.execute("select tokens from runs where id = %s", (run,)).fetchone()["tokens"]
    assert used <= 1000 + 900, f"{answered.count(200)} calls answered, {used} tokens for a budget of 1000"
