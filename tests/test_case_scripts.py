"""A case step may say which script its answer is written in (a5s/cases.py's `writes_in`), such
as Thai to someone who wrote in Thai: most of the letters the agent wrote must be, leaving out
links and a5s's own notes, so a record's key or a name in Latin letters doesn't count against it.
The assistant's suite asks it of a question written in Thai (agents/assistant/tests/language.yaml),
live, at each release and each night."""

from pathlib import Path

import pytest

from a5s import cases

ROOT = Path(__file__).resolve().parents[1]
STEP = {"say": "สถานะของ Q-1002 เป็นอย่างไร", "writes_in": "thai"}


def test_an_answer_in_thai_passes_with_its_record_key_and_link():
    reply = ("คำถาม Q-1002 ตอนนี้รอฝ่ายการเงินตรวจสอบอยู่ และครบกำหนดวันที่ 6 พฤศจิกายน "
             "ดูได้ที่ https://sample.a5s.dev/records/Q-1002")
    assert cases.check(STEP, reply, [], allow_own=True) == []


def test_an_answer_in_english_to_someone_who_wrote_in_thai_fails():
    reply = "Q-1002 is waiting on finance, and it's due on 6 November."
    assert cases.check(STEP, reply, [], allow_own=True) == ["didn't answer in Thai script"]


def test_a5s_own_note_in_english_doesnt_count_against_it():
    reply = ("คำถาม Q-1002 ครบกำหนดวันที่ 2026-11-06 (a5s: the agent wrote 2026-11-06 itself, "
             "which nothing it read says, so check it before relying on it)")
    assert cases.written_in(reply, "thai")


def test_an_answer_of_no_letters_is_in_no_script():
    assert not cases.written_in("Q-1002: 2026-11-06", "thai")


def test_a_case_naming_a_script_a5s_doesnt_know_is_refused():
    text = "- name: answers in Klingon\n  steps:\n    - say: nuqneH\n      writes_in: klingon\n"
    with pytest.raises(cases.Unreadable, match="writes_in is a script a5s knows, such as thai"):
        cases.read(text, "tests/language.yaml")


def test_the_assistants_case_in_thai_reads_as_one_a5s_runs():
    path = ROOT / "agents" / "assistant" / "tests" / "language.yaml"
    [case] = cases.read(path.read_text(encoding="utf-8"), "tests/language.yaml")
    [step] = case["steps"]
    assert step["writes_in"] == "thai" and cases.written_in(step["say"], "thai")
