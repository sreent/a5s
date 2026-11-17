"""What code masks of who someone is (core/masking.py), in what someone said to an agent and what
it answered, before people who aren't to learn whom it's about read it: a test case kept from a
run, or an answer its owners check."""

import time
from types import SimpleNamespace

from a5s import db
from a5s.core import masking

PEOPLE = {"ana": "Ana Ortiz", "lwei": "Li Wei", "som": "สมศักดิ์ ใจดี", "ben": "Ben Okafor"}


class Directory:
    record_pattern = r"\bQ-\d{4}\b"

    def person(self, who: str):
        return SimpleNamespace(name=PEOPLE[who]) if who in PEOPLE else None


def masked(text: str, people=("ana", "lwei", "som"), **kw) -> tuple[str, dict]:
    return masking.mask(text, Directory(), list(people), **kw)


def test_each_part_of_a_name_and_an_id_are_masked_however_theyre_written():
    said, counts = masked("ANA ORTIZ asked ana, and ortiz@ isn't an address. Banana stays.")
    assert said == "[someone] [someone] asked [someone], and [someone]@ isn't an address. Banana stays."
    assert counts == {"names": 4}


def test_a_short_name_is_masked_as_the_directory_writes_it_alone():
    said, _ = masked("Li Wei asked; li is two letters, as Li is.")
    assert said == "[someone] [someone] asked; li is two letters, as [someone] is."


def test_a_thai_name_is_found_inside_a_sentence_written_without_spaces():
    said, counts = masked("คุณสมศักดิ์บอกว่าใจดีจะโทรมา")  # Thai puts no space between words
    assert said == "คุณ[someone]บอกว่า[someone]จะโทรมา" and counts == {"names": 2}


def test_whom_it_doesnt_name_stays_and_so_do_amounts_and_dates():
    said, counts = masked("Ben Okafor owes £860.00, due 2026-11-06.")
    assert said == "Ben Okafor owes £860.00, due 2026-11-06." and counts == {}
    said, _ = masked("Ben Okafor owes £860.00.", people=("ben",))
    assert said == "[someone] [someone] owes £860.00."


def test_emails_links_long_numbers_and_record_keys_where_asked():
    text = ("Write to a.ortiz+bills@example.co.uk or see https://intranet.example/x?id=4, "
            "call +44 20 7946 0958 about Q-1001, Q-1002 and Q-1001 again.")
    said, counts = masked(text)
    assert said == ("Write to [an email] or see [a link] call [a number] about Q-1001, Q-1002 and "
                    "Q-1001 again.")
    said, counts = masked(text, records=True)
    assert said.endswith("about [record 1], [record 2] and [record 1] again.")
    assert counts == {"emails": 1, "links": 1, "numbers": 1, "records": 3}


def test_a_long_text_is_read_once_and_only_so_far():
    for text in ("a" * 1_000_000, "a." * 500_000, "x@" * 500_000, "1 " * 500_000):
        started = time.monotonic()
        said, _ = masked(text)
        assert time.monotonic() - started < 2 and len(said) <= masking.MOST + 50


def test_everyone_a5s_serves_and_who_runs_its_instances_are_known(stack):
    with db.transaction(stack.admin) as conn:
        known = masking.known(conn, stack.gateway.scenario)
    assert {"ana", "ben"} <= known  # whom the assistant serves, and its owner and deputy
