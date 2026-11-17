"""What became of a held change, and a5s's own words in someone's digest, in the language they
read (round 14's deferrals): the change itself in its own words, each name and figure as the
records have it, and the records keeping English."""

from datetime import UTC, datetime

from a5s import db
from a5s.contract import Person
from a5s.core import digests, obligations, reminders, undoing
from test_digests import MONDAY
from test_languages import reads
from test_proposals import asked, decide, held, sweep


def test_what_became_of_a_held_change_reads_in_thai(stack, approving, provider):
    reads(stack, "ben", "th")  # Ben asked for it; Ana decides it
    reads(stack, "ana", "th")
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    assert sweep(stack)["made"] == 1
    told = [m["text"] for m in stack.inbox("ben")]
    assert any(t.startswith("Ana Ortiz อนุมัติ P-1 แล้ว และ a5s ดำเนินการแล้ว: Change a customer "
                            "question's due date: Q-1002") for t in told), told
    with db.transaction(stack.admin) as conn:
        [kept] = conn.execute("select outcome from proposals").fetchall()
        mine = [r["text"] for r in conn.execute(
            "select text from digest_items where person = 'ana'")]
    assert kept["outcome"].startswith("Ana Ortiz approved P-1, and a5s has made it")  # the record
    assert any(t.startswith("ผลของ P-1 ที่คุณตัดสิน: Ana Ortiz อนุมัติ P-1 แล้ว") for t in mine), mine


def test_a_refused_decision_is_told_in_thai(stack, approving, provider):
    reads(stack, "ana", "th")
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    with db.transaction(stack.admin) as conn:  # a sign-in that doesn't check out
        conn.execute("update proposal_decisions set proof = 'not.a.sign-in'")
    sweep(stack)
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute(
            "select text from digest_items where person = 'ana' and agent is null")]
    assert any(t.startswith("การตัดสินใจของคุณเรื่อง P-1 ไม่นับ: ") and
               t.endswith("หากยังรอคุณอยู่ โปรดตัดสินใจอีกครั้งที่หน้าของ a5s โดยลงชื่อเข้าใช้ใหม่")
               for t in told), told


def test_a_digest_is_framed_in_the_language_its_reader_reads(stack, monkeypatch):
    reads(stack, "ana", "th")
    stack.with_watcher()
    records = stack.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.model.reply("Ana, you have Q-1001, waiting on the customer.")
    stack.model.reply("Ben, you have Q-1002, waiting on finance.")
    assert stack.scheduler().work_due() == 4
    [ana] = stack.inbox("ana")
    assert ana["text"] == ("สรุปวันของคุณจาก a5s จ. 2 พ.ย.\n\n"
                           "จาก assistant:\nAna, Q-1001 is due on Wednesday.\n\n"
                           "จาก watcher:\nAna, you have Q-1001, waiting on the customer.")
    [ben] = stack.inbox("ben")  # Ben reads English, still
    assert ben["text"].startswith("Your day from a5s, Mon 2 Nov.\n\nFrom the assistant:")


def test_a5s_s_own_reminders_and_chases_read_in_thai():
    ana = Person(id="ana", name="Ana Ortiz", team="finance", timezone="Asia/Bangkok")
    at = datetime(2026, 11, 2, 2, 30, tzinfo=UTC)  # Monday, 09:30 in Bangkok
    assert obligations.day(ana, at, "th") == "จ. 2 พ.ย." and obligations.day(ana, at) == "Mon 2 Nov"
    reminded = reminders.notice({"confirmed_at": at, "agent": "assistant", "about": "call Q-1001's customer"},
                                ana, "ถูกระงับ", "th")
    assert reminded == ("เมื่อ จ. 2 พ.ย. คุณขอให้ assistant เตือนคุณในตอนนี้: call Q-1001's customer "
                        "ขณะนี้ assistant ถูกระงับ a5s จึงเตือนคุณเอง")
    row = {"record": "Q-1001", "title": "Invoice query", "due_at": at, "link": None, "agent": "assistant"}
    chased = obligations.instead(row, ana, "it has used its budget for today", "th")
    assert chased == ("Q-1001 Invoice query ครบกำหนดภายในเวลา 09:30 น. วันที่ จ. 2 พ.ย. และยังเปิดอยู่ "
                      "assistant เขียนถึงคุณเรื่องนี้ไม่ได้ เพราะใช้งบประมาณของวันนี้หมดแล้ว a5s จึงแจ้งคุณเอง")
    assert obligations.instead(row, ana, "it has used its budget for today").startswith(
        "Q-1001, Invoice query, is due by 09:30 on Mon 2 Nov and is still open.")
    offer = undoing.offered(at, "https://a5s.example", 7, "th", "Asia/Bangkok")
    assert offer.startswith("ยกเลิกการเปลี่ยนแปลงนี้ได้จนถึง 2 พ.ย. 2569 เวลา 09:30 น.")
    assert undoing.offered(at, "https://a5s.example", 7).startswith(
        "It can be undone until 02 Nov 2026, 02:30 UTC, on its page: ")
    framed = digests.compose(ana, [{"agent": None, "text": "x"}], at, "assistant", "th")
    assert framed == "สรุปวันของคุณจาก assistant จ. 2 พ.ย.\n\nจาก a5s:\nx"
