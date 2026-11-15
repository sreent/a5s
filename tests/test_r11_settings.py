"""Round 11, reviewer B (B-1): a version of the settings comes into force only on the version
it was written against. A version written from version N, and approved as changing that, came
into force on whatever was in force when its last approval came, undoing what had come in
since; and the settings app's Send asked for what was reviewed against whatever was in force
when it was sent."""

import base64
import json

import yaml

from a5s import db
from test_approvals import decide, proposed, serves, sign_in
from test_group_roles import approve as approved
from test_settings_app import api


def propose(stack, raw: dict) -> dict:
    with stack.client() as c:
        r = c.post("/settings/proposals",
                   json={"raw": base64.b64encode(yaml.safe_dump(raw).encode()).decode()})
    r.raise_for_status()
    return r.json()


def approve(stack, approving, provider, digest: str, person: str):
    token, salt = sign_in(approving, provider, digest, person)
    done = decide(approving, digest, token, salt)
    stack.scheduler().apply_approved()
    return done


def test_a_version_written_against_one_no_longer_in_force_never_comes_into_force(
        stack, approving, provider):
    with db.transaction(stack.admin) as conn:
        now = yaml.safe_load(bytes(conn.execute(
            "select raw from settings_versions order by serial desc limit 1").fetchone()["raw"]))
    narrower = yaml.safe_load(yaml.safe_dump(now))
    narrower["serial"] = now["serial"] + 1
    narrower["instances"]["assistant-finance"]["serves"] = ["ana"]  # Ben no longer served
    later = yaml.safe_load(yaml.safe_dump(now))  # written from the same version, numbered after
    later["serial"] = now["serial"] + 2
    later["instances"]["assistant-finance"]["level"] = 0
    later["groups"] = {"a5s-auditors": ["auditor"]}  # which waits for assurance too
    b, c = propose(stack, narrower), propose(stack, later)
    approve(stack, approving, provider, c["digest"], "ana")  # as changing the one in force then
    approve(stack, approving, provider, b["digest"], "ana")
    assert serves(stack) == ["ana"]
    approve(stack, approving, provider, c["digest"], "kofi")  # its last approval
    with db.transaction(stack.admin) as conn:
        outcome = conn.execute("select outcome from settings_proposals where digest = %s",
                               (c["digest"],)).fetchone()["outcome"]
    assert outcome == "superseded" and serves(stack) == ["ana"]  # Ben stays out
    refused = approve(stack, approving, provider, c["digest"], "omar")
    assert refused.status_code == 409 and "superseded" in refused.text


def test_send_asks_only_for_what_was_reviewed_against_the_version_in_force(
        stack, approving, provider):
    now = api(approving, provider, "/settings/api").json()
    draft = now["in_force"]["data"]
    draft["instances"]["assistant-finance"]["level"] = 0  # what Ana changes in the forms
    text = json.dumps(draft)
    seen = api(approving, provider, "/settings/api/review", text=text).json()
    assert seen["in_force"] == now["in_force"]["serial"]
    narrower = proposed(stack, serves=["ana"])  # meanwhile Ben stops being served
    approved(stack, approving, provider, narrower["digest"], "ana")
    assert serves(stack) == ["ana"]
    sent = api(approving, provider, "/settings/api/requests", text=text, base=seen["in_force"])
    assert sent.status_code == 409 and "review it again" in sent.text
    again = api(approving, provider, "/settings/api/review", text=text).json()
    sent = api(approving, provider, "/settings/api/requests", text=text, base=again["in_force"])
    assert sent.status_code == 202  # reviewed against what's in force now
