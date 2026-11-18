"""Round 15, E8: the copier copied the ledger every hour, so an entry written since its last
copy could be rewritten unseen, every hash after it recomputed, and the next copy locked the
forgery in; and nothing told auditors whether the trail checks out. Now the copier looks every
minute, by the database alone, copying what people decided within a minute and the rest within
15 minutes, and reads the copies only when it must; it checks the whole ledger, its chain and
every copy, when it starts and once a day; and the status, the operators' figures and the
auditors' page say what it found, the page marking each entry it shows that isn't copied yet,
or doesn't chain. An entry taken out of a copied ledger, or put in, with those after it
renumbered, shows as such, not as one changed."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from a5s import db
from a5s.core import anchor, ledger, status
from a5s.core.ledger import canonical
from a5s.core.stores import FolderStore
from conftest import accessible
from test_anchor import check, copy, folder, rewrite, write  # noqa: F401 - folder is the fixture
from test_audit_page import AUDITOR, reading
from test_metrics import collected, figures  # noqa: F401 - figures is the fixture
from test_r15_copies_seen import stood
from test_ui_pages import shot


class Counted(FolderStore):
    """A folder of copies that counts what's read of it."""

    def __init__(self, path):
        super().__init__(path)
        self.read = 0

    def get(self, key: str) -> bytes:
        self.read += 1
        return super().get(key)


def decided(url: str, n: int = 1) -> None:
    """What someone decided, as an administrator's entry records it."""
    with db.transaction(url) as conn:
        for i in range(n):
            ledger.append(conn, {"kind": "admin", "action": "decide", "decision": "record",
                                 "args": {"n": i}})


def acted(url: str, n: int) -> list[int]:
    """What agents did, as tool calls' entries record it."""
    with db.transaction(url) as conn:
        return [ledger.append(conn, {"kind": "tool", "action": "look_up", "decision": "allow",
                                     "args": {"n": i}}) for i in range(n)]


def ticked(url: str, copier: anchor.Copier, **kwargs) -> list[tuple[int, int]]:
    """The copier, looking once, as `a5s anchor --every` has it each minute, as its own role."""
    with db.transaction(db.as_role(url, "anchor")) as conn:
        return [(h.first, h.seq) for h in copier.tick(conn, **kwargs)]


def checked(url: str, copier: anchor.Copier, **kwargs) -> tuple[str, ...] | None:
    with db.transaction(db.as_role(url, "anchor")) as conn:
        return copier.checking(conn, **kwargs)


def crudely(url: str, seq: int) -> None:
    """An entry changed as a database administrator could, leaving its hash as it was."""
    with psycopg.connect(url) as conn:
        conn.execute("alter table ledger disable trigger user")
        conn.execute("update ledger set entry = replace(entry, '\"n\":1', '\"n\":7') "
                     "where seq = %s", (seq,))
        conn.execute("alter table ledger enable trigger user")


def renumbered(url: str, gone: int | None = None, put_in: int | None = None) -> None:
    """The ledger with an entry taken out, or one put in, and every entry after it renumbered,
    with every hash after it recomputed: what someone with the database's own powers could do."""
    with psycopg.connect(url) as conn:
        conn.execute("alter table ledger disable trigger user")
        rows = conn.execute("select seq, entry from ledger order by seq").fetchall()
        entries = [json.loads(e) for _, e in rows]
        if gone is not None:
            del entries[gone - 1]
        if put_in is not None:
            entries.insert(put_in - 1, {**entries[put_in - 1], "args": {"n": 99}})
        conn.execute("delete from ledger")
        prev = ledger.GENESIS
        for seq, entry in enumerate(entries, start=1):
            text = canonical({**entry, "seq": seq})
            digest = hashlib.sha256(prev + text.encode()).digest()
            conn.execute("insert into ledger (seq, entry, prev_hash, hash) values (%s, %s, %s, "
                         "%s)", (seq, text, prev, digest))
            prev = digest
        conn.execute("alter table ledger enable trigger user")


def test_what_people_decided_is_copied_within_a_minute_and_the_rest_within_15(database,
                                                                              folder):  # noqa: F811
    copier = anchor.Copier(folder)
    write(database, 2)
    assert ticked(database, copier) == [(1, 2)]  # it starts by copying everything new
    acted(database, 3)
    assert ticked(database, copier) == []  # what agents did waits, up to 15 minutes
    later = datetime.now(UTC) + timedelta(minutes=15)
    assert ticked(database, copier, now=later) == [(3, 5)]
    acted(database, 1)
    decided(database)  # what someone decided goes at once, with what waited before it
    assert ticked(database, copier) == [(6, 7)]
    assert check(database, folder).ok


def test_the_copier_reads_the_copies_only_when_it_must(database, tmp_path):
    store = Counted(tmp_path / "copies")
    copier = anchor.Copier(store)
    write(database, 2)
    ticked(database, copier)  # it reads the copies as it starts
    for _ in range(3):
        decided(database)
        before = store.read
        assert len(ticked(database, copier)) == 1 and store.read == before  # by the database
    other = anchor.Copier(store)  # another copier, as during an upgrade, copies meanwhile
    decided(database)
    assert ticked(database, other) == [(6, 6)]
    decided(database)
    before = store.read
    assert ticked(database, copier) == [(7, 7)]  # it reads them afresh, and goes on from there
    assert store.read > before and check(database, store).ok


def test_two_copiers_never_fork_the_copies(database, folder):  # noqa: F811
    first, second = anchor.Copier(folder), anchor.Copier(folder)
    write(database, 3)
    ticked(database, first)
    ticked(database, second)
    decided(database, 2)
    with pytest.raises(RuntimeError), db.transaction(db.as_role(database, "anchor")) as conn:
        first.copy(conn)  # it copies, then its transaction fails, so it records nothing
        raise RuntimeError("the database went away")
    assert ticked(database, second) == [(4, 5)]  # the second copies the same, as the first did
    assert check(database, folder).ok
    assert sorted(folder.keys("heads/")) == ["heads/000000000003.json", "heads/000000000005.json"]


def test_a_rewrite_of_what_was_copied_stops_the_copier_at_its_next_look(database,
                                                                         folder):  # noqa: F811
    copier = anchor.Copier(folder)
    write(database, 4)
    ticked(database, copier)

    rewrite(database, 2, lambda entry: entry.replace('"n":1', '"n":7'))  # every hash after it
    with pytest.raises(anchor.AnchorError, match="no longer matches its copy"):
        ticked(database, copier)  # nothing new to copy, but it looks all the same


def test_an_entry_taken_out_shows_as_taken_out(database, folder):  # noqa: F811
    write(database, 6)
    copy(database, folder)
    renumbered(database, gone=3)
    assert check(database, folder).problems == (
        "entry 3 was taken out after it was copied, and those after it renumbered",)


def test_an_entry_put_in_shows_as_put_in(database, folder):  # noqa: F811
    write(database, 6)
    copy(database, folder)
    renumbered(database, put_in=3)
    assert check(database, folder).problems == (
        "an entry was put in at entry 3 after it was copied, and those after renumbered",)


def test_the_copier_checks_the_whole_ledger_as_it_starts_and_once_a_day(stack, tmp_path,
                                                                       figures):  # noqa: F811
    copier = anchor.Copier(FolderStore(tmp_path / "copies"))
    [seq, _] = acted(stack.admin, 2)
    ticked(stack.admin, copier)
    assert checked(stack.admin, copier) == ()  # as it starts: nothing wrong
    assert checked(stack.admin, copier) is None  # and not again until tomorrow
    full = stood(stack)["copies"]["checked"]
    assert (full["problems"], full["through"]) == ([], stood(stack)["copies"]["through"])
    assert "the whole ledger checked 0 hours ago: it checks out" in status.told(stood(stack))
    assert collected(figures)["a5s.ledger.check.problems"] == [(0.0, {})]
    crudely(stack.admin, seq + 1)  # its hash left as it was, which the copier's look can't see
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    assert checked(stack.admin, copier, now=tomorrow) == (
        f"the ledger's chain breaks at entry {seq + 1}",
        f"entry {seq + 1} was changed after it was copied")
    assert (f"checked 0 hours ago: the ledger's chain breaks at entry {seq + 1}; entry "
            f"{seq + 1} was changed after it was copied") in status.told(stood(stack))


def test_auditors_are_told_whether_the_trail_checks_out(stack, approving, provider, tmp_path):
    api = reading(approving, provider)
    assert api("/audit/api").json()["trail"] is None  # no copier keeps copies here, yet
    copier = anchor.Copier(FolderStore(tmp_path / "copies"))
    copied = acted(stack.admin, 3)
    ticked(stack.admin, copier, now=datetime.now(UTC) + timedelta(minutes=15))
    checked(stack.admin, copier)
    trail = api("/audit/api").json()["trail"]
    assert (trail["checks_out"], trail["problems"], trail["failing"]) == (True, [], False)
    assert trail["copied_through"] >= copied[-1] and trail["checked_minutes_ago"] == 0
    assert (trail["stale"], trail["late"]) == (False, False)
    newer = acted(stack.admin, 2)
    page = api("/audit/api/entries", kind="tool").json()
    assert page["broken"] == [] and [e["seq"] for e in page["entries"]] == copied + newer
    assert page["copied_through"] == trail["copied_through"] < newer[0]  # not copied yet
    crudely(stack.admin, copied[1])
    assert api("/audit/api/entries", kind="tool").json()["broken"] == [copied[1]]  # at once
    checked(stack.admin, copier, now=datetime.now(UTC) + timedelta(days=1))
    trail = api("/audit/api").json()["trail"]
    assert not trail["checks_out"] and trail["problems"] == [
        f"the ledger's chain breaks at entry {copied[1]}",
        f"entry {copied[1]} was changed after it was copied"]


def test_a_check_or_copies_long_overdue_never_show_as_checking_out(stack, approving, provider,
                                                                  tmp_path):
    """As when the copier stopped running: its last check, however good, vouches for nothing
    written since, and the page says what's overdue."""
    copier = anchor.Copier(FolderStore(tmp_path / "copies"))
    acted(stack.admin, 1)
    ticked(stack.admin, copier)
    checked(stack.admin, copier)
    with psycopg.connect(stack.admin) as conn:
        conn.execute("update copier set checked_at = now() - interval '3 days', "
                     "copied_at = now() - interval '3 days'")
    acted(stack.admin, 1)
    trail = reading(approving, provider)("/audit/api").json()["trail"]
    assert (trail["checks_out"], trail["stale"], trail["late"], trail["problems"]) == (
        False, True, True, [])
    assert trail["checked_minutes_ago"] >= 3 * 24 * 60


def test_an_auditor_reads_whether_the_trail_checks_out_in_the_browser(stack, approving, provider,
                                                                      browser, tmp_path):
    copier = anchor.Copier(FolderStore(tmp_path / "copies"))
    acted(stack.admin, 2)
    ticked(stack.admin, copier, now=datetime.now(UTC) + timedelta(minutes=15))
    checked(stack.admin, copier)
    acted(stack.admin, 1)  # written since: not copied yet
    provider.person = AUDITOR
    page = browser.new_page()
    page.goto(f"{approving}/studio/audit")
    page.wait_for_selector("#trail", timeout=30000)
    trail = page.inner_text("#trail")
    assert "It checks out" in trail and "rewrite them unseen" in trail
    page.select_option("#kind", "tool")
    page.click("#search")
    page.wait_for_selector("#entries li", timeout=30000)
    marked = page.locator("#entries li").filter(has=page.locator("[data-uncopied]"))
    assert page.locator("#entries li").count() == 3 and marked.count() == 1
    accessible(page)
    shot(page, "audit-trail")
