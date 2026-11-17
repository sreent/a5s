"""a5s's own words in the language someone reads (core/languages.py): English, as a5s writes them,
or Thai, for those this catalogue has, the words people read most: what waits on them in the
studio and why, the roles they hold and what each lets them do, and a5s's notes to them in chat.

An English sentence is its own key, with {name}s for what changes, so the code that writes it
stays as readable as it was (`say`). Sentences other parts of a5s write whole, such as why a
version of the settings waits on someone, are matched as they come, each name and figure kept
(`translated`). Anything the catalogue hasn't stays in English. tests/test_languages.py holds
each Thai to its English's {name}s.
"""

from __future__ import annotations

import re

from a5s.core.languages import ENGLISH

THAI = "th"

TH: dict[str, str] = {
    # What waits on someone, on their home (core/home.py)
    # What a5s says of values the agent wrote itself, beside its answer (core/provenance.py)
    "(a5s: {which} came from the {agent} itself, not from the records or from you, so check "
    "it before you rely on it.)":
        "(a5s: {which} มาจาก {agent} เอง ไม่ได้มาจากระเบียนหรือจากคุณ โปรดตรวจสอบก่อนนำไปใช้)",
    "(a5s: {which} came from the {agent} itself, not from the records or from you, so check "
    "them before you rely on them.)":
        "(a5s: {which} มาจาก {agent} เอง ไม่ได้มาจากระเบียนหรือจากคุณ โปรดตรวจสอบก่อนนำไปใช้)",
    "{first} and {last}": "{first} และ {last}",
    "Version {serial} of the settings waits for your approval":
        "การตั้งค่าเวอร์ชัน {serial} รอการอนุมัติจากคุณ",
    "{names} approved version {serial} of the settings alone, since it only narrows what agents "
    "may do in {parts}: {said}":
        "{names} อนุมัติการตั้งค่าเวอร์ชัน {serial} เพียงลำพัง เพราะเวอร์ชันนี้เพียงจำกัดสิ่งที่เอเจนต์ทำได้ใน "
        "{parts}: {said}",
    "{n} change an agent asked for waits for your decision":
        "การเปลี่ยนแปลงที่เอเจนต์ขอ {n} รายการรอการตัดสินใจจากคุณ",
    "{n} changes an agent asked for wait for your decision":
        "การเปลี่ยนแปลงที่เอเจนต์ขอ {n} รายการรอการตัดสินใจจากคุณ",
    "{n} sample of agents' work waits for your grade": "ตัวอย่างงานของเอเจนต์ {n} รายการรอให้คุณให้คะแนน",
    "{n} samples of agents' work wait for your grade": "ตัวอย่างงานของเอเจนต์ {n} รายการรอให้คุณให้คะแนน",
    "{n} or more samples of agents' work wait for your grade":
        "ตัวอย่างงานของเอเจนต์ {n} รายการขึ้นไปรอให้คุณให้คะแนน",
    "Release {version} of a5s waits for your signature, as {who}":
        "รีลีส {version} ของ a5s รอให้คุณลงนามในฐานะ {who}",
    "{person} asks for the {agent}": "{person} ขอใช้ {agent}",
    "{n} of the {agent}'s answers someone said was wrong wait for you to check":
        "คำตอบของ {agent} {n} รายการที่มีผู้บอกว่าไม่ถูกต้องรอให้คุณตรวจสอบ",
    "{n} of the {agent}'s answers people said were wrong wait for you to check":
        "คำตอบของ {agent} {n} รายการที่มีผู้บอกว่าไม่ถูกต้องรอให้คุณตรวจสอบ",
    "{n} of your tasks waits for you, blocked or asked for": "งานของคุณ {n} งานรอคุณอยู่ เพราะติดขัดหรือมีคำถาม",
    "{n} of your tasks wait for you, blocked or asked for": "งานของคุณ {n} งานรอคุณอยู่ เพราะติดขัดหรือมีคำถาม",
    "you own it": "คุณเป็นเจ้าของ",
    "A new version's answer waits for you to compare with the one sent":
        "คำตอบของเวอร์ชันใหม่รอให้คุณเทียบกับคำตอบที่ส่งไปแล้ว",
    "{n} of new versions' answers wait for you to compare with those sent":
        "คำตอบของเวอร์ชันใหม่ {n} รายการรอให้คุณเทียบกับคำตอบที่ส่งไปแล้ว",
    "you grade agents' work": "คุณให้คะแนนงานของเอเจนต์",
    "{person}'s conversation with the {agent} was handed to the {team} team, and waits for an answer":
        "บทสนทนาของ {person} กับ {agent} ถูกส่งต่อให้ทีม {team} และรอคำตอบ",
    "The {agent} made a change for you, which you can undo until {until}: {said}":
        "{agent} เปลี่ยนแปลงให้คุณ ซึ่งคุณยกเลิกได้จนถึง {until}: {said}",
    # On an instance's page (core/home.py, of_instance)
    "{changes} for your decision": "{changes} รอการตัดสินใจจากคุณ",
    "{changes} for someone else's decision": "{changes} รอการตัดสินใจจากผู้อื่น",
    "{n} change": "การเปลี่ยนแปลง {n} รายการ",
    "{n} changes": "การเปลี่ยนแปลง {n} รายการ",
    # Spending (core/spending.py)
    "{whose} has spent {amount} this month, past its budget of {budget}":
        "{whose} ใช้ไปแล้ว {amount} ในเดือนนี้ เกินงบประมาณ {budget}",
    "{whose} is on course to spend {amount} this month, past its budget of {budget}":
        "{whose} มีแนวโน้มจะใช้ {amount} ในเดือนนี้ เกินงบประมาณ {budget}",
    "you own {what}": "คุณเป็นเจ้าของ {what}",
    "{whose} ran {n} times this month on a model whose prices aren't known, which count for "
    "nothing against its budget":
        "{whose} ทำงาน {n} ครั้งในเดือนนี้บนโมเดลที่ไม่ทราบราคา ซึ่งไม่ถูกนับรวมในงบประมาณ",
    "Budgets are in {theirs}, and models.yaml prices models in {prices}, so a5s compares neither":
        "งบประมาณเป็นสกุลเงิน {theirs} แต่ models.yaml กำหนดราคาโมเดลเป็น {prices} "
        "a5s จึงไม่เปรียบเทียบทั้งสองอย่าง",
    "no currency it names": "สกุลเงินที่ไม่ได้ระบุ",
    "you own a budget": "คุณเป็นเจ้าของงบประมาณ",
    # The roles someone holds, and what each lets them do (core/home.py, core/administration.py)
    "Owner of {scope}": "เจ้าของ {scope}",
    "Delegate in {scope}": "ผู้รับมอบหมายใน {scope}",
    "Owner of the {scope}": "เจ้าของ {scope}",
    "Author of the {scope}": "ผู้เขียน {scope}",
    "Viewer of the {scope}": "ผู้ดู {scope}",
    "Instance approver": "ผู้อนุมัติอินสแตนซ์",
    "Release approver": "ผู้อนุมัติรีลีส",
    "Assurance": "ผู้ตรวจรับรอง",
    "Auditor": "ผู้ตรวจสอบ",
    "Data protection officer": "เจ้าหน้าที่คุ้มครองข้อมูล",
    "Grader": "ผู้ให้คะแนน",
    "Engineer": "วิศวกร",
    "The team that runs a5s": "ทีมที่ดูแล a5s",
    "the directory": "ไดเรกทอรี",
    "what the scenario gives it": "สิ่งที่ซีนาริโอกำหนดให้",
    "approve the instances that work in {scope}, and how far each may act there; decide the "
    "changes agents ask for there; watch those instances' runs; and approve what agents' models "
    "may cost there a month, and see what they do":
        "อนุมัติอินสแตนซ์ที่ทำงานใน {scope} และขอบเขตที่แต่ละตัวทำได้ที่นั่น ตัดสินใจเรื่องการเปลี่ยนแปลงที่เอเจนต์ขอที่นั่น "
        "ติดตามการทำงานของอินสแตนซ์เหล่านั้น และอนุมัติค่าใช้จ่ายโมเดลรายเดือนของเอเจนต์ที่นั่น พร้อมดูว่าใช้ไปเท่าใด",
    "decide the changes agents ask for in {scope}, beside its owner":
        "ตัดสินใจเรื่องการเปลี่ยนแปลงที่เอเจนต์ขอใน {scope} ร่วมกับเจ้าของ",
    "own the {scope}: its definition and releases, drafts of it, and its instances' runs; start "
    "new agents; suspend it; give a group its authors' or viewers' role; and approve what its "
    "models may cost a month, and see what they do":
        "เป็นเจ้าของ {scope}: นิยามและรีลีส ฉบับร่าง และการทำงานของอินสแตนซ์ เริ่มสร้างเอเจนต์ใหม่ ระงับการทำงาน "
        "ให้บทบาทผู้เขียนหรือผู้ดูแก่กลุ่ม และอนุมัติค่าใช้จ่ายโมเดลรายเดือน พร้อมดูว่าใช้ไปเท่าใด",
    "draft changes to the {scope}, try them in the sandbox, and publish them for its owners to sign":
        "ร่างการเปลี่ยนแปลงของ {scope} ทดลองในแซนด์บ็อกซ์ และเผยแพร่ให้เจ้าของลงนาม",
    "see how the {scope} is built, read only: its instructions and skills":
        "ดูว่า {scope} สร้างขึ้นอย่างไร แบบอ่านอย่างเดียว: คำสั่งและทักษะ",
    "start new agents, and draft them": "เริ่มสร้างเอเจนต์ใหม่ และร่างเอเจนต์",
    "approve the instances that work in no part, and set their levels":
        "อนุมัติอินสแตนซ์ที่ไม่ได้ทำงานในส่วนงานใด และกำหนดระดับของอินสแตนซ์เหล่านั้น",
    "approve releases, from outside the team that runs a5s": "อนุมัติรีลีส ในฐานะผู้อยู่นอกทีมที่ดูแล a5s",
    "grade agents' work, never your own team's": "ให้คะแนนงานของเอเจนต์ ยกเว้นงานของทีมคุณเอง",
    "read the ledger: find what was done and decided, and export it":
        "อ่านเลดเจอร์: ค้นหาสิ่งที่ทำและตัดสินใจไปแล้ว และส่งออก",
    "hold the ledger's locked copies, test releases, and read the ledger; where the directory "
    "names you, give a group the auditor's role":
        "เก็บสำเนาที่ล็อกไว้ของเลดเจอร์ ทดสอบรีลีส และอ่านเลดเจอร์ หากไดเรกทอรีระบุชื่อคุณ ให้บทบาทผู้ตรวจสอบแก่กลุ่มได้",
    "export or erase what a5s keeps about one person, one request at a time; where the directory "
    "names you, approve the settings' choices for people's data: how long a5s keeps it, and whom "
    "it names; and give a group your role":
        "ส่งออกหรือลบสิ่งที่ a5s เก็บไว้เกี่ยวกับบุคคล ครั้งละหนึ่งคำขอ หากไดเรกทอรีระบุชื่อคุณ อนุมัติตัวเลือกในการตั้งค่าเกี่ยวกับ"
        "ข้อมูลบุคคล ได้แก่ a5s เก็บไว้นานเท่าใด และระบุชื่อใครบ้าง และให้บทบาทของคุณแก่กลุ่มได้",
    "run it, and make it safer alone: suspend an instance, lower a cap or withdraw a release, "
    "never loosen it; sign its releases as an engineer":
        "ดูแลระบบ และทำให้ปลอดภัยขึ้นได้เองลำพัง: ระงับอินสแตนซ์ ลดเพดาน หรือถอนรีลีส แต่ไม่ผ่อนคลาย "
        "และลงนามรีลีสในฐานะวิศวกร",
    # a5s's notes in chat (core/feedback.py)
    "Noted: its owners will see that answer, and the run behind it, to check it, and nothing "
    "more of what you said.":
        "รับทราบแล้ว เจ้าของเอเจนต์จะเห็นคำตอบนั้นและการทำงานเบื้องหลังเพื่อตรวจสอบ โดยไม่เห็นสิ่งอื่นที่คุณพูด",
}

# Sentences other parts of a5s write whole, by pattern: each group a name or a figure, kept as
# it is, in its place in the Thai
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple((re.compile(p), th) for p, th in (
    (r"the owner of (\S+) hasn't approved it", "เจ้าของ {0} ยังไม่ได้อนุมัติ"),
    (r"the owner of the (\S+) hasn't approved its budget", "เจ้าของ {0} ยังไม่ได้อนุมัติงบประมาณ"),
    (r"no instance-approver has approved it, for the instances in no part",
     "ยังไม่มีผู้อนุมัติอินสแตนซ์อนุมัติ สำหรับอินสแตนซ์ที่ไม่อยู่ในส่วนงานใด"),
    (r"no instance-approver has approved its classes of data",
     "ยังไม่มีผู้อนุมัติอินสแตนซ์อนุมัติประเภทของข้อมูล"),
    (r"the (\S+) named in the directory hasn't approved giving (.+) the (\S+) role",
     "{0} ที่ระบุในไดเรกทอรียังไม่ได้อนุมัติการให้บทบาท {2} แก่ {1}"),
    ((r"the data-protection-officer named in the directory hasn't approved its choices for "
      r"people's data"), "เจ้าหน้าที่คุ้มครองข้อมูลที่ระบุในไดเรกทอรียังไม่ได้อนุมัติตัวเลือกเกี่ยวกับข้อมูลบุคคล"),
    (r"you own the (\S+)", "คุณเป็นเจ้าของ {0}"),
    (r"you own (\S+), where (\S+) works", "คุณเป็นเจ้าของ {0} ซึ่ง {1} ทำงานอยู่"),
    (r"you own (\S+)", "คุณเป็นเจ้าของ {0}"),
    (r"you approve instances", "คุณเป็นผู้อนุมัติอินสแตนซ์"),
))


def say(language: str, text: str, **given: object) -> str:
    """Words in someone's language, as the catalogue has them, with what changes put in."""
    said = TH.get(text, text) if language == THAI else text
    return said.format(**given) if given else said


def translated(language: str, text: str) -> str:
    """A sentence another part of a5s wrote whole, in English, in someone's language, where the
    catalogue knows it: as it is, otherwise."""
    if language == ENGLISH or language != THAI:
        return text
    if text in TH and "{" not in TH[text]:
        return TH[text]
    for pattern, thai in PATTERNS:
        if found := pattern.fullmatch(text):
            return thai.format(*found.groups())
    return text
