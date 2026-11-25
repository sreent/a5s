"""Round 16, reviewer D: what `a5s restore` redoes, and what waits for it (core/restoring.py).

- D1: a customer's erasure since the backup counted as erased again, though the ledger keeps
  their address by its digest alone, so nothing of theirs went: the officer asks again.
- D3, D4: a backup brought back the tokens of an account someone disconnected since, the status
  of an instance suspended since, and a seal key retired since, unretired.
- D6: with `restore.id` left set, an upgrade that brought a migration failed, as the restore
  checked the schema before it found it had run already.
- D9: a core that started before the restore opened runs, answering again what it answered
  since the backup."""

from __future__ import annotations

from dataclasses import replace

import pytest

from a5s import cli, db
from a5s.config import Config
from a5s.core import anchor, customers, ledger, restoring
from a5s.core.stores import FolderStore
from test_anchor import copy, write
from test_r15_restore import backed_up, put_back, restored


def since_backup(database, tmp_path, *entries: dict) -> FolderStore:
    """Two entries copied at the backup, then `entries` and their copies, then the restore."""
    store = FolderStore(tmp_path / "copies")
    write(database, 2)
    copy(database, store)
    with db.transaction(database) as conn:
        for entry in entries:
            ledger.append(conn, {"run": None, "instance": None, "acts_for": [],
                                 "decision": "record", **entry})
    copy(database, store)
    restored(database, 2)
    return store


def test_a_customers_erasure_since_the_backup_is_for_the_officer_to_ask_again(database,
                                                                              tmp_path):
    whom = customers.subject("pat@fabrikam.example")
    store = since_backup(database, tmp_path, {
        "kind": "admin", "action": "erase", "args": {"person": whom, "by": "dpo"}})
    done = put_back(database, store)
    assert (done["erased_again"], done["erase_again"]) == (0, [whom])
    assert f"to erase {whom}" in restoring.told(done)


def test_restore_lets_go_of_accounts_and_sets_instances_and_keys_as_they_were_since(
        database, tmp_path):
    with db.transaction(database) as conn:  # as the backup has them
        conn.execute("insert into delegations (person, system, sealed) values "
                     "('ben', 'itsm', '\\x00'), ('ana', 'itsm', '\\x00')")
        conn.execute("insert into instances (id, definition, release, model, status) values "
                     "('assistant-finance', 'assistant', 'r1', 'm', 'active'), "
                     "('watcher-finance', 'watcher', 'r2', 'm', 'suspended')")
        conn.execute("update instances set suspended_by = 'ana' where id = 'watcher-finance'")
        conn.execute("insert into seal_keys (fingerprint) values ('0123456789abcdef')")
    store = since_backup(
        database, tmp_path,
        {"kind": "admin", "action": "disconnect", "acts_for": ["ben"],
         "args": {"system": "itsm", "why": "they let it go"}},
        {"kind": "admin", "action": "suspend", "instance": "assistant-finance",
         "args": {"by": "omar", "suspended_by": "omar"}},
        {"kind": "admin", "action": "resume", "instance": "watcher-finance",
         "args": {"by": "ana"}},
        {"kind": "admin", "action": "retire-seal-key",
         "args": {"fingerprint": "0123456789abcdef", "leaked": True}})
    done = put_back(database, store)
    assert (done["let_go"], done["set_back"], done["keys_retired"]) == (1, 2, 1)
    with db.transaction(database) as conn:
        assert [r["person"] for r in conn.execute("select person from delegations")] == ["ana"]
        statuses = {r["id"]: (r["status"], r["suspended_by"]) for r in conn.execute(
            "select id, status, suspended_by from instances")}
        key = conn.execute("select retired_at, leaked from seal_keys").fetchone()
    assert statuses == {"assistant-finance": ("suspended", "omar"),
                        "watcher-finance": ("active", None)}
    assert key["retired_at"] is not None and key["leaked"]


def test_a_restore_named_already_runs_before_the_schema_is_checked(database, tmp_path,
                                                                  monkeypatch, capsys):
    store = backed_up(database, tmp_path)
    with db.transaction(db.as_role(database, "gateway")) as conn:
        restoring.restore(conn, store, "nightly-2026-11-20")

    def newer(_url: str) -> None:  # as after an upgrade that brings a migration
        raise SystemExit("the database needs migrating")
    monkeypatch.setattr(db, "known", newer)
    monkeypatch.setattr(cli.build, "store", lambda _cfg: store)
    cfg = replace(Config.from_env(), database_url=db.as_role(database, "gateway"))
    cli._restore(cfg, "nightly-2026-11-20")
    assert "already" in capsys.readouterr().out


def test_no_run_opens_while_the_copier_waits_for_a_restore(stack, tmp_path):
    store = FolderStore(tmp_path / "copies")
    copy(stack.admin, store)
    write(stack.admin, 2)
    copy(stack.admin, store)
    restored(stack.admin, 1)  # the database restored, and a core started on it
    with pytest.raises(anchor.AnchorError) as stops:
        copy(stack.admin, store)
    anchor.stuck(db.as_role(stack.admin, "anchor"), str(stops.value), stopped=True)  # as the
    # copier records it, for the status
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", "ben")}})
    assert r.status_code == 503 and "a5s restore" in r.text  # waits, rather than answer again
