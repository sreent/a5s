"""The ledger's locked copies: a rewritten history shows, even with every hash recomputed."""

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import boto3
import psycopg
import pytest
from moto import mock_aws

from a5s import db
from a5s.core import anchor, ledger
from a5s.core.stores import AzureBlobStore, Exists, FolderStore, GcsStore, S3Store

DAY = timedelta(days=1)


def write(url: str, n: int) -> None:
    with db.transaction(url) as conn:
        for i in range(n):
            ledger.append(conn, {"kind": "test", "action": "note", "decision": "allow",
                                 "args": {"n": i}})


def copy(url: str, store) -> list[anchor.Head]:
    with db.transaction(db.as_role(url, "anchor")) as conn:  # the copier only reads the ledger
        return anchor.anchor(conn, store)


def check(url: str, store, **kwargs) -> anchor.AnchorCheck:
    with db.transaction(db.as_role(url, "anchor")) as conn:
        return anchor.check(conn, store, **kwargs)


def rewrite(url: str, seq: int, change) -> None:
    """What a database administrator could do: change an entry, and recompute every hash after it."""
    with psycopg.connect(url) as conn:
        conn.execute("alter table ledger disable trigger user")
        rows = conn.execute("select seq, entry, prev_hash from ledger where seq >= %s order by seq",
                            (seq,)).fetchall()
        prev = bytes(rows[0][2])
        for number, entry, _ in rows:
            entry = change(entry) if number == seq else entry
            digest = hashlib.sha256(prev + entry.encode()).digest()
            conn.execute("update ledger set entry = %s, prev_hash = %s, hash = %s where seq = %s",
                         (entry, prev, digest, number))
            prev = digest
        conn.execute("alter table ledger enable trigger user")


@pytest.fixture
def folder(tmp_path):
    return FolderStore(tmp_path / "copies")


def test_the_ledger_is_copied_and_matches_its_copies(database, folder):
    write(database, 5)
    [head] = copy(database, folder)
    assert (head.first, head.seq) == (1, 5)
    assert copy(database, folder) == []  # nothing new
    write(database, 3)
    [head] = copy(database, folder)
    assert (head.first, head.seq) == (6, 8)
    result = check(database, folder)
    assert result.ok and result.copied_through == 8, result.problems
    assert not result.locked  # a folder is for development only


def test_a_rewritten_history_shows_even_with_every_hash_recomputed(database, folder):
    write(database, 6)
    copy(database, folder)
    rewrite(database, 3, lambda entry: entry.replace('"allow"', '"deny"'))

    with db.transaction(database) as conn:
        assert ledger.verify(conn).ok  # the chain alone can't tell
    result = check(database, folder)
    assert not result.ok
    assert result.problems == ("entry 3 was changed after it was copied",)
    with pytest.raises(anchor.AnchorError, match="no longer matches its copy heads/000000000006"):
        copy(database, folder)  # and a5s won't copy the rewritten history


def test_entries_deleted_after_they_were_copied_show(database, folder):
    write(database, 4)
    copy(database, folder)
    with psycopg.connect(database) as conn:
        conn.execute("alter table ledger disable trigger user")
        conn.execute("delete from ledger where seq > 2")
        conn.execute("alter table ledger enable trigger user")
    assert check(database, folder).problems == (
        "entry 3 is missing from the ledger, though it was copied",)


def test_copying_that_stops_shows_but_a_quiet_ledger_is_fine(database, folder):
    write(database, 2)
    copy(database, folder)
    later = datetime.now(UTC) + timedelta(hours=3)
    assert check(database, folder, now=later).ok  # nothing waiting to be copied
    write(database, 1)
    [problem] = check(database, folder, now=later).problems
    assert problem.endswith("so copying has stopped")


def test_a_copy_that_stopped_half_way_finishes_and_nothing_is_overwritten(database, folder):
    write(database, 3)
    [head] = copy(database, folder)
    segment = folder.get(head.segment)
    with pytest.raises(Exists):
        folder.put(head.segment, b"something else")
    assert folder.get(head.segment) == segment

    write(database, 2)  # the next copy wrote its segment, then stopped before its head
    with db.transaction(database) as conn:
        rows = conn.execute("select seq, entry, prev_hash, hash from ledger where seq > 3 "
                            "order by seq").fetchall()
    body = "".join(ledger.canonical({"seq": r["seq"], "entry": r["entry"],
                                     "prev_hash": bytes(r["prev_hash"]).hex(),
                                     "hash": bytes(r["hash"]).hex()}) + "\n" for r in rows)
    folder.put("segments/000000000004-000000000005.jsonl", body.encode())
    [head] = copy(database, folder)
    assert (head.first, head.seq) == (4, 5)
    assert check(database, folder).ok


@pytest.fixture
def s3(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3")
        client.create_bucket(Bucket="assurance", ObjectLockEnabledForBucket=True)
        client.create_bucket(Bucket="unlocked")
        yield client


def test_s3_copies_are_locked_and_a_replaced_one_shows(database, s3):
    store = S3Store("assurance", "a5s/", DAY, s3)
    write(database, 4)
    [head] = copy(database, store)
    assert check(database, store).ok and check(database, store).locked

    name = "a5s/" + head.segment
    [version] = s3.list_object_versions(Bucket="assurance", Prefix=name)["Versions"]
    with pytest.raises(s3.exceptions.ClientError, match="AccessDenied"):
        s3.delete_object(Bucket="assurance", Key=name, VersionId=version["VersionId"])
    with pytest.raises(Exists):
        store.put(head.segment, b"forged")

    s3.put_object(Bucket="assurance", Key=name, Body=b"forged")  # a new version beside it
    assert store.get(head.segment).startswith(b'{"entry"')  # a5s reads the first version
    assert check(database, store).problems == (f"someone tried to replace or delete {head.segment}",)


def test_a_store_that_cant_lock_refuses_the_copy(database, s3):
    write(database, 1)
    with pytest.raises(s3.exceptions.ClientError, match="ObjectLockConfiguration"):
        copy(database, S3Store("unlocked", "", DAY, s3))


@pytest.mark.skipif(not os.environ.get("A5S_TEST_AZURITE"), reason="needs Azurite")
def test_azure_copies(database):
    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(os.environ["A5S_TEST_AZURITE"])
    container = service.create_container(f"a5s-{uuid.uuid4().hex[:12]}")
    store = AzureBlobStore(container, "a5s/", DAY)
    write(database, 3)
    [head] = copy(database, store)
    with pytest.raises(Exists):
        store.put(head.segment, b"forged")
    assert check(database, store).ok


@pytest.mark.skipif(not os.environ.get("A5S_TEST_GCS"), reason="needs a Cloud Storage emulator")
def test_google_cloud_copies(database, monkeypatch):
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", os.environ["A5S_TEST_GCS"])
    name = f"a5s-{uuid.uuid4().hex[:12]}"
    GcsStore.connect(name, "", DAY).bucket.client.create_bucket(name)
    store = GcsStore.connect(name, "a5s/", DAY)
    write(database, 3)
    [head] = copy(database, store)
    with pytest.raises(Exists):
        store.put(head.segment, b"forged")
    assert check(database, store).ok


def plant(store, key: str, **head) -> None:
    """What someone with write access to the store could add."""
    defaults = {"first": 1, "seq": 1, "hash": "00" * 32, "segment": "segments/none.jsonl",
                "segment_sha256": "00" * 32, "at": datetime.now(UTC).isoformat()}
    store.put(key, ledger.canonical({**defaults, **head}).encode())


def test_a_planted_head_neither_stops_the_copying_nor_hides_anything(database, folder):
    write(database, 3)
    [first] = copy(database, folder)
    plant(folder, "heads/999999999999.json", first=4, seq=999999999999, prev=first.hash)  # past the end
    plant(folder, "heads/000000000005.json", first=4, seq=5, prev=first.hash)  # where the next goes
    write(database, 2)
    [second] = copy(database, folder)
    assert (second.first, second.seq) == (4, 5)
    result = check(database, folder)
    assert result.copied_through == 5
    assert sorted(result.problems) == [
        "heads/000000000005.json doesn't continue the copies before it",
        "heads/999999999999.json doesn't continue the copies before it"]
    assert copy(database, folder) == []  # and the next copy carries on from entry 5


def test_a_copier_that_finds_a_rewritten_history_stops_loudly(database, folder, monkeypatch):
    from a5s import cli
    from a5s.config import Config

    def rewritten(conn, store):
        raise anchor.AnchorError("the ledger no longer matches its copy heads/000000000006.json")

    monkeypatch.setattr(anchor, "anchor", rewritten)
    cfg = Config(database_url=database, gateway_url="http://unused", service_token="",
                 root=folder, anchor_store=f"file://{folder}")
    with pytest.raises(SystemExit) as stopped:
        cli._anchor(cfg, every=3600)  # it doesn't wait an hour to try again
    assert stopped.value.code == 1
