"""Round 15, A12: a5s's own words in a chat, such as that the agent is suspended or its model
isn't answering, are in the language the reader reads, as its other words are, and so are why
the web chat won't take more of someone's files, and why they may not undo a change. In a group
chat, they're in the language everyone in it reads, else English. The conversation keeps them
as they were said."""

from __future__ import annotations

import pytest

from a5s import db
from a5s.core import groups, notices
from test_files import send
from test_languages import reads
from test_levels import asked, levelled
from test_undo import kept, page


def test_a_thai_reader_hears_that_the_assistant_is_suspended_in_thai(stack):
    stack.suspend(by="ana")
    assert stack.say("Is Q-1002 paid?", person="ben") == (
        "The assistant is suspended at the moment, so it can't help. Ana Ortiz suspended it and "
        "can resume it.")
    reads(stack, "ben", "th")
    assert stack.say("Q-1002 จ่ายแล้วหรือยังคะ", person="ben") == (
        "ขณะนี้ assistant ถูกระงับอยู่ จึงช่วยไม่ได้ Ana Ortiz เป็นผู้ระงับและเปิดให้กลับมาทำงานได้")


def test_and_that_its_model_isnt_answering_as_the_conversation_keeps_it(stack):
    reads(stack, "ben", "th")
    stack.model.failing = 1
    said = stack.say("สวัสดีค่ะ", person="ben")
    assert said == ("โมเดลที่ฉันใช้ไม่ตอบสนองในขณะนี้ จึงทำเรื่องนี้ไม่เสร็จ "
                    "ลองใหม่อีกครั้งในอีกสักครู่")
    with db.transaction(stack.admin) as conn:
        [noted] = conn.execute("select content from turns where person = 'ben' and role = 'notice'")
    assert noted["content"] == said  # so a later run knows what they heard


def test_and_that_its_budget_for_them_is_spent_today(stack):
    reads(stack, "ben", "th")
    stack.model.tokens = 900_000  # one long answer takes their day
    stack.model.reply("คำตอบยาวมาก")
    stack.say("สรุปทุกอย่างให้หน่อยค่ะ", person="ben")
    stack.model.tokens = 15
    assert stack.say("Q-1002 ครบกำหนดเมื่อไหร่คะ", person="ben") == (
        "assistant ใช้งบประมาณสำหรับคุณของวันนี้หมดแล้ว จึงช่วยเรื่องนี้ไม่ได้จนถึงพรุ่งนี้ "
        "หากรอไม่ได้ โปรดสอบถาม Ana Ortiz")


def test_the_web_chat_says_why_it_wont_take_more_files_in_thai(stack):
    reads(stack, "ben", "th")
    for n in range(3):
        assert send(stack, f"หน้า {n}", (f"page-{n}.txt", "text/plain", b"more"),
                    person="ben").status_code == 202
    refused = send(stack, "อีกหน้า", ("page-9.txt", "text/plain", b"more"), person="ben")
    assert refused.status_code == 429
    assert refused.json()["detail"] == ("a5s เก็บข้อความที่มีไฟล์ของคุณซึ่งยังรอคำตอบอยู่ 3 ข้อความ: "
                                        "ส่งเพิ่มได้เมื่อตอบข้อความเหล่านั้นแล้ว")


def test_the_undo_page_says_why_not_in_thai(stack, approving, provider):
    levelled(stack)
    asked(stack)
    change = kept(stack)["id"]
    with db.transaction(stack.admin) as conn:
        conn.execute("update changes_made set until = now() - interval '1 minute'")
    reads(stack, "ben", "th")
    late = page(approving, provider, change, "ben").json()
    assert not late["may"]
    assert late["why_not"] == "ยกเลิกที่นี่ไม่ได้อีกแล้ว: เลยเวลาที่ยกเลิกได้แล้ว"


def test_a_notice_puts_in_what_changes_in_the_readers_words():
    assert notices.said("th", groups.UNSERVED, {"who": ["Ana Ortiz", "Ben Okafor"],
                                                "add": notices.ADD}) == (
        "ฉันยังไม่ได้ทำงานให้ Ana Ortiz และ Ben Okafor จึงช่วยในแชตนี้ไม่ได้ "
        "ผู้อนุมัติเอเจนต์ที่นี่เพิ่มพวกเขาได้ หรือถามฉันในแชตที่ไม่มีพวกเขา หรือคุยกันแบบตัวต่อตัว")
    assert notices.said("en", notices.NOT_AT_WORK, {"agent": "assistant", "status": "proposed",
                                                    "who": notices.ANYONE}) == (
        "The assistant is waiting for approval, so it can't help. Ask whoever runs a5s.")
    assert notices.said("th", notices.NOT_AT_WORK, {"agent": "assistant", "status": "proposed",
                                                    "who": notices.ANYONE}) == (
        "assistant อยู่ในสถานะรอการอนุมัติ จึงช่วยไม่ได้ โปรดสอบถาม ผู้ดูแล a5s")
    old = "The assistant {is} as an older scheduler wrote it."  # none of a5s's: as it is
    assert notices.said("th", old, {"is": "x"}) == old
    with pytest.raises(ValueError, match="who"):
        notices.said("th", notices.UNFINISHED, {})


def test_the_core_says_a_notice_in_english_where_it_cant_say_it_whole(stack):
    """A notice comes in English too, as a core that says it in no other language takes it, so
    an older core, or one missing what it needs, still says it."""
    reads(stack, "ben", "th")
    english = "I couldn't finish that. Try again, or ask Ana Ortiz."
    with stack.client() as c:
        missing = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                           "text": english, "notice": notices.UNFINISHED})
        whole = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                         "text": english, "notice": notices.UNFINISHED,
                                         "given": {"who": "Ana Ortiz"}})
        unknown = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                           "text": "Words of a newer scheduler.",
                                           "notice": "Words of a {newer} scheduler."})
    assert missing.json() == {"sent": True, "text": english}
    assert whole.json() == {"sent": True, "text": "ฉันทำเรื่องนี้ไม่เสร็จ ลองใหม่อีกครั้ง หรือสอบถาม "
                                                  "Ana Ortiz"}
    assert unknown.json() == {"sent": True, "text": "Words of a newer scheduler."}
