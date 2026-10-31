"""Held proposals and signed decisions. Below level 2, a change an agent asks for waits for
the owner of the part its record is in, who decides it on the core's page, signed in afresh
for that decision. The gateway makes it once approved, if the records haven't changed, and
tells whoever it was for."""

import base64
import hashlib
import json
import secrets
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from a5s import db
from a5s.contract import record_of
from a5s.core import proposals
from conftest import CLIENT

MOVE = ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"})


def asked(stack, call=MOVE, person: str = "ben", said: str = "Please move Q-1002 to 2026-11-13.") -> dict:
    """Ben asks the assistant for a change, and it calls the tool: what the tool answered."""
    stack.model.reply(None, call)
    stack.model.reply("It waits for Ana Ortiz to decide.")
    stack.say(said, person=person)
    answer = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    return json.loads(answer) if answer.startswith("{") else answer


def held(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from proposals order by id").fetchall()


def due_of(stack, key: str = "Q-1002") -> str:
    return record_of(stack.gateway.scenario, key).fields["due date"]


def signed(url: str, provider, digests: list[str], decision: str, person: str = "ana",
           fresh: bool = True) -> tuple[str, str]:
    """A sign-in to decide, made as the page makes one: the token, and its salt."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    query = {"client_id": CLIENT, "redirect_uri": f"{url}/decide/", "state": "s",
             "nonce": proposals.nonce(digests, decision, salt), "code_challenge": challenge.decode(),
             "code_challenge_method": "S256"}
    went = httpx.get(f"{provider.url}/auth", params={**query, **({"max_age": "0"} if fresh else {})})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    tokens = httpx.post(f"{url}/decide/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/decide/"}).json()
    return tokens["id_token"], salt


def decide(url: str, provider, digests: list[str], decision: str = "approve", person: str = "ana",
           **kwargs) -> httpx.Response:
    token, salt = signed(url, provider, digests, decision, person, **kwargs)
    return httpx.post(f"{url}/decide/proposals", json={
        "proposals": digests, "decision": decision, "salt": salt},
        headers={"Authorization": f"Bearer {token}"})


def sweep(stack) -> dict:
    with stack.client() as c:
        r = c.post("/proposals/sweep")
    r.raise_for_status()
    return r.json()


def test_a_change_below_level_2_waits_for_the_owner_of_its_part(stack, approving):
    answer = asked(stack)
    assert answer["held"] == "P-1" and answer["decides"] == "Ana Ortiz", answer
    assert "Not made yet" in answer["status"]
    assert due_of(stack) == "2026-11-06"  # nothing changed
    [p] = held(stack)
    assert (p["deciders"], p["acts_for"], p["action"], p["status"]) == (
        ["ana"], ["ben"], "change-due-date", "waiting")
    assert p["said"].startswith("Change a customer question's due date: Q-1002, with due 2026-11-13.")
    assert "as it stands: status waiting on finance, due date 2026-11-06" in p["said"]
    holds = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "change_due_date"]
    assert [e["decision"] for e in holds] == ["hold"]
    [card] = [m for m in stack.inbox("ana") if m["text"].startswith("P-1 waits")]
    assert f"{approving}/decide/?proposal={p['digest']}" in card["text"]


def test_what_the_decider_approves_is_made_and_whoever_asked_is_told(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    decided = decide(approving, provider, [p["digest"]])
    assert decided.status_code == 200, decided.text
    assert decided.json() == {"decided": ["P-1"], "decision": "approve", "by": "Ana Ortiz"}
    assert due_of(stack) == "2026-11-06"  # the gateway makes it, not the page
    assert sweep(stack)["made"] == 1
    assert due_of(stack) == "2026-11-13"
    [p] = held(stack)
    assert (p["status"], p["decided_by"]) == ("made", "ana")
    told = [m["text"] for m in stack.inbox("ben")]
    assert any(t.startswith("Ana Ortiz approved P-1, and a5s has made it: Change a customer "
                            "question's due date: Q-1002") for t in told), told
    with db.transaction(stack.admin) as conn:  # and the agent's next run knows
        notices = [r["content"] for r in conn.execute(
            "select content from turns where person = 'ben' and role = 'notice'")]
    assert any("approved P-1" in n for n in notices)
    kinds = [(e["kind"], e["action"], e["decision"]) for e in stack.ledger()
             if e["kind"] in ("proposal", "tool", "admin") and e["action"] != "apply"]
    assert ("admin", "decide", "record") in kinds and ("proposal", "decide", "allow") in kinds
    assert ("tool", "change_due_date", "record") in kinds and ("proposal", "made", "record") in kinds
    assert sweep(stack)["made"] == 0  # once


def test_a_rejected_change_isnt_made(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]], "reject").status_code == 200
    sweep(stack)
    assert due_of(stack) == "2026-11-06"
    assert held(stack)[0]["status"] == "rejected"
    assert any(m["text"].startswith("Ana Ortiz didn't approve P-1") for m in stack.inbox("ben"))


def test_a_change_isnt_made_if_its_record_changed_since(stack, approving, provider, monkeypatch):
    asked(stack)
    [p] = held(stack)
    records = dict(stack.gateway.scenario._records)
    records["Q-1002"] = {**records["Q-1002"], "status": "open"}  # someone answered it meanwhile
    monkeypatch.setattr(stack.gateway.scenario, "_records", records)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    assert due_of(stack) == "2026-11-06"
    assert held(stack)[0]["status"] == "not made"
    assert any("since Q-1002 changed after it was asked for" in m["text"]
               for m in stack.inbox("ben"))


def test_nobody_decides_a_change_they_asked_for(stack, approving):
    """Ana owns billing, so only she could decide a change to Q-1001, which she asks for."""
    answer = asked(stack, ("change_due_date", {"key": "Q-1001", "due": "2026-11-20"}), "ana",
                   "Move Q-1001 to 2026-11-20.")
    assert answer.startswith("Not allowed: nobody but the people this run is for may decide")
    assert held(stack) == []
    [entry] = [e for e in stack.ledger() if e["action"] == "change_due_date"]
    assert (entry["decision"], entry["reasons"]) == ("deny", ["someone-else-decides"])


def test_without_a_decision_page_a_change_isnt_held(stack):
    answer = asked(stack)
    assert answer.startswith("Not allowed: a change can't wait for a decision here")
    assert held(stack) == []


def test_a_decision_is_signed_for_that_decision_on_that_change_alone(stack, approving, provider):
    asked(stack)
    asked(stack, ("close_question", {"key": "Q-1002"}), said="And close Q-1002.")
    one, two = (p["digest"] for p in held(stack))
    token, salt = signed(approving, provider, [one], "approve")

    def send(digests, decision="approve", t=token, s=salt):
        return httpx.post(f"{approving}/decide/proposals", json={
            "proposals": digests, "decision": decision, "salt": s},
            headers={"Authorization": f"Bearer {t}"})

    assert send([one], "reject").status_code == 403  # signed to approve, not to reject
    assert send([two]).status_code == 403  # nor for another change
    assert send([one, two]).status_code == 403  # nor for more
    assert send([one]).status_code == 200
    assert send([one]).status_code == 409  # a sign-in decides once
    silent = decide(approving, provider, [two], fresh=False)  # a session's silent sign-in
    assert silent.status_code == 401 and "sign in again" in silent.json()["detail"]
    ben = decide(approving, provider, [two], person="ben")  # he asked for it
    assert ben.status_code == 403 and "may not decide P-2" in ben.json()["detail"]


def test_changes_that_arent_sensitive_can_be_decided_together(stack, approving, provider):
    asked(stack)
    asked(stack, ("close_question", {"key": "Q-1002"}), said="And close Q-1002.")
    digests = [p["digest"] for p in held(stack)]
    together = decide(approving, provider, digests)
    assert together.status_code == 200 and together.json()["decided"] == ["P-1", "P-2"]
    sweep(stack)
    assert [p["status"] for p in held(stack)] == ["made", "made"]
    assert record_of(stack.gateway.scenario, "Q-1002").fields["status"] == "closed"


def test_a_sensitive_change_is_decided_on_its_own(stack, approving, provider):
    asked(stack)
    asked(stack, ("close_question", {"key": "Q-1002"}), said="And close Q-1002.")
    with db.transaction(stack.admin) as conn:
        conn.execute("update proposals set sensitive = true where id = 2")  # as a destructive tool's
    together = decide(approving, provider, [p["digest"] for p in held(stack)])
    assert together.status_code == 409 and "on its own" in together.json()["detail"]


def test_deciders_see_values_the_agent_wrote_itself(stack, approving):
    asked(stack, said="Please move Q-1002 out a week.")  # Ben named no date
    [p] = held(stack)
    assert p["flags"] == [("2026-11-13 came from the assistant itself, not from the records or "
                           "from Ben Okafor")]
    [card] = [m for m in stack.inbox("ana") if m["text"].startswith("P-1 waits")]
    assert "What to know:\n- 2026-11-13 came from the assistant itself" in card["text"]


def test_the_page_shows_a_decider_what_waits_for_them_and_nobody_else(stack, approving, provider):
    asked(stack)
    review = httpx.post(f"{approving}/decide/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='ana')}"})
    assert review.status_code == 200, review.text
    [shown] = review.json()["proposals"]
    assert (shown["key"], shown["status"], shown["sensitive"]) == ("P-1", "waiting", False)
    ben = httpx.post(f"{approving}/decide/review",
                     headers={"Authorization": f"Bearer {provider.id_token(person='ben')}"})
    assert ben.json()["proposals"] == []


def test_a_decider_who_no_longer_owns_the_part_decides_nothing(stack, approving, provider,
                                                                monkeypatch):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=("instance-approver",)))
    sweep(stack)
    assert held(stack)[0]["status"] == "waiting" and due_of(stack) == "2026-11-06"


def test_a_decision_waits_a_day_after_the_deciders_authenticator_was_reset(stack, approving,
                                                                            provider, monkeypatch):
    asked(stack)
    [p] = held(stack)
    now = stack.gateway.clock()
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], reset_at=now - timedelta(hours=2)))
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    assert held(stack)[0]["status"] == "waiting"  # a reset is how a stolen identity starts
    stack.at((now + timedelta(hours=21)).isoformat())
    sweep(stack)
    assert held(stack)[0]["status"] == "waiting"
    stack.at((now + timedelta(hours=22, minutes=1)).isoformat())  # a day after the reset
    sweep(stack)
    assert held(stack)[0]["status"] == "made"


def test_a_change_nobody_decides_is_chased_and_then_lapses(stack, approving, monkeypatch):
    stack.at("2026-11-02T09:30:00+00:00")  # a Monday
    asked(stack)
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "ana", replace(people["ana"], manager="lena"))
    stack.at("2026-11-04T10:00:00+00:00")  # two working days on
    sweep(stack)
    sweep(stack)  # once
    assert sum(m["text"].startswith("Still waiting for your decision") for m in stack.inbox("ana")) == 1
    stack.at("2026-11-09T10:00:00+00:00")  # five
    sweep(stack)
    [up] = [m["text"] for m in stack.inbox("lena")]
    assert up.startswith("P-1 has waited 5 working days for Ana Ortiz to decide it.")
    stack.at("2026-11-16T10:00:00+00:00")  # ten
    sweep(stack)
    assert held(stack)[0]["status"] == "lapsed" and due_of(stack) == "2026-11-06"
    assert any(m["text"].startswith("Nobody decided P-1 within 10 working days")
               for m in stack.inbox("ben"))


def test_a_held_change_keeps_the_values_its_handles_stand_for(stack):
    values = {"7f3a9c2b": "accounts@northwind.test"}
    args = {"key": "Q-1001", "to": "[h:7f3a9c2b]", "copy": ["[h:7f3a9c2b] and [h:00000000]"]}
    assert proposals.handles_in(args) == {"7f3a9c2b", "00000000"}
    assert proposals.resolved(args, values) == {
        "key": "Q-1001", "to": "accounts@northwind.test",
        "copy": ["accounts@northwind.test and [h:00000000]"]}


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_the_nonce_commits_to_the_decision_and_every_change(decision):
    one = proposals.nonce(["b" * 64, "a" * 64], decision, "salt" * 4)
    assert one == proposals.nonce(["a" * 64, "b" * 64], decision, "salt" * 4)  # in any order
    assert one != proposals.nonce(["a" * 64], decision, "salt" * 4)
    other = "reject" if decision == "approve" else "approve"
    assert one != proposals.nonce(["a" * 64, "b" * 64], other, "salt" * 4)


def test_the_decision_page_runs_only_its_own_script_and_shows_only_text(approving):
    page = httpx.get(f"{approving}/decide/")
    script = httpx.get(f"{approving}/decide/decide.js")
    assert page.status_code == script.status_code == 200
    policy = page.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe" not in policy and "innerHTML" not in script.text


def test_a_decider_reviews_and_approves_in_the_browser(stack, approving, provider, browser):
    asked(stack, said="Please move Q-1002 out a week.")
    [p] = held(stack)
    page = browser.new_page()
    page.goto(f"{approving}/decide/?proposal={p['digest']}")  # signed in, to see what waits
    page.wait_for_selector("article >> text=Q-1002", timeout=30000)
    assert page.inner_text("#who") == "Ana Ortiz"
    assert "max_age" not in provider.asked[-1]  # seeing what waits needs no fresh sign-in
    assert page.inner_text("article h3") == "P-1"
    assert "as it stands: status waiting on finance" in page.inner_text("article .said")
    assert page.locator("article .flags li").all_inner_texts() == [
        "2026-11-13 came from the assistant itself, not from the records or from Ben Okafor"]
    page.click("article button >> text=Approve")  # afresh, for this decision alone
    page.wait_for_selector("#status >> text=You approved P-1", timeout=30000)
    assert provider.asked[-1]["max_age"] == "0"
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    stack.scheduler().decided()
    assert due_of(stack) == "2026-11-13"


def test_a_change_and_its_decision_go_a_year_after_it_ended(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]], "reject")
    sweep(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("update proposals set ended_at = now() - interval '13 months'")
    with stack.client() as c:
        gone = c.post("/retention/sweep").json()["deleted"]
    assert held(stack) == [] and gone.get("changes") == 1 and gone.get("decisions") == 1, gone
