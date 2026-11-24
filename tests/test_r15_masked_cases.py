"""Round 15, the author's finding (C6): a test case kept from a real run kept bank account
numbers, dates of birth, national ids and addresses, though it goes where everyone who reads the
agent's repository reads it. Now code masks those too, in what's kept from a run: dates of birth,
by what's said before them or by a year at least fifteen back, in English, Thai and the Buddhist
era; ids of letters and digits; numbers of six digits or more; and street addresses and
postcodes. The dates people work by, such as an invoice's due date, stay, as do amounts; and the
masking graders and owners read is as it was."""

from __future__ import annotations

from a5s import db
from a5s.core import masking, run_cases


class Directory:
    """A scenario as masking reads it: its records' keys, and nobody it knows by name."""

    record_pattern = r"\bQ-\d{4}\b"

    def person(self, who: str):
        return None


def strictly(text: str) -> str:
    return masking.mask(text, Directory(), [], records={"Q-1001": 1}, strict=True)[0]


def test_dates_of_birth_ids_numbers_and_addresses_are_masked_in_a_kept_case():
    assert strictly("Account 123-4-56789-0, sort code 12-34-56, DOB 12/03/1985") == (
        "Account [a number], sort code [a number], [a date of birth]")
    assert strictly("Born on 12 March 1985. Passport AA1234567, id 1-2345-67890-12-3") == (
        "[a date of birth]. Passport [an id], id [a number]")
    assert strictly("Her father's was 4/7/1952; the child's birthday is 2019-08-30") == (
        "Her father's was [a date]; the child's [a date of birth]")  # by the year, or what's said
    assert strictly("IBAN GB82 WEST 1234 5698 7654 32, NI QQ 12 34 56 C") == (
        "IBAN [an id], NI [an id]")
    assert strictly("I live at 221B Baker Street, London NW1 6XE") == (
        "I live at [an address], London [an address]")


def test_thai_addresses_and_dates_of_birth_are_masked_too():
    said = strictly("บ้านเลขที่ 99/12 หมู่ 3 ถนนสุขุมวิท แขวงคลองเตย กรุงเทพฯ 10110")
    assert said == " ".join(["[an address]"] * 5)
    assert strictly("ต.บางพลี อ.บางพลี จ.สมุทรปราการ 10540") == " ".join(["[an address]"] * 3)
    assert strictly("วันเกิด 12 มีนาคม 2528, เกิดวันที่ 5 ม.ค. 2530") == (
        "[a date of birth], [a date of birth]")


def test_the_dates_people_work_by_amounts_and_thai_abbreviations_stay():
    said = ("Invoice Q-1001: £860.00, due 2026-11-06, paid 12/03/26, ราคา 15000 บาท ภายใน ต.ค. "
            "นี้ จ. 2 พ.ย.")
    assert strictly(said) == said.replace("Q-1001", "[record 1]")
    assert strictly("Write to ana19851@example.com about 1985-03-12") == (
        "Write to [an email] about [a date]")


def test_what_graders_and_owners_read_is_masked_as_it_was():
    said = "DOB 12/03/1985, passport AA1234567, 221B Baker Street"
    assert masking.mask(said, Directory(), [])[0] == said  # they judge by these


def test_a_case_kept_from_a_run_masks_them(stack):
    text = "Ana's date of birth is 1985-03-12 and she lives at 221B Baker Street"
    with db.transaction(stack.admin) as conn:
        masked_by = run_cases.mask(conn, stack.gateway.scenario, {"acts_for": ["ana"]}, text)
    said, masked = masked_by(text)
    assert said == "[someone]'s [a date of birth] and she lives at [an address]"
    assert masked == {"names": 1, "births": 1, "addresses": 1}


def test_more_ways_of_writing_a_date_of_birth_are_masked():
    """Round 16, C10: these each came back unmasked."""
    assert strictly("I was born on the 12th of March 1985.") == "I was [a date of birth]."
    assert strictly("born 12th of March, 1985") == "[a date of birth]"
    assert strictly("born on 12-Mar-1985") == "[a date of birth]"
    assert strictly("เกิดวันที่ 12 เดือนมีนาคม พ.ศ. 2528") == "[a date of birth]"
    assert strictly("due on the 12th of March 2026") == "due on the 12th of March 2026"  # stays
