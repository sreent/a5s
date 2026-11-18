"""Round 15, the operator's finding (D1): restoring the database from a backup broke the ledger's
copies for good, and sent again what had gone since, with no runbook. Now the copier copies
nothing while its copies hold entries the database lacks, rather than fork them, and a core that
reads the copies won't start; and `a5s restore` puts those entries back, takes as done what their
runs were for, erases again whom an erasure since had erased, holds what a5s would send again,
and starts mailboxes afresh. Only the copies the copier marked count: a continuation someone
planted in the store stops nothing, and is never put back."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from a5s import cli, db
from a5s.config import Config
from a5s.core import anchor, ledger, restoring
from a5s.core.stores import FolderStore
from test_anchor import check, copy, write
from test_configuration import pod, rendered


def restored(url: str, through: int) -> None:
    """The database as a backup taken at entry `through` left it: the ledger's later entries
    gone, as the copies go on."""
    with psycopg.connect(url) as conn:
        conn.execute("alter table ledger disable trigger user")
        conn.execute("delete from ledger where seq > %s", (through,))
        conn.execute("alter table ledger enable trigger user")


def backed_up(database, tmp_path) -> FolderStore:
    """Entries 1 to 5 copied, as at the backup, and 6 to 9 copied since: then the restore."""
    store = FolderStore(tmp_path / "copies")
    write(database, 5)
    copy(database, store)
    write(database, 4)
    copy(database, store)
    restored(database, 5)
    return store


def put_back(database, store) -> dict:
    with db.transaction(db.as_role(database, "gateway")) as conn:  # as the core
        return restoring.restore(conn, store)


def test_the_copier_copies_nothing_on_a_restored_database_rather_than_fork_its_copies(
        database, tmp_path):
    store = backed_up(database, tmp_path)
    with pytest.raises(anchor.AnchorError, match="hold entries 6 to 9, which the database lacks"):
        copy(database, store)
    assert "entry 6 is missing from the ledger, though it was copied" in check(
        database, store).problems


def test_restore_puts_the_entries_back_and_the_copies_go_on(database, tmp_path):
    store = backed_up(database, tmp_path)
    done = put_back(database, store)
    assert (done["put_back"], done["through"]) == (4, 9)
    write(database, 2)
    [head] = copy(database, store)  # the restore's own entry, and the two since
    assert (head.first, head.seq) == (10, 12)
    result = check(database, store)
    assert result.ok and result.copied_through == 12, result.problems
    with db.transaction(database) as conn:
        [entry] = conn.execute("select entry from ledger where kind = 'restore'").fetchall()
    assert '"put_back":4' in entry["entry"]


def test_restore_holds_what_would_be_sent_again_and_starts_mailboxes_afresh(database, tmp_path):
    store = backed_up(database, tmp_path)
    with db.transaction(database) as conn:
        conn.execute("insert into outbox (person, channel, text, inbound_id, retry_at) values "
                     "('ben', 'teams', 'Your refund is on its way.', gen_random_uuid(), now()), "
                     "('ana', 'local', 'In the inbox already.', null, null)")
        conn.execute("insert into mail_state (mailbox, delta) values ('finance', 'since-backup')")
    done = put_back(database, store)
    assert (done["held"], done["mailboxes"]) == (1, 1)
    with db.transaction(database) as conn:
        held = conn.execute("select channel, problem, inbound_id, retry_at from outbox "
                            "where person = 'ben'").fetchone()
        assert conn.execute("select count(*) as n from mail_state").fetchone()["n"] == 0
    assert held is not None and (held["channel"], held["problem"]) == ("local", restoring.HELD)
    assert held["inbound_id"] is None and held["retry_at"] is None  # in their local inbox
    assert "Held 1 messages" in restoring.told(done)


def test_restore_takes_as_done_what_the_runs_since_the_backup_were_for(database, tmp_path):
    store, message, run = FolderStore(tmp_path / "copies"), str(uuid.uuid4()), str(uuid.uuid4())
    with db.transaction(database) as conn:  # as the backup has them: waiting still
        conn.execute("insert into inbound (id, channel, source_id, person, agent, text, reply_to) "
                     "values (%s, 'teams', 'm-1', 'ben', 'assistant', 'Refund order 7', '{}')",
                     (message,))
        event = conn.execute("insert into events (source, event_id, type) values ('itsm', 'e-1', "
                             "'ticket-opened') returning id::text as id").fetchone()["id"]
        conn.execute("insert into instances (id, definition, release, model) values "
                     "('assistant-finance', 'assistant', 'r1', 'm') on conflict do nothing")
    write(database, 2)
    copy(database, store)
    with db.transaction(database) as conn:  # the runs that opened since the backup
        for args in ({"trigger": "message", "inbound": message},
                     {"trigger": "event", "event": event},
                     {"trigger": "schedule", "schedule": "weekly",
                      "due": "2026-11-16T09:00:00+07:00"}):
            ledger.append(conn, {"kind": "run", "action": "open", "run": run,
                                 "instance": "assistant-finance", "acts_for": [],
                                 "decision": "allow", "reasons": [], "args": args})
    copy(database, store)
    restored(database, 2)
    done = put_back(database, store)
    assert (done["put_back"], done["answered"], done["worked_on"], done["fired"]) == (3, 1, 1, 1)
    with db.transaction(database) as conn:  # so no agent answers or acts on them again
        assert conn.execute("select answered_at from inbound where id = %s",
                            (message,)).fetchone()["answered_at"] is not None
        taken = conn.execute("select taken_at, run_id::text from events where id = %s",
                             (event,)).fetchone()
        fired = conn.execute("select due_at, outcome from schedule_fires where instance_id = "
                             "'assistant-finance' and schedule = 'weekly'").fetchone()
    assert taken["taken_at"] is not None and taken["run_id"] == run
    assert fired["due_at"] == datetime(2026, 11, 16, 2, tzinfo=UTC) and fired["outcome"] == "run"


def test_restore_erases_again_whom_an_erasure_since_the_backup_erased(database, tmp_path):
    store = FolderStore(tmp_path / "copies")
    with db.transaction(database) as conn:  # what the backup keeps of ben, and of ana
        conn.execute("insert into fresh_starts (person, agent, through) values "
                     "('ben', 'assistant', 1), ('ana', 'assistant', 1)")
    write(database, 2)
    copy(database, store)
    with db.transaction(database) as conn:  # ben's erasure since, and an archive's
        for person in ("ben", "former:2a7c"):
            ledger.append(conn, {"kind": "admin", "action": "erase", "run": None,
                                 "instance": None, "acts_for": [person], "decision": "record",
                                 "args": {"person": person, "by": "dpo", "erased": {},
                                          "archives_left": 0}})
    copy(database, store)
    restored(database, 2)
    done = put_back(database, store)
    assert (done["erased_again"], done["erase_again"]) == (1, ["former:2a7c"])
    with db.transaction(database) as conn:  # the backup brought ben back: erased again
        assert [r["person"] for r in conn.execute("select person from fresh_starts")] == ["ana"]
    assert "to erase former:2a7c" in restoring.told(done)  # by a name no archive has now


def planted(store, after: anchor.Head, entries: list[str]) -> None:
    """What someone with write access to the store could add past the ledger's end: a segment
    whose hashes chain on from the copies, as anyone can make, and its head, with no mark."""
    prev, lines = bytes.fromhex(after.hash), []
    for seq, entry in enumerate(entries, start=after.seq + 1):
        digest = hashlib.sha256(prev + entry.encode()).digest()
        lines.append(ledger.canonical({"seq": seq, "entry": entry, "prev_hash": prev.hex(),
                                       "hash": digest.hex()}))
        prev = digest
    body = ("\n".join(lines) + "\n").encode()
    last = after.seq + len(entries)
    segment = f"segments/{after.seq + 1:012d}-{last:012d}.jsonl"
    store.put(segment, body)
    store.put(f"heads/{last:012d}.json", ledger.canonical({
        "first": after.seq + 1, "seq": last, "hash": prev.hex(), "segment": segment,
        "segment_sha256": hashlib.sha256(body).hexdigest(), "prev": after.hash,
        "at": datetime.now(UTC).isoformat()}).encode())


def test_a_continuation_planted_in_the_store_stops_nothing_and_is_never_put_back(database,
                                                                                 tmp_path):
    store = FolderStore(tmp_path / "copies")
    write(database, 3)
    [head] = copy(database, store)
    at = datetime.now(UTC).isoformat()  # entries as the ledger writes them, but made up
    planted(store, head, [ledger.canonical({"kind": "proposal", "action": "made", "seq": 4,
                                            "decision": "allow", "at": at, "args": {}}),
                          ledger.canonical({"kind": "run", "action": "open", "seq": 5,
                                            "decision": "allow", "at": at, "args": {}})])
    assert copy(database, store) == []  # the copier goes on, with nothing new to copy
    with db.transaction(db.as_role(database, "gateway")) as conn:
        assert anchor.behind(conn, store) is None  # and the core starts
    assert put_back(database, store)["put_back"] == 0
    write(database, 1)
    [after] = copy(database, store)  # past the restore's own entry, and the planted head
    assert (after.first, after.seq) == (4, 5)


def test_the_core_wont_start_on_a_restored_database_where_it_reads_the_copies(database,
                                                                              tmp_path):
    store = backed_up(database, tmp_path)
    cfg = Config(database_url=db.as_role(database, "gateway"), gateway_url="http://127.0.0.1:1",
                 service_token="t" * 40, root=tmp_path, anchor_store=store.path.as_uri())
    with pytest.raises(RuntimeError, match="hold entries 6 to 9, which the database lacks"):
        cli._service(cfg, "gateway")


def test_a_restore_a_deployment_names_runs_once(database, tmp_path, capsys):
    store = backed_up(database, tmp_path)
    cfg = Config(database_url=db.as_role(database, "gateway"), gateway_url="http://127.0.0.1:1",
                 service_token="t" * 40, root=tmp_path, anchor_store=store.path.as_uri())
    cli._restore(cfg, "backup-2026-11-17")
    assert "Put back 4 entries" in capsys.readouterr().out
    cli._restore(cfg, "backup-2026-11-17")  # the chart's job, at the next upgrade
    assert "already" in capsys.readouterr().out
    with db.transaction(database) as conn:
        assert conn.execute("select count(*) as n from ledger where kind = 'restore'"
                            ).fetchone()["n"] == 1


def test_the_chart_restores_before_setup_once_a_backup_is_named():
    found = {(d["kind"], d["metadata"]["name"]): d
             for d in rendered("ci-values.yaml", sets=("restore.id=backup-2026-11-17",))}

    def weight(kind: str, name: str) -> int:
        return int(found[(kind, name)]["metadata"]["annotations"]["helm.sh/hook-weight"])

    job = found[("Job", "a5s-restore")]
    assert set(job["metadata"]["annotations"]["helm.sh/hook"].split(",")) == {
        "pre-install", "pre-upgrade"}  # before any part starts, in a new cluster too
    assert weight("ServiceAccount", "a5s-restore") < weight("Job", "a5s-restore") < weight(
        "Job", "a5s-setup")  # its own account first, then it, then setup
    spec = pod(job)
    [container] = spec["containers"]
    env = {e["name"]: e for e in container["env"]}
    assert container["args"] == ["restore", "--id", "backup-2026-11-17"]
    assert env["A5S_DATABASE_URL"]["valueFrom"]["secretKeyRef"]["key"] == "database-gateway-url"
    assert "A5S_ANCHOR_STORE" in env and spec["serviceAccountName"] == "a5s-restore"
    assert not [d for d in rendered("ci-values.yaml") if d["metadata"]["name"] == "a5s-restore"]
