import hashlib

import psycopg
import pytest

from a5s import db
from a5s.core import ledger


def write(url: str, *actions: str) -> None:
    with db.transaction(url) as conn:
        for action in actions:
            ledger.append(conn, {"kind": "test", "action": action, "decision": "record"})


def test_the_chain_verifies(database):
    write(database, "a", "b", "c")
    with db.transaction(database) as conn:
        result = ledger.verify(conn)
    assert result.ok and result.entries == 3


def test_the_database_refuses_to_change_an_entry(database):
    write(database, "a")
    with (pytest.raises(psycopg.errors.RaiseException, match="append-only"),
          db.transaction(database) as conn):
        conn.execute("update ledger set entry = entry where seq = 1")
    with (pytest.raises(psycopg.errors.RaiseException, match="append-only"),
          db.transaction(database) as conn):
        conn.execute("delete from ledger")


def test_a_rewritten_entry_shows_where_the_chain_breaks(database):
    write(database, "a", "b", "c")
    # Someone with full rights switches the guard off and rewrites history.
    with db.transaction(database) as conn:
        conn.execute("alter table ledger disable trigger ledger_append_only")
        conn.execute("""update ledger set entry = replace(entry, '"b"', '"x"') where seq = 2""")
    with db.transaction(database) as conn:
        result = ledger.verify(conn)
    assert not result.ok and result.broken_at == 2 and result.entries == 1


def test_text_is_kept_by_hash_and_length_only_however_short():
    masked = ledger.mask({"title": "Short", "body": "x" * 500, "key": "Q-1001", "count": 3},
                         plain=("key",))
    assert masked["title"] == {"sha256": hashlib.sha256(b"Short").hexdigest(), "chars": 5}
    assert masked["body"]["chars"] == 500 and "x" * 50 not in str(masked)
    assert (masked["key"], masked["count"]) == ("Q-1001", 3)  # a record's key, and numbers
