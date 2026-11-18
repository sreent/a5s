"""Round 15, B6: a Thai decider read what to know of a held change in English, unwarned. Now a5s
keeps each flag as one of its sentences with what changes in it, and says it in each reader's
language: on the decide page, in the message that asks a decider and on their card, and to each
grader of its sample. The English stays, for the record and the judge. The change's own words
and its records stay as their system gives them, since its deciders seal those words, and a
reader of another language is told so."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from a5s.core import counts, proposals, samples, words
from conftest import SEAL_KEY, accessible
from test_languages import reads
from test_proposals import asked, decide, held, invented, sweep
from test_samples import drawn


def review(url: str, provider, page: str, person: str) -> dict:
    return httpx.post(f"{url}/{page}/review", headers={
        "Authorization": f"Bearer {provider.id_token(person=person)}"}).json()


def test_a_thai_decider_reads_what_to_know_in_thai(stack, approving, provider):
    reads(stack, "ana", "th")
    call, day = invented()
    asked(stack, call, said="Please move Q-1002 out a week.")  # Ben named no date
    [p] = held(stack)
    assert p["flags"] == [  # the record, in English, as before
        f"{day} came from the assistant itself, not from the records or from Ben Okafor"]
    thai = f"{day} มาจาก assistant เอง ไม่ได้มาจากระเบียนหรือจาก Ben Okafor"
    [shown] = review(approving, provider, "decide", "ana")["proposals"]
    assert shown["flags"] == [thai]
    [asking] = [m for m in stack.inbox("ana") if m["text"].startswith("P-1 รอการตัดสินใจของคุณ")]
    assert f"สิ่งที่ควรรู้:\n- {thai}" in asking["text"]
    assert p["said"] in asking["text"]  # the words its deciders seal, as they are,
    assert words.say("th", proposals.SEALED) in asking["text"]  # and said to be so


def test_a_thai_grader_reads_what_its_deciders_were_told_in_thai(stack, approving, provider):
    call, day = invented()
    asked(stack, call, said="Please move Q-1002 out a week.")
    decide(approving, provider, [p["digest"] for p in held(stack)])
    sweep(stack)
    [sample] = drawn(stack)
    assert sample["flagged"] and samples.drawn_by_core((SEAL_KEY,), sample)
    reads(stack, "dana", "th")
    [shown] = review(approving, provider, "grade", "dana")["samples"]
    assert shown["flags"] == [f"{day} มาจาก assistant เอง ไม่ได้มาจากระเบียนหรือจาก Ben Okafor"]


def test_a_card_and_what_to_know_are_said_in_the_deciders_language():
    over = words.kept(counts.PERSON_LIMIT, most=3, action="change-due-date", person="ben",
                      made=3)
    event = proposals.after_kept({"kind": "event", "source": "billing", "type": "invoice.overdue"})
    flagged = [words.kept(proposals.OVER, over=over),
               words.kept(proposals.UNASKED_ABOUT, agent="assistant", after=event,
                          whom=["Ana Ortiz", "Ben Okafor"])]
    held_ = {"id": 7, "said": "Change a customer question's due date: Q-1002.",
             "flags": [words.said("en", f) for f in flagged], "flagged": flagged,
             "proposed_at": datetime(2026, 11, 3, tzinfo=UTC)}
    assert held_["flags"] == [
        ("it waits because it's past the scenario's limit of 3 change-due-date in 30 days for "
         "each person: ben has had 3 already"),
        ("nobody asked for it: the assistant asked for it after billing said invoice.overdue "
         "happened, about Ana Ortiz and Ben Okafor")]
    card = proposals.card(held_, "https://a5s.example/d", again=True, language="th")
    said = [b["text"] for b in card["body"]]
    assert said[0] == "ยังรอการตัดสินใจของคุณ: P-7"
    assert said[2] == words.say("th", proposals.SEALED)
    assert said[3] == ("สิ่งที่ควรรู้:\n"
                       "- รอเพราะเกินขีดจำกัดของสถานการณ์ที่ 3 change-due-date ใน 30 วันต่อคน: "
                       "ben ได้ไปแล้ว 3\n"
                       "- ไม่มีใครขอ: assistant ขอเองหลังจากที่ billing แจ้งว่าเกิด invoice.overdue "
                       "เกี่ยวกับ Ana Ortiz และ Ben Okafor")
    assert card["actions"][0]["title"] == "ตรวจสอบและตัดสินใจ"
    english = proposals.card(held_, "https://a5s.example/d", again=True)
    assert [b["text"] for b in english["body"]][:2] == [
        "Still waiting for your decision: P-7", held_["said"]]  # no word on its words
    assert proposals.asking(held_, "https://a5s.example/d", again=True, language="th").startswith(
        "ยังรอการตัดสินใจของคุณ: P-7 ตั้งแต่ 3 พ.ย.")


def test_flags_kept_before_are_said_as_they_were():
    assert words.flags({"flags": ["kept before, in English"], "flagged": None}, "th") == [
        "kept before, in English"]
    planted = words.kept("{value.__class__} and {x}", value="a")  # only names are put in
    assert words.said("en", planted) == "{value.__class__} and {x}"


def test_a_samples_seal_covers_what_its_graders_are_told_where_a5s_keeps_it():
    kept = {"id": 1, "scenario": "sample", "flags": ["English"], "flagged": [
        words.kept(proposals.READ_OUTSIDE, agent="assistant")]}
    before = {**kept, "flagged": None}  # drawn before a5s kept its words
    for row in (kept, before):
        assert samples.drawn_by_core((SEAL_KEY,), {**row, "drawn_seal": samples.draw_seal(
            (SEAL_KEY,), row)})
    changed = {**kept, "flagged": [words.kept(proposals.READ_OUTSIDE, agent="someone else")],
               "drawn_seal": samples.draw_seal((SEAL_KEY,), kept)}
    assert not samples.drawn_by_core((SEAL_KEY,), changed)


def test_on_the_decide_page_a_thai_decider_reads_what_to_know_and_why_the_rest_is_english(
        stack, approving, provider, browser):
    reads(stack, "ana", "th")
    call, day = invented()
    asked(stack, call, said="Please move Q-1002 out a week.")
    [p] = held(stack)
    page = browser.new_page()
    page.goto(f"{approving}/studio/decide?proposal={p['digest']}")
    page.wait_for_selector(".approval >> text=Q-1002", timeout=30000)
    assert page.locator(".approval .flags li").all_inner_texts() == [
        "ต้องตัดสินใจรายการนี้แยกต่างหาก ไม่รวมกับรายการอื่น",
        f"{day} มาจาก assistant เอง ไม่ได้มาจากระเบียนหรือจาก Ben Okafor"]
    assert page.inner_text(".approval h2").startswith("Change a customer question's due date")
    assert words.say("th", proposals.SEALED) in page.inner_text(".approval")
    accessible(page)
