"""Round 10: an audit export says what period it holds, with the entries either side of it, so
`a5s audit verify`, against the ledger's locked copies, shows it holds the whole period, from
its start to its end (core/audit.py's bounded and ended). Without the copies it says how
little holding together proves. And the ledger's times never go back, whatever a writer's
clock says, so a period's entries are those between two times (core/ledger.py)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from a5s import db
from a5s.core import anchor, audit, ledger
from a5s.core.stores import FolderStore

AUDITOR = "kofi"


def talked(stack, times: int = 1) -> None:
    for _ in range(times):
        stack.model.reply("Hello, Ana.")
        assert stack.say("Hello") == "Hello, Ana."


@pytest.fixture
def cli(stack, monkeypatch, tmp_path):
    """The command line, on the stack's core, with the ledger's locked copies in a folder."""
    from a5s import cli as command_line
    from conftest import SERVICE_TOKEN

    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("A5S_ANCHOR_STORE", f"file://{tmp_path / 'copies'}")
    return command_line.main


def copy(stack, tmp_path) -> FolderStore:
    store = FolderStore(tmp_path / "copies")
    with db.transaction(db.as_role(stack.admin, "anchor")) as conn:
        anchor.anchor(conn, store)
    return store


def at_of(line: dict) -> datetime:
    return datetime.fromisoformat(json.loads(line["entry"])["at"])


def export(cli, out, **period) -> tuple[dict, list[dict]]:
    flags = [x for k, v in period.items() for x in (f"--{k}", v.isoformat())]
    cli(["audit", "export", "--by", AUDITOR, *flags, "--out", str(out)])
    header, *lines = [json.loads(line) for line in out.read_text().splitlines()]
    return header["export"], lines


def write(out, bounds: dict, lines: list[dict]) -> None:
    out.write_text("".join(json.dumps(x) + "\n" for x in [{"export": bounds}, *lines]))


def test_an_export_holds_its_period_with_the_entries_either_side(stack, tmp_path, cli, capsys):
    talked(stack, 2)
    with db.transaction(stack.admin) as conn:
        made = [json.loads(r["entry"]) for r in conn.execute(
            "select entry from ledger order by seq")]
    since = datetime.fromisoformat(made[3]["at"])  # from the fourth entry on
    talked(stack, 2)
    until = datetime.now(UTC)
    talked(stack)  # and entries after the period, too
    copy(stack, tmp_path)
    bounds, lines = export(cli, tmp_path / "p.jsonl", since=since, until=until)
    assert lines[0]["seq"] == bounds["first"] and lines[-1]["seq"] == bounds["last"]
    assert at_of(bounds["before"]) < since <= at_of(lines[0])
    assert at_of(lines[-1]) < until <= at_of(bounds["after"])
    capsys.readouterr()
    cli(["audit", "verify", str(tmp_path / "p.jsonl")])
    said = capsys.readouterr().out
    assert "match the ledger's locked copies, with the entries either side" in said


def test_an_export_cut_short_at_its_end_doesnt_check_out(stack, tmp_path, cli):
    talked(stack, 3)
    until = datetime.now(UTC)
    talked(stack)
    copy(stack, tmp_path)
    out = tmp_path / "p.jsonl"
    bounds, lines = export(cli, out, until=until)
    write(out, bounds, lines[:-6])  # the period's last six entries, left out
    with pytest.raises(SystemExit, match="the period's entries are"):
        cli(["audit", "verify", str(out)])
    # and what it says of the period, rewritten to match
    write(out, {**bounds, "last": lines[-7]["seq"], "after": None}, lines[:-6])
    with pytest.raises(SystemExit, match="made in the period, which the export leaves out"):
        cli(["audit", "verify", str(out)])
    write(out, {**bounds, "last": lines[-7]["seq"], "after": lines[-6]}, lines[:-6])
    with pytest.raises(SystemExit, match="the entry after the period, .* was made in it"):
        cli(["audit", "verify", str(out)])


def test_an_export_cut_short_at_its_start_doesnt_check_out(stack, tmp_path, cli):
    talked(stack)
    since = datetime.now(UTC)
    talked(stack, 3)
    copy(stack, tmp_path)
    out = tmp_path / "p.jsonl"
    bounds, lines = export(cli, out, since=since)
    write(out, bounds, lines[4:])  # the period's first four, left out
    with pytest.raises(SystemExit, match="the period's entries are"):
        cli(["audit", "verify", str(out)])
    write(out, {**bounds, "first": lines[4]["seq"], "before": lines[3]}, lines[4:])
    with pytest.raises(SystemExit, match="the entry before the period, .* was made in it"):
        cli(["audit", "verify", str(out)])


def test_without_the_copies_verify_says_how_little_holding_together_proves(
        stack, tmp_path, cli, capsys, monkeypatch):
    talked(stack)
    monkeypatch.delenv("A5S_ANCHOR_STORE")
    out = tmp_path / "p.jsonl"
    bounds, lines = export(cli, out)
    forged = [dict(line) for line in lines]  # an entry changed, and every hash after it again
    entry = json.loads(forged[2]["entry"])
    forged[2]["entry"] = ledger.canonical({**entry, "decision": "deny"})
    prev = bytes.fromhex(forged[2]["prev_hash"])
    for line in forged[2:]:
        line["prev_hash"] = prev.hex()
        line["hash"] = hashlib.sha256(prev + line["entry"].encode()).hexdigest()
        prev = bytes.fromhex(line["hash"])
    write(out, bounds, forged)
    capsys.readouterr()
    cli(["audit", "verify", str(out)])  # it holds together, as it would...
    said = capsys.readouterr().out
    assert "which alone proves little" in said and "A5S_ANCHOR_STORE" in said
    monkeypatch.setenv("A5S_ANCHOR_STORE", f"file://{tmp_path / 'copies'}")
    copy(stack, tmp_path)
    with pytest.raises(SystemExit, match="differs from the ledger's locked copy"):
        cli(["audit", "verify", str(out)])  # ...but not against the locked copies


def test_the_ledgers_times_never_go_back_whatever_a_writers_clock_says(stack, monkeypatch):
    behind = datetime.now(UTC) - timedelta(hours=1)

    class Behind(datetime):  # a writer whose own clock is an hour behind
        @classmethod
        def now(cls, tz=None):
            return behind

    monkeypatch.setattr(ledger, "datetime", Behind)
    with db.transaction(stack.cfg.database_url) as conn:
        for n in range(3):
            ledger.append(conn, {"kind": "test", "action": f"made-{n}", "run": None,
                                 "instance": None, "decision": "record"})
    monkeypatch.undo()
    with db.transaction(stack.admin) as conn:  # the database's clock goes back, as after a
        head = conn.execute("select seq, hash from ledger order by seq desc limit 1").fetchone()
        ahead = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()  # failover
        text = ledger.canonical({"kind": "test", "action": "ahead", "run": None,
                                 "instance": None, "decision": "record",
                                 "seq": head["seq"] + 1, "at": ahead})
        conn.execute("insert into ledger (seq, entry, prev_hash, hash) values (%s, %s, %s, %s)",
                     (head["seq"] + 1, text, head["hash"],
                      hashlib.sha256(bytes(head["hash"]) + text.encode()).digest()))
    with db.transaction(stack.cfg.database_url) as conn:
        ledger.append(conn, {"kind": "test", "action": "after", "run": None, "instance": None,
                             "decision": "record"})
    with db.transaction(stack.admin) as conn:
        times = [datetime.fromisoformat(json.loads(r["entry"])["at"]) for r in conn.execute(
            "select entry from ledger order by seq")]
        assert times == sorted(times)  # in the chain's order, whoever wrote them
        assert times[-1] >= datetime.fromisoformat(ahead)
        made = [json.loads(r["entry"]) for r in conn.execute(
            "select entry from ledger where kind = 'test' order by seq")]
        found = audit.search(conn, since=datetime.fromisoformat(made[1]["at"]), kind="test")
    assert [e["action"] for e in found["entries"]][-2:] == ["ahead", "after"]
    assert "made-0" not in [e["action"] for e in found["entries"]] or (
        made[0]["at"] == made[1]["at"])  # only what was made from then on
