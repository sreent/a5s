"""Round 15, D8: the ledger's copies showed in neither the status nor the operators' figures, so
a copier that stopped, as after a restore from a backup, went unnoticed until assurance
checked. Now the copier records how it's doing each time it copies, or can't, and the core's
status and figures say how far its copies hold the ledger, since when, and whether its last
try failed, or it stopped until someone acts. Never what the store said, which stays in the
copier's log."""

from __future__ import annotations

import psycopg
import pytest

from a5s import cli, db
from a5s.config import Config
from a5s.core import metrics, status
from a5s.core.stores import FolderStore
from test_anchor import write
from test_metrics import collected, figures  # noqa: F401

COPIES = ("a5s.ledger.copies.behind", "a5s.ledger.copies.age", "a5s.ledger.copies.failing",
          "a5s.ledger.copies.stopped")


def stood(stack) -> dict:
    with stack.client() as c:
        return c.get("/status").json()


def copier(stack, store: FolderStore) -> None:
    """The copier, once, as its own role, as `a5s anchor` runs it."""
    cfg = Config(database_url=db.as_role(stack.admin, "anchor"), gateway_url="http://unused",
                 service_token="", root=store.path, anchor_store=store.path.as_uri())
    cli._anchor(cfg, every=None)


def top(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select max(seq) as top from ledger").fetchone()["top"]


def test_the_status_and_figures_say_how_far_the_copies_hold_the_ledger(stack, tmp_path, figures):  # noqa: F811
    assert stood(stack)["copies"] is None  # no copier has run here
    assert "The ledger's copies: none recorded" in status.told(stood(stack))
    assert all(metrics.figures(stood(stack))[name] == [] for name in COPIES)  # nothing to say
    store = FolderStore(tmp_path / "copies")
    copier(stack, store)
    copies = stood(stack)["copies"]
    assert (copies["through"], copies["behind"], copies["problem"], copies["stopped"]) == (
        top(stack), 0, None, False)
    write(stack.admin, 3)
    copies = stood(stack)["copies"]
    assert copies["behind"] == 3
    assert f"through entry {copies['through']}, 3 entries behind, copied 0 minutes ago" in \
        status.told(stood(stack))
    found = collected(figures)
    assert found["a5s.ledger.copies.behind"] == [(3.0, {})]
    assert found["a5s.ledger.copies.failing"] == found["a5s.ledger.copies.stopped"] == [(0.0, {})]
    assert found["a5s.ledger.copies.age"][0][0] < 60


def test_a_copier_a_restore_stopped_shows_so_until_its_put_back(stack, tmp_path, figures):  # noqa: F811
    store = FolderStore(tmp_path / "copies")
    copier(stack, store)
    backup = top(stack)
    write(stack.admin, 3)
    copier(stack, store)  # copied since the backup
    with psycopg.connect(stack.admin) as conn:  # the backup, restored
        conn.execute("alter table ledger disable trigger user")
        conn.execute("delete from ledger where seq > %s", (backup,))
        conn.execute("alter table ledger enable trigger user")
    with pytest.raises(SystemExit):
        copier(stack, store)
    copies = stood(stack)["copies"]
    assert copies["stopped"] and copies["problem"].startswith(
        f"the ledger's copies hold entries {backup + 1} to {backup + 3}, which the database lacks")
    assert "The ledger's copies: stopped, until someone acts: the ledger's copies hold" in \
        status.told(stood(stack))
    assert collected(figures)["a5s.ledger.copies.stopped"] == [(1.0, {})]


def test_a_store_that_fails_shows_as_failing_and_says_nothing_of_itself(
        stack, tmp_path, figures, monkeypatch):  # noqa: F811
    store = FolderStore(tmp_path / "copies")
    copier(stack, store)
    write(stack.admin, 1)

    def down(self, key, body):
        raise OSError("https://store.example/a5s?sig=secret refused the copy")

    monkeypatch.setattr(FolderStore, "put", down)
    with pytest.raises(OSError):
        copier(stack, store)
    copies = stood(stack)["copies"]
    assert (copies["problem"], copies["stopped"], copies["behind"]) == (
        "OSError, as the copier's log says", False, 1)
    assert "sig=secret" not in str(stood(stack))
    assert collected(figures)["a5s.ledger.copies.failing"] == [(1.0, {})]
    monkeypatch.undo()
    copier(stack, store)  # the store is back: it copies, and the problem goes
    copies = stood(stack)["copies"]
    assert (copies["problem"], copies["behind"]) == (None, 0)


def test_only_the_copier_records_how_its_copies_stand(stack):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction(
            db.as_role(stack.admin, "gateway")) as conn:
        conn.execute("insert into copier (only_one, through) values (true, 1)")
