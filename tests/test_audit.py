"""The audit trail (core/audit.py, docs/administration.md): an auditor, or assurance, finds a
period's entries as asked, a page at a time; exports a period exactly as the ledger holds it,
which anyone can check holds together, and, with the locked copies, is the ledger's own; and
gets a report of who holds each role and who did what. Each read of the trail is in the
ledger too. Nobody else reads it."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from a5s import db
from a5s.core import anchor, audit
from a5s.core.stores import FolderStore
from test_approvals import decide as approve
from test_approvals import proposed
from test_approvals import sign_in as sign_in_to_approve

AUDITOR = "kofi"  # the sample's assurance


def read(stack, path: str, by: str = AUDITOR, **params):
    with stack.client() as c:
        return c.get(f"/audit/{path}", params={"by": by, **params})


def found(stack, by: str = AUDITOR, **params) -> dict:
    r = read(stack, "entries", by, **params)
    assert r.status_code == 200, r.text
    return r.json()


def talked(stack) -> None:
    stack.model.reply("Hello, Ana.")
    assert stack.say("Hello") == "Hello, Ana."


def test_an_auditor_finds_a_periods_entries_as_asked(stack):
    talked(stack)
    runs = found(stack, kind="run")["entries"]
    assert runs and {e["kind"] for e in runs} == {"run"}
    assert {e["action"] for e in runs} >= {"open", "close"}
    hers = found(stack, person="ana")["entries"]
    assert hers and all("ana" in (e.get("acts_for") or [])
                        or (e.get("args") or {}).get("by") == "ana" for e in hers)
    assert found(stack, person="nobody-here")["entries"] == []
    hour = datetime.now(UTC) + timedelta(hours=1)
    assert found(stack, since=hour.isoformat())["entries"] == []
    assert found(stack, until=hour.replace(tzinfo=None).isoformat())["entries"]  # UTC's
    first = found(stack, limit=2)
    assert len(first["entries"]) == 2 and first["next"] == first["entries"][-1]["seq"]
    second = found(stack, limit=2, after=first["next"])
    assert second["entries"][0]["seq"] == first["next"] + 1


def test_only_an_auditor_or_assurance_reads_the_trail(stack):
    talked(stack)
    for who in ("ana", "nobody-here"):
        r = read(stack, "entries", who)
        assert r.status_code == 403 and "auditor" in r.json()["detail"]
    with stack.client() as c:
        assert c.get("/audit/entries").status_code == 422  # by whom, always


def test_each_read_of_the_trail_is_in_the_ledger(stack):
    talked(stack)
    found(stack, kind="run", person="ana")
    assert read(stack, "export").status_code == 200
    assert read(stack, "report").status_code == 200
    reads = [e for e in stack.ledger() if e["kind"] == "audit"]
    assert [e["action"] for e in reads] == ["search", "export", "report"]
    searched = reads[0]["args"]
    assert (searched["by"], searched["kind"]) == (AUDITOR, "run")
    # who read it, through the service token, which names them; and whom they asked about, as
    # a stand-in under the deployment's own key, which no hash of an id in the directory finds
    assert all(e["args"]["through"] == "the service token" for e in reads)
    with db.transaction(stack.admin) as conn:
        assert searched["person"] == audit.stand_in(audit.key(conn), "ana")


def test_an_export_holds_together_and_a_changed_one_doesnt(stack):
    talked(stack)
    page = read(stack, "export").json()
    lines = page["entries"]
    assert len(lines) > 3 and page["head"]["seq"] >= lines[-1]["seq"]
    assert audit.checks(lines) is None
    changed = [dict(line) for line in lines]
    entry = json.loads(changed[2]["entry"])
    changed[2]["entry"] = json.dumps({**entry, "decision": "allow"})
    assert "isn't as the ledger made it" in audit.checks(changed)
    assert "doesn't follow" in audit.checks(lines[:1] + lines[2:])  # one left out
    assert audit.checks(lines[1:]) is None  # a period can start anywhere


def test_an_export_matches_the_ledgers_locked_copies(stack, tmp_path):
    talked(stack)
    store = FolderStore(tmp_path / "copies")
    with db.transaction(db.as_role(stack.admin, "anchor")) as conn:
        last = anchor.anchor(conn, store)[-1].seq  # what the copier copied
    copied = read(stack, "export", until=datetime.now(UTC).isoformat()).json()["entries"]
    copied = [line for line in copied if line["seq"] <= last]
    assert copied and audit.copied(copied, store) is None
    forged = [dict(line) for line in copied]
    forged[0]["hash"] = "00" * 32
    assert "differs from the ledger's locked copy" in audit.copied(forged, store)
    talked(stack)  # entries after the last copy
    later = read(stack, "export", after=last).json()["entries"]
    assert later and "aren't in the locked copies" in audit.copied(later, store)


def test_the_report_names_who_holds_each_role_and_who_did_what(stack, approving, provider):
    lower = proposed(stack, level=0)
    assert approve(approving, lower["digest"],
                   *sign_in_to_approve(approving, provider, lower["digest"])).status_code == 200
    r = read(stack, "report")
    assert r.status_code == 200, r.text
    roles = {row["role"]: row["held_by"] for row in r.json()["roles"]}
    assert "ana" in roles["instance-approver"] and roles["assurance"] == [AUDITOR]
    assert roles["part-owner:billing"] == ["ana"] and roles["release-approver"] == ["rosa"]
    assert roles["agent-owner:assistant"]  # someone owns each agent
    [approved] = [a for a in r.json()["acts"] if a["action"] == "approve"]
    assert (approved["by"], approved["what"]) == ("ana", "approved settings")
    assert approved["about"]["digest"] == lower["digest"]


def test_the_command_line_exports_a_period_and_checks_it(stack, monkeypatch, capsys, tmp_path):
    from a5s import cli
    from conftest import SERVICE_TOKEN

    talked(stack)
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.delenv("A5S_ANCHOR_STORE", raising=False)
    out = tmp_path / "period.jsonl"
    cli.main(["audit", "export", "--by", AUDITOR, "--out", str(out)])
    assert "Check it with: a5s audit verify" in capsys.readouterr().out
    cli.main(["audit", "verify", str(out)])
    said = capsys.readouterr().out  # without the locked copies, it says how little that proves
    assert "hold together, which alone proves little" in said and "A5S_ANCHOR_STORE" in said
    lines = out.read_text().splitlines()
    assert "export" in json.loads(lines[0])  # what it says of the period, first
    entry = json.loads(lines[1])
    lines[1] = json.dumps({**entry, "entry": entry["entry"].replace('"seq"', '"seq" ', 1)})
    out.write_text("\n".join(lines) + "\n")
    with pytest.raises(SystemExit, match="doesn't check out"):
        cli.main(["audit", "verify", str(out)])
    cli.main(["audit", "report", "--by", AUDITOR])
    assert "assurance: kofi" in capsys.readouterr().out
