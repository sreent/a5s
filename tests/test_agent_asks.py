"""Asking for an agent (core/asks.py, docs/studio.md#people-roles-and-spaces): someone who knows
of an agent, from the catalogue, asks to be served by it. The ask waits on the agent's owners
and its instances' approvers, who answer it with a version of the settings that serves the
asker, which goes to its approvers as any version does, or decline it. It ends once a version in
force serves them, or they withdraw it, or it's declined, or nobody answers it in a month."""

import httpx

from a5s import db
from a5s.core import asks, export
from test_group_roles import approve, in_force


def send(url: str, provider, person: str, method: str, path: str,
         body: dict | None = None) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.request(method, f"{url}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})


def listed(stack, monkeypatch, agent: str = "assistant") -> None:
    found = stack.gateway.definitions[agent]
    monkeypatch.setitem(stack.gateway.definitions, agent, found.model_copy(update={"listed": True}))


def waiting(url: str, provider, person: str) -> list[dict]:
    home = send(url, provider, person, "GET", "/studio/api/home").json()
    return [w for w in home["waiting"] if w["kind"] == "ask"]


def ended(stack, ask: str) -> str | None:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select outcome from agent_asks where id = %s::uuid",
                            (ask,)).fetchone()["outcome"]


def test_someone_asks_for_an_agent_and_an_approver_serves_them(stack, approving, provider,
                                                               monkeypatch):
    listed(stack, monkeypatch)
    asked = send(approving, provider, "lena", "POST", "/studio/api/agents/assistant/ask")
    assert asked.status_code == 200, asked.text
    ask = asked.json()["id"]
    again = send(approving, provider, "lena", "POST", "/studio/api/agents/assistant/ask")
    assert again.json()["id"] == ask  # one open ask for each agent
    page = send(approving, provider, "lena", "GET", "/studio/api/agents/assistant").json()
    assert page["ask"]["id"] == ask and "asks" not in page
    [theirs] = waiting(approving, provider, "ana")  # who owns billing, where it works
    assert theirs["what"] == "Lena Fischer asks for the assistant"
    assert theirs["why"] == ["you own billing, where assistant-finance works"]
    assert waiting(approving, provider, "priya")  # who owns the assistant
    assert waiting(approving, provider, "omar") == []  # it works in no part of his
    shown = send(approving, provider, "ana", "GET", "/studio/api/agents/assistant").json()
    assert [a["person"] for a in shown["asks"]] == ["Lena Fischer"]
    served = send(approving, provider, "ana", "POST", f"/studio/api/asks/{ask}/serve",
                  {"instance": "assistant-finance"})
    assert served.status_code == 202, served.text  # a request, as the settings app makes
    stack.scheduler().apply_approved()  # the core proposes it to everyone it needs
    with db.transaction(stack.admin) as conn:
        proposed = conn.execute("select digest, serial from settings_proposals where outcome is "
                                "null order by serial desc limit 1").fetchone()
    assert proposed["serial"] == served.json()["serial"]
    assert ended(stack, ask) is None  # it waits for its approvers
    approve(stack, approving, provider, proposed["digest"], "ana")  # who owns billing
    assert in_force(stack) == (proposed["serial"], None)
    send(approving, provider, "lena", "GET", "/studio/api/home")  # which settles what's served
    assert ended(stack, ask) == "served"
    lena = send(approving, provider, "lena", "GET", "/studio/api/agents/assistant").json()
    assert "uses" in lena["layers"] and "ask" not in lena  # it serves her: nothing to ask
    actions = [e["action"] for e in stack.ledger() if e["kind"] == "admin"]
    assert "ask for agent" in actions and "ask for agent served" in actions


def test_an_ask_ends_when_withdrawn_declined_or_unanswered(stack, approving, provider,
                                                          monkeypatch):
    listed(stack, monkeypatch)
    path = "/studio/api/agents/assistant/ask"
    first = send(approving, provider, "lena", "POST", path).json()["id"]
    assert send(approving, provider, "lena", "DELETE", path).json()["outcome"] == "withdrawn"
    assert send(approving, provider, "lena", "DELETE", path).status_code == 404
    second = send(approving, provider, "lena", "POST", path).json()["id"]
    assert second != first
    assert send(approving, provider, "omar", "POST",  # it doesn't wait on him
                f"/studio/api/asks/{second}/decline").status_code == 404
    declined = send(approving, provider, "ana", "POST", f"/studio/api/asks/{second}/decline")
    assert declined.json()["outcome"] == "declined" and "ended_by" not in declined.json()
    third = send(approving, provider, "lena", "POST", path).json()["id"]
    with db.transaction(stack.admin) as conn:  # nobody answered it for a month and a day
        conn.execute("update agent_asks set asked_at = now() - interval '31 days' where id = "
                     "%s::uuid", (third,))
        asks.settle(conn, stack.gateway.scenario, [])
    assert ended(stack, third) == "lapsed"


def test_nobody_asks_for_an_agent_they_may_not_know_of_or_have(stack, approving, provider):
    assert send(approving, provider, "lena", "POST",  # unlisted, and nothing of hers
                "/studio/api/agents/assistant/ask").status_code == 404
    have = send(approving, provider, "ben", "POST", "/studio/api/agents/assistant/ask")
    assert have.status_code == 409 and "serves you already" in have.text


def test_an_ask_is_the_askers_to_see_and_goes_with_them(stack, approving, provider, monkeypatch):
    listed(stack, monkeypatch)
    send(approving, provider, "lena", "POST", "/studio/api/agents/assistant/ask")
    with db.transaction(stack.admin) as conn:
        found = export.gather(conn, "lena")
    assert [(a["agent"], a["outcome"]) for a in found["asks"]] == [("assistant", None)]


def test_an_ended_ask_goes_once_the_officers_time_for_it_is_past(stack, approving, provider,
                                                                 monkeypatch):
    listed(stack, monkeypatch)
    path = "/studio/api/agents/assistant/ask"
    send(approving, provider, "lena", "POST", path)
    send(approving, provider, "lena", "DELETE", path)
    with stack.client() as c:
        assert "asks" not in c.post("/retention/sweep").json()["deleted"]  # ended just now
    with db.transaction(stack.admin) as conn:  # a year and a month ago
        conn.execute("update agent_asks set ended_at = now() - interval '13 months'")
    with stack.client() as c:
        assert c.post("/retention/sweep").json()["deleted"]["asks"] == 1
