"""a5s's own words in the language someone reads (core/languages.py): English, as a5s writes them,
or Thai, for those this catalogue has, the words people read most: what waits on them in the
studio and why, the roles they hold and what each lets them do, and a5s's notes to them in chat.

An English sentence is its own key, with {name}s for what changes, so the code that writes it
stays as readable as it was: each module that writes words someone reads passes its sentence
and what changes to `say`, with the language they read, a version of the settings and why it
waits on someone among them, and what became of a change they asked for, and a5s's own lines in
their digest (round 14's deferrals). Anything the catalogue hasn't stays in English.
tests/test_languages.py holds each Thai to its English's {name}s.
"""

from __future__ import annotations

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
        "{whose} ใช้ไปแล้ว {amount} ในเดือนนี้ เกินงบ\u2060ประมาณที่ตั้งไว้ {budget}",
    "{whose} is on course to spend {amount} this month, past its budget of {budget}":
        "{whose} มีแนวโน้มจะใช้ {amount} ในเดือนนี้ เกินงบ\u2060ประมาณที่ตั้งไว้ {budget}",
    "you own {what}": "คุณเป็นเจ้าของ {what}",
    "{whose} ran {n} times this month on a model whose prices aren't known, which count for "
    "nothing against its budget":
        "{whose} ทำงาน {n} ครั้งในเดือนนี้บนโมเดลที่ไม่ทราบราคา ซึ่งไม่ถูกนับรวมในงบประมาณ",
    "Budgets are in {theirs}, and models.yaml prices models in {prices}, so a5s compares neither":
        "งบประมาณเป็นสกุลเงิน {theirs} แต่ models.yaml กำหนดราคาโมเดลเป็น {prices} "
        "a5s จึงไม่เปรียบเทียบทั้งสองอย่าง",
    "no currency it names": "สกุลเงินที่ไม่ได้ระบุ",
    "you own a budget": "คุณเป็นเจ้าของงบประมาณ",
    # The map of what depends on what (core/dependencies.py): each edge whole, with {from} and
    # {to} where the page names them, and what each thing on it is
    "{from} may call {to}": "{from} เรียกใช้ {to} ได้",
    "{from} comes from {to}": "{from} มาจาก {to}",
    "{from} acts in {to} as the person it acts for, with their own permissions":
        "{from} ทำงานใน {to} ในนามของผู้ที่ทำงานให้ ด้วยสิทธิ์ของผู้นั้นเอง",
    "{to}'s {type} events start {from}'s runs": "เหตุการณ์ {type} จาก {to} เริ่มการทำงานของ {from}",
    "{from}'s release names {to}": "รีลีสของ {from} ระบุ {to}",
    "{to} judges {from}'s work": "{to} ประเมินงานของ {from}",
    "{from} runs {to}'s version {release}": "{from} ใช้งาน {to} เวอร์ชัน {release}",
    "{from} calls {to}": "{from} เรียกใช้ {to}",
    "{from} works in {to}, at level {level}": "{from} ทำงานใน {to} ที่ระดับ {level}",
    "{from} works in {to}, at level {level}, and at level 2 for {types}":
        "{from} ทำงานใน {to} ที่ระดับ {level} และที่ระดับ 2 สำหรับ {types}",
    "{from} works in {to}, at level {level}; the settings set level 2 for {held}, which a5s's "
    "cap holds at level 1 until graded samples show it's accurate enough":
        "{from} ทำงานใน {to} ที่ระดับ {level} การตั้งค่ากำหนดระดับ 2 สำหรับ {held} "
        "ซึ่งเพดานของ a5s ยังคงไว้ที่ระดับ 1 จนกว่าตัวอย่างที่ให้คะแนนแล้วจะแสดงว่าแม่นยำพอ",
    "{from} works in {to}, at level {level}, and at level 2 for {types}; the settings set "
    "level 2 for {held} too, which a5s's cap holds at level 1 until graded samples show it's "
    "accurate enough":
        "{from} ทำงานใน {to} ที่ระดับ {level} และที่ระดับ 2 สำหรับ {types} การตั้งค่ากำหนดระดับ 2 "
        "สำหรับ {held} ด้วย ซึ่งเพดานของ a5s ยังคงไว้ที่ระดับ 1 จนกว่าตัวอย่างที่ให้คะแนนแล้วจะแสดงว่าแม่นยำพอ",
    "{from} works in {to}, at level {level}; the settings set level 2 for {held}, which counts "
    "only once an owner of {to} approves the settings in force":
        "{from} ทำงานใน {to} ที่ระดับ {level} การตั้งค่ากำหนดระดับ 2 สำหรับ {held} "
        "ซึ่งจะมีผลเมื่อเจ้าของ {to} อนุมัติการตั้งค่าที่ใช้อยู่แล้วเท่านั้น",
    "{from} may ask {to}": "{from} ถาม {to} ได้",
    "(a5s: what the {agent} just changed can be undone until {until}, on its page: {link})":
        "(a5s: สิ่งที่ {agent} เพิ่งเปลี่ยนยกเลิกได้จนถึง {until} ที่หน้าของรายการนี้: {link})",
    # Handing a conversation over (core/handover.py), and what the team answers
    "The {agent} has handed this conversation to the {team} team, at your word: someone there "
    "answers you here. They read its brief, and what you've said to it since you last left it a "
    "day or more, but not its answers nor anything older. The {agent} answers again once they "
    "hand it back.":
        "{agent} ส่งต่อการสนทนานี้ให้ทีม {team} ตามที่คุณขอ: จะมีคนจากทีมนั้นตอบคุณที่นี่ "
        "พวกเขาอ่านสรุปของเอเจนต์ และสิ่งที่คุณพูดกับเอเจนต์ตั้งแต่ครั้งล่าสุดที่คุณเว้นไปหนึ่งวันขึ้นไป "
        "แต่ไม่ได้อ่านคำตอบของเอเจนต์หรือสิ่งที่เก่ากว่านั้น {agent} จะตอบอีกครั้งเมื่อทีมส่งคืน",
    "The {team} team has handed this conversation back to the {agent}, which answers you again "
    "from here.":
        "ทีม {team} ส่งการสนทนานี้คืนให้ {agent} แล้ว ซึ่งจะตอบคุณต่อจากนี้",
    "{name}, of the {team} team: {said}": "{name} จากทีม {team}: {said}",
    "[a record you may not see]": "[ระเบียนที่คุณไม่มีสิทธิ์เห็น]",
    "[the agent's brief, which draws on records you may not see: read what they've said "
    "instead]": "[สรุปของเอเจนต์ ซึ่งอ้างอิงระเบียนที่คุณไม่มีสิทธิ์เห็น: โปรดอ่านสิ่งที่ผู้นั้นพูดแทน]",
    # What waits on an instance (core/home.py)
    "{n} change it asked for waits for your decision": "การเปลี่ยนแปลง {n} รายการที่เอเจนต์ขอรอการตัดสินใจของคุณ",
    "{n} changes it asked for wait for your decision": "การเปลี่ยนแปลง {n} รายการที่เอเจนต์ขอรอการตัดสินใจของคุณ",
    "{n} change it asked for waits for someone else's decision, as its parts' owners and "
    "delegates decide them":
        "การเปลี่ยนแปลง {n} รายการที่เอเจนต์ขอรอการตัดสินใจของผู้อื่น ตามที่เจ้าของส่วนงานและผู้ได้รับมอบหมายเป็นผู้ตัดสิน",
    "{n} changes it asked for wait for someone else's decision, as its parts' owners and "
    "delegates decide them":
        "การเปลี่ยนแปลง {n} รายการที่เอเจนต์ขอรอการตัดสินใจของผู้อื่น ตามที่เจ้าของส่วนงานและผู้ได้รับมอบหมายเป็นผู้ตัดสิน",
    "{n} sample of its work waits for your grade": "ตัวอย่างงาน {n} รายการรอการให้คะแนนของคุณ",
    "{n} samples of its work wait for your grade": "ตัวอย่างงาน {n} รายการรอการให้คะแนนของคุณ",
    "{n} or more samples of its work wait for your grade": "ตัวอย่างงาน {n} รายการขึ้นไปรอการให้คะแนนของคุณ",
    "{n} sample of its work waits for a grade, from graders outside the team that built it":
        "ตัวอย่างงาน {n} รายการรอการให้คะแนนจากผู้ให้คะแนนนอกทีมที่สร้างเอเจนต์",
    "{n} samples of its work wait for a grade, from graders outside the team that built it":
        "ตัวอย่างงาน {n} รายการรอการให้คะแนนจากผู้ให้คะแนนนอกทีมที่สร้างเอเจนต์",
    "{n} note it keeps from what it learned, which you may read and remove":
        "บันทึก {n} รายการที่เอเจนต์เก็บจากสิ่งที่เรียนรู้ ซึ่งคุณอ่านและลบได้",
    "{n} notes it keeps from what it learned, which you may read and remove":
        "บันทึก {n} รายการที่เอเจนต์เก็บจากสิ่งที่เรียนรู้ ซึ่งคุณอ่านและลบได้",
    "{from} answers beside {to}, and sends nothing": "{from} ตอบคู่กับ {to} โดยไม่ส่งสิ่งใดออกไป",
    "{from} may hand a conversation to {to}, whose people answer it":
        "{from} ส่งต่อบทสนทนาให้ {to} ได้ ซึ่งคนในทีมจะเป็นผู้ตอบ",
    "people who answer the conversations handed to them": "ผู้ที่ตอบบทสนทนาที่ส่งต่อมาให้",
    "an MCP server": "เซิร์ฟเวอร์ MCP",
    "the scenario's own records": "ระเบียนของสถานการณ์เอง",
    "a library of documents": "คลังเอกสาร",
    "sends events": "ส่งเหตุการณ์",
    "a system agents act in as the person, with their own permissions":
        "ระบบที่เอเจนต์ทำงานในนามของบุคคล ด้วยสิทธิ์ของบุคคลนั้นเอง",
    "a part of the records, which its owners decide for":
        "ส่วนหนึ่งของระเบียน ซึ่งเจ้าของส่วนงานเป็นผู้ตัดสินใจ",
    "not in the scenario now": "ไม่มีในสถานการณ์แล้ว",
    "not in models.yaml": "ไม่มีใน models.yaml",
    "at work": "กำลังทำงาน",
    "suspended": "ถูกระงับ",
    "waiting for approval": "รอการอนุมัติ",
    "a shadow: it answers beside another, and sends nothing":
        "เงา: ตอบคู่กับอินสแตนซ์อื่น โดยไม่ส่งสิ่งใดออกไป",
    # What a version of the settings would have done differently (core/impact.py)
    "It decides again the agents' tool calls, and nothing else: not which models may answer, "
    "whom an instance serves, whom it asks or hands conversations to, or what shadows do. Each "
    "call is decided as the directory, the agents' releases, the records' parts and a5s's caps "
    "stand now. A change someone asked for of their own records counts as theirs only where the "
    "decision recorded shows it was.":
        "ตัวอย่างนี้ตัดสินเฉพาะการเรียกใช้เครื่องมือของเอเจนต์ใหม่อีกครั้งเท่านั้น ไม่ได้ตัดสินว่าโมเดลใดตอบได้ "
        "อินสแตนซ์ให้บริการใคร ถามใครหรือส่งต่อการสนทนาให้ใคร หรือเงาทำอะไร "
        "แต่ละการเรียกใช้ถูกตัดสินตามไดเรกทอรี รีลีสของเอเจนต์ ส่วนงานของระเบียน และเพดานของ a5s "
        "ในปัจจุบัน การเปลี่ยนแปลงที่ผู้ใดขอสำหรับระเบียนของตนเอง จะนับเป็นของผู้นั้นเฉพาะเมื่อการตัดสินที่บันทึกไว้แสดงเช่นนั้น",
    "It changes the classes of data, which decide which models may answer: it doesn't decide "
    "the agents' model calls again.":
        "เวอร์ชันนี้เปลี่ยนประเภทข้อมูล ซึ่งกำหนดว่าโมเดลใดตอบได้: ตัวอย่างนี้ไม่ได้ตัดสินการเรียกโมเดลของเอเจนต์ใหม่",
    "It changes whom {instance} serves, which it doesn't decide again.":
        "เวอร์ชันนี้เปลี่ยนผู้ที่ {instance} ให้บริการ ซึ่งตัวอย่างนี้ไม่ได้ตัดสินใหม่",
    "It changes whom {instance} may ask, which it doesn't decide again.":
        "เวอร์ชันนี้เปลี่ยนผู้ที่ {instance} ถามได้ ซึ่งตัวอย่างนี้ไม่ได้ตัดสินใหม่",
    "It changes whom {instance} may hand conversations to, which it doesn't decide again.":
        "เวอร์ชันนี้เปลี่ยนผู้ที่ {instance} ส่งต่อการสนทนาให้ได้ ซึ่งตัวอย่างนี้ไม่ได้ตัดสินใหม่",
    "It changes what {instance} shadows, which it doesn't decide again.":
        "เวอร์ชันนี้เปลี่ยนสิ่งที่ {instance} เป็นเงาให้ ซึ่งตัวอย่างนี้ไม่ได้ตัดสินใหม่",
    "It changes what agents may spend, which decides when they stop for the month: it doesn't "
    "decide that again.":
        "เวอร์ชันนี้เปลี่ยนงบที่เอเจนต์ใช้ได้ ซึ่งกำหนดว่าจะหยุดเมื่อใดในเดือนนั้น: ตัวอย่างนี้ไม่ได้ตัดสินใหม่",
    "It changes the data protection officer's choices, which it doesn't decide again.":
        "เวอร์ชันนี้เปลี่ยนตัวเลือกของเจ้าหน้าที่คุ้มครองข้อมูล ซึ่งตัวอย่างนี้ไม่ได้ตัดสินใหม่",
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
    "changes agents ask for there; and watch those instances' runs, and what they cost":
        "อนุมัติอินสแตนซ์ที่ทำงานใน {scope} และขอบเขตที่แต่ละตัวทำได้ที่นั่น ตัดสินใจเรื่องการเปลี่ยนแปลงที่เอเจนต์ขอที่นั่น "
        "และติดตามการทำงานของอินสแตนซ์เหล่านั้น รวมถึงค่าใช้จ่าย",
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
    "Noted: its owners will see that answer, the run behind it and what you said of it, to check "
    "it, and who you are only if the data protection officer lets them.":
        "รับทราบแล้ว เจ้าของเอเจนต์จะเห็นคำตอบนั้น การทำงานเบื้องหลัง และสิ่งที่คุณบอกเกี่ยวกับคำตอบนั้นเพื่อตรวจสอบ "
        "และจะรู้ว่าคุณเป็นใครก็ต่อเมื่อเจ้าหน้าที่คุ้มครองข้อมูลอนุญาต",
    # A version of the settings in words, as approvers read it (core/approvals.py)
    "nobody": "ไม่มีใคร",
    "none": "ไม่มี",
    "everyone in the {team} team": "ทุกคนในทีม {team}",
    "everyone who holds the {role} role": "ทุกคนที่มีบทบาท {role}",
    "the {team} team": "ทีม {team}",
    "the {teams} and {last} teams": "ทีม {teams} และ {last}",
    "the {agent} ({id})": "{agent} ({id})",
    "{n} in one run": "{n} รายการต่อการทำงานหนึ่งครั้ง",
    "{n} for one person in 30 days": "{n} รายการต่อบุคคลใน 30 วัน",
    "no limit": "ไม่มีขีดจำกัด",
    "in no part, at level {level}": "ไม่อยู่ในส่วนงานใด ที่ระดับ {level}",
    "working in {parts}": "ทำงานใน {parts}",
    "{part} at level {level}": "{part} ที่ระดับ {level}",
    "{field} is {data_class}": "{field} เป็น {data_class}",
    "{data_class}, except that {own}": "{data_class} ยกเว้น {own}",
    "{n} days": "{n} วัน",
    "{n} months": "{n} เดือน",
    "The scenario's data becomes {now}, instead of {was}.":
        "ข้อมูลของซีนาริโอเปลี่ยนเป็น {now} จากเดิม {was}",
    "The limit for {action} becomes {now}, instead of {was}.":
        "ขีดจำกัดของ {action} เปลี่ยนเป็น {now} จากเดิม {was}",
    "The limit for {action} becomes {now}.": "ขีดจำกัดของ {action} เปลี่ยนเป็น {now}",
    "{action} has no limit any more, instead of {was}.":
        "{action} ไม่มีขีดจำกัดอีกต่อไป จากเดิม {was}",
    "none, so none earns it": "ไม่มี จึงไม่มีเอเจนต์ใดได้ระดับ 2",
    "The accuracy {part} needs before an agent earns level 2 there becomes {share}, instead of "
    "{was}.":
        "ความแม่นยำที่ {part} ต้องการก่อนเอเจนต์จะได้ระดับ 2 ที่นั่น เปลี่ยนเป็น {share} จากเดิม {was}",
    "The accuracy {part} needs before an agent earns level 2 there becomes {share}.":
        "ความแม่นยำที่ {part} ต้องการก่อนเอเจนต์จะได้ระดับ 2 ที่นั่น เปลี่ยนเป็น {share}",
    "the currency models.yaml prices models in": "สกุลเงินที่ models.yaml ใช้กำหนดราคาโมเดล",
    "Budgets are in {now}, instead of {was}.": "งบประมาณใช้ {now} จากเดิม {was}",
    "There's no budget for the {name} any more, instead of {was} a month.":
        "{name} ไม่มีงบประมาณอีกต่อไป จากเดิม {was} ต่อเดือน",
    "The budget for the {name} becomes {amount} a month, instead of {was}: what its model calls "
    "may cost, which a5s shows spending against, and which stops no work.":
        "งบประมาณของ {name} เปลี่ยนเป็น {amount} ต่อเดือน จากเดิม {was}: คือค่าใช้จ่ายที่การเรียกโมเดลใช้ได้ "
        "ซึ่ง a5s แสดงการใช้จ่ายเทียบกับงบนี้ และไม่หยุดงานใด",
    "The budget for the {name} becomes {amount} a month: what its model calls may cost, which "
    "a5s shows spending against, and which stops no work.":
        "งบประมาณของ {name} เปลี่ยนเป็น {amount} ต่อเดือน: คือค่าใช้จ่ายที่การเรียกโมเดลใช้ได้ "
        "ซึ่ง a5s แสดงการใช้จ่ายเทียบกับงบนี้ และไม่หยุดงานใด",
    "Adds {id}: the {agent}, {where}, serving {whom}, run by {owner}.":
        "เพิ่ม {id}: {agent} {where} ให้บริการ {whom} ดูแลโดย {owner}",
    "Adds {id}: the {agent}, {where}, serving {whom}.": "เพิ่ม {id}: {agent} {where} ให้บริการ {whom}",
    "It may ask {asked} questions, for the people it acts for, which each answers from the "
    "records in its own parts that those people may see.":
        "อินสแตนซ์นี้ถามคำถาม {asked} ได้ แทนผู้ที่ตนทำงานให้ ซึ่งแต่ละตัวตอบจากระเบียนในส่วนงานของตน"
        "ที่บุคคลเหล่านั้นดูได้",
    "{id} may ask {asked} questions, for the people it acts for, which each answers from the "
    "records in its own parts that those people may see.":
        "{id} ถามคำถาม {asked} ได้ แทนผู้ที่ตนทำงานให้ ซึ่งแต่ละตัวตอบจากระเบียนในส่วนงานของตน"
        "ที่บุคคลเหล่านั้นดูได้",
    "It may hand a conversation over, at its agent's word, to the people of {teams}, who read "
    "its brief and what the person said, and answer them in the same chat until they hand it "
    "back.":
        "อินสแตนซ์นี้ส่งต่อการสนทนาให้คนใน{teams}ได้ เมื่อเอเจนต์เห็นควร ซึ่งจะอ่านสรุปและสิ่งที่ผู้นั้นพูด "
        "และตอบในแชทเดียวกันจนกว่าจะส่งคืน",
    "{id} may hand a conversation over, at its agent's word, to the people of {teams}, who read "
    "its brief and what the person said, and answer them in the same chat until they hand it "
    "back.":
        "{id} ส่งต่อการสนทนาให้คนใน{teams}ได้ เมื่อเอเจนต์เห็นควร ซึ่งจะอ่านสรุปและสิ่งที่ผู้นั้นพูด "
        "และตอบในแชทเดียวกันจนกว่าจะส่งคืน",
    "It's a shadow: it answers what {live} is asked, beside it, as the same people, sending and "
    "changing nothing: graders read its answers beside those sent.":
        "อินสแตนซ์นี้เป็นเงา: ตอบสิ่งที่ {live} ถูกถามคู่กันไปในนามของคนกลุ่มเดียวกัน "
        "โดยไม่ส่งและไม่เปลี่ยนแปลงสิ่งใด: ผู้ให้คะแนนอ่านคำตอบของเงาเทียบกับคำตอบที่ส่งไปแล้ว",
    "{id} answers what {live} is asked, beside it, as the same people, sending and changing "
    "nothing: graders read its answers beside those sent, as a shadow.":
        "{id} ตอบสิ่งที่ {live} ถูกถามคู่กันไปในฐานะเงา ในนามของคนกลุ่มเดียวกัน "
        "โดยไม่ส่งและไม่เปลี่ยนแปลงสิ่งใด: ผู้ให้คะแนนอ่านคำตอบของเงาเทียบกับคำตอบที่ส่งไปแล้ว",
    "{id} is no longer a shadow of {live}: it works for its people itself.":
        "{id} ไม่ได้เป็นเงาของ {live} อีกต่อไป: ทำงานให้ผู้คนของตนเองโดยตรง",
    "{id} no longer hands conversations to {teams}.": "{id} ไม่ส่งต่อการสนทนาให้{teams}อีกต่อไป",
    "{id} no longer asks {asked}.": "{id} ไม่ถาม {asked} อีกต่อไป",
    "{id} becomes the {agent}, instead of the {was}.": "{id} เปลี่ยนเป็น {agent} จากเดิม {was}",
    "{id} serves {whom} as well.": "{id} ให้บริการ {whom} ด้วย",
    "{id} no longer serves {whom}.": "{id} ไม่ให้บริการ {whom} อีกต่อไป",
    "{id}'s level goes from {was} to {now}.": "ระดับของ {id} เปลี่ยนจาก {was} เป็น {now}",
    "{id} works in {part} as well, at level {level}.": "{id} ทำงานใน {part} ด้วย ที่ระดับ {level}",
    "{id} no longer works in {part}.": "{id} ไม่ทำงานใน {part} อีกต่อไป",
    "{id}'s level in {part} goes from {was} to {now}.":
        "ระดับของ {id} ใน {part} เปลี่ยนจาก {was} เป็น {now}",
    "{id}'s level for {action} in {part} goes from {was} to {now}, where it acts and reports, "
    "once samples show it's accurate enough.":
        "ระดับของ {id} สำหรับ {action} ใน {part} เปลี่ยนจาก {was} เป็น {now} "
        "ซึ่งจะลงมือทำแล้วรายงาน เมื่อตัวอย่างแสดงว่าแม่นยำพอ",
    "{id}'s level for {action} in {part} goes from {was} to {now}.":
        "ระดับของ {id} สำหรับ {action} ใน {part} เปลี่ยนจาก {was} เป็น {now}",
    "{id}'s owner changes from {was} to {now}.": "เจ้าของ {id} เปลี่ยนจาก {was} เป็น {now}",
    "{id}'s deputy changes from {was} to {now}.": "ผู้แทนของ {id} เปลี่ยนจาก {was} เป็น {now}",
    "Retires {id}, which served {whom}.": "เลิกใช้ {id} ซึ่งเคยให้บริการ {whom}",
    "Everyone in the group {group} holds {roles}, as their sign-ins show they're in it.":
        "ทุกคนในกลุ่ม {group} มีบทบาท {roles} ตามที่การลงชื่อเข้าใช้แสดงว่าอยู่ในกลุ่มนั้น",
    "The group {group} no longer gives {roles}.": "กลุ่ม {group} ไม่ให้บทบาท {roles} อีกต่อไป",
    "a5s keeps what's said for {kept} after a conversation's last message, and what goes with "
    "it, instead of {was}.":
        "a5s เก็บสิ่งที่พูดกันไว้ {kept} หลังข้อความสุดท้ายของการสนทนา รวมถึงสิ่งที่เกี่ยวข้อง จากเดิม {was}",
    "An instance's own figures go out to the team's dashboards once it serves {n} people, "
    "instead of {was}.":
        "ตัวเลขของอินสแตนซ์จะส่งไปยังแดชบอร์ดของทีมเมื่ออินสแตนซ์ให้บริการ {n} คน จากเดิม {was}",
    "a5s keeps what's said for {kept} after a conversation's last message, and what goes with "
    "it.":
        "a5s เก็บสิ่งที่พูดกันไว้ {kept} หลังข้อความสุดท้ายของการสนทนา รวมถึงสิ่งที่เกี่ยวข้อง",
    "An instance's own figures go out to the team's dashboards once it serves {n} people or "
    "more.":
        "ตัวเลขของอินสแตนซ์จะส่งไปยังแดชบอร์ดของทีมเมื่ออินสแตนซ์ให้บริการตั้งแต่ {n} คนขึ้นไป",
    "The studio's pages name whom each run acted for.":
        "หน้าต่าง ๆ ของสตูดิโอระบุชื่อผู้ที่การทำงานแต่ละครั้งทำแทน",
    "The studio's pages say how many people each run acted for, never who.":
        "หน้าต่าง ๆ ของสตูดิโอบอกเพียงจำนวนคนที่การทำงานแต่ละครั้งทำแทน ไม่ระบุว่าเป็นใคร",
    "The auditors' page names whom agents acted for, and exports the ledger.":
        "หน้าของผู้ตรวจสอบระบุชื่อผู้ที่เอเจนต์ทำงานแทน และส่งออกเลดเจอร์ได้",
    "The auditors' page shows stand-ins for whom agents acted for, and exports nothing.":
        "หน้าของผู้ตรวจสอบแสดงชื่อสมมติแทนผู้ที่เอเจนต์ทำงานแทน และไม่ส่งออกสิ่งใด",
    "The status names the deciders whose approvals are graded wrong far more often than "
    "others'.":
        "หน้าสถานะระบุชื่อผู้ตัดสินที่การอนุมัติถูกให้คะแนนว่าผิดบ่อยกว่าคนอื่นมาก",
    "The status names no decider for how often their approvals are graded wrong.":
        "หน้าสถานะไม่ระบุชื่อผู้ตัดสินคนใด ไม่ว่าการอนุมัติจะถูกให้คะแนนว่าผิดบ่อยเพียงใด",
    "Those who author an agent may keep one of its runs as a test case, where every one of them "
    "may see the run: what someone said to it, masked by code and checked by whoever keeps it. "
    "Every author of the agent reads it, and once it's released, so does everyone who reads the "
    "agents' repository.":
        "ผู้เขียนเอเจนต์เก็บการทำงานครั้งหนึ่งของเอเจนต์เป็นกรณีทดสอบได้ เมื่อผู้เขียนทุกคนดูการทำงานนั้นได้: "
        "สิ่งที่มีคนพูดกับเอเจนต์ ซึ่งโค้ดปิดบังข้อมูลไว้และผู้ที่เก็บเป็นผู้ตรวจ ผู้เขียนเอเจนต์ทุกคนอ่านได้ "
        "และเมื่อรีลีสแล้ว ทุกคนที่อ่านรีโพสิทอรีของเอเจนต์ก็อ่านได้เช่นกัน",
    "No run of an agent's becomes a test case: its cases are made up.":
        "ไม่มีการทำงานใดของเอเจนต์ที่กลายเป็นกรณีทดสอบ: กรณีทดสอบเป็นข้อมูลที่แต่งขึ้นทั้งหมด",
    "A shadow may answer what people ask the instance it shadows, beside it, sending and changing "
    "nothing: it reads what they say and what their records hold, and graders read what it "
    "answered beside what was sent, with what they said, masked by code unless names are shown, "
    "as the studio shows runs.":
        "เงาตอบสิ่งที่ผู้คนถามอินสแตนซ์ที่ตนเป็นเงาให้ได้ คู่กันไป โดยไม่ส่งและไม่เปลี่ยนแปลงสิ่งใด: "
        "เงาอ่านสิ่งที่ผู้คนพูดและสิ่งที่อยู่ในระเบียนของพวกเขา และผู้ให้คะแนนอ่านคำตอบของเงาเทียบกับสิ่งที่ส่งไปแล้ว "
        "พร้อมสิ่งที่ผู้คนพูด ซึ่งโค้ดปิดบังข้อมูลไว้ เว้นแต่จะแสดงชื่อ ตามที่สตูดิโอแสดงการทำงาน",
    "No shadow answers what people ask: a new version is tried on test cases alone.":
        "ไม่มีเงาตอบสิ่งที่ผู้คนถาม: เวอร์ชันใหม่ทดลองกับกรณีทดสอบเท่านั้น",
    "It changes nothing the agents do: only its number or its notes.":
        "เวอร์ชันนี้ไม่เปลี่ยนสิ่งที่เอเจนต์ทำ: เปลี่ยนเพียงหมายเลขหรือหมายเหตุ",
    "The scenario's data is {classes}.": "ข้อมูลของซีนาริโอเป็น {classes}",
    "{id}: the {agent}, {where}, serving {whom}, run by {owner} with {deputy} as deputy.":
        "{id}: {agent} {where} ให้บริการ {whom} ดูแลโดย {owner} โดยมี {deputy} เป็นผู้แทน",
    "{id}: the {agent}, {where}, serving {whom}, run by {owner}.":
        "{id}: {agent} {where} ให้บริการ {whom} ดูแลโดย {owner}",
    "{id}: the {agent}, {where}, serving {whom}, with {deputy} as deputy.":
        "{id}: {agent} {where} ให้บริการ {whom} โดยมี {deputy} เป็นผู้แทน",
    "{id}: the {agent}, {where}, serving {whom}.": "{id}: {agent} {where} ให้บริการ {whom}",
    "{id} works at level {level} for {action} in {part}, where it acts and reports, once graded "
    "samples show it's accurate enough: until then a5s holds it at level 1.":
        "{id} ทำงานที่ระดับ {level} สำหรับ {action} ใน {part} ซึ่งจะลงมือทำแล้วรายงาน "
        "เมื่อตัวอย่างที่ให้คะแนนแล้วแสดงว่าแม่นยำพอ: ระหว่างนี้ a5s คงไว้ที่ระดับ 1",
    "{id} works at level {level} for {action} in {part}.":
        "{id} ทำงานที่ระดับ {level} สำหรับ {action} ใน {part}",
    "No instances: every agent here is retired.": "ไม่มีอินสแตนซ์: เอเจนต์ทุกตัวที่นี่เลิกใช้แล้ว",
    "Limit for {action}: {limit}.": "ขีดจำกัดของ {action}: {limit}",
    "An agent earns level 2 in {part} once graded samples show it's {share} accurate.":
        "เอเจนต์จะได้ระดับ 2 ใน {part} เมื่อตัวอย่างที่ให้คะแนนแล้วแสดงความแม่นยำ {share}",
    "The budget for the {name} is {amount} a month: what its model calls may cost, which a5s "
    "shows spending against.":
        "งบประมาณของ {name} คือ {amount} ต่อเดือน: ค่าใช้จ่ายที่การเรียกโมเดลใช้ได้ "
        "ซึ่ง a5s แสดงการใช้จ่ายเทียบกับงบนี้",
    "The budget for the {name} is {amount} a month: what its model calls may cost, which a5s "
    "shows spending against, in the currency models.yaml prices models in.":
        "งบประมาณของ {name} คือ {amount} ต่อเดือน: ค่าใช้จ่ายที่การเรียกโมเดลใช้ได้ "
        "ซึ่ง a5s แสดงการใช้จ่ายเทียบกับงบนี้ ในสกุลเงินที่ models.yaml ใช้กำหนดราคาโมเดล",
    "Settings to approve": "การตั้งค่าที่รออนุมัติ",
    "What it changes:": "สิ่งที่เปลี่ยนแปลง:",
    "Version {serial} of a5s's settings waits for its instance approvers to approve it.":
        "การตั้งค่า a5s เวอร์ชัน {serial} รอให้ผู้อนุมัติอนุมัติ",
    "You decide on a5s's page, after signing in again. Telling an agent doesn't approve "
    "anything.":
        "คุณตัดสินใจที่หน้าของ a5s หลังจากลงชื่อเข้าใช้อีกครั้ง การบอกเอเจนต์ไม่ถือเป็นการอนุมัติใด ๆ",
    "Review and approve": "ตรวจทานและอนุมัติ",
    "Review it, and approve it only if you mean it, at {link}":
        "ตรวจทาน และอนุมัติเฉพาะเมื่อคุณตั้งใจจริง ที่ {link}",
    # Why a version waits on someone, and why an ask for an agent does (core/registry.py,
    # core/asks.py), and what gave someone a role (core/administration.py)
    "the owner of {part} hasn't approved it": "เจ้าของ {part} ยังไม่ได้อนุมัติ",
    "the owner of the {agent} hasn't approved its budget": "เจ้าของ {agent} ยังไม่ได้อนุมัติงบประมาณ",
    "no instance-approver has approved it, for the instances in no part":
        "ยังไม่มีผู้อนุมัติอินสแตนซ์อนุมัติ สำหรับอินสแตนซ์ที่ไม่อยู่ในส่วนงานใด",
    "no instance-approver has approved its classes of data":
        "ยังไม่มีผู้อนุมัติอินสแตนซ์อนุมัติประเภทของข้อมูล",
    "the {owner} named in the directory hasn't approved giving {group} the {role} role":
        "{owner} ที่ระบุในไดเรกทอรียังไม่ได้อนุมัติการให้บทบาท {role} แก่ {group}",
    "the data-protection-officer named in the directory hasn't approved its choices for people's "
    "data":
        "เจ้าหน้าที่คุ้มครองข้อมูลที่ระบุในไดเรกทอรียังไม่ได้อนุมัติตัวเลือกเกี่ยวกับข้อมูลบุคคล",
    "nobody who approves instances has approved it": "ยังไม่มีผู้อนุมัติอินสแตนซ์คนใดอนุมัติ",
    "you own the {agent}": "คุณเป็นเจ้าของ {agent}",
    "you own {part}, where {instance} works": "คุณเป็นเจ้าของ {part} ซึ่ง {instance} ทำงานอยู่",
    "you approve instances": "คุณเป็นผู้อนุมัติอินสแตนซ์",
    "group {group}": "กลุ่ม {group}",
    # What became of a held change, as whoever it was for hears it (core/proposals.py), and what
    # its deciders read in their digest
    "{by} approved {key}, and a5s has made it: {change}":
        "{by} อนุมัติ {key} แล้ว และ a5s ดำเนินการแล้ว: {change}",
    "{by} approved {key}, and a5s has made it: {change} {undo}":
        "{by} อนุมัติ {key} แล้ว และ a5s ดำเนินการแล้ว: {change} {undo}",
    "{by} didn't approve {key}, so a5s didn't make it: {change}":
        "{by} ไม่อนุมัติ {key} a5s จึงไม่ได้ดำเนินการ: {change}",
    "{by} didn't approve {key}, so a5s didn't make it: {change} They said: {reason}":
        "{by} ไม่อนุมัติ {key} a5s จึงไม่ได้ดำเนินการ: {change} เหตุผล: {reason}",
    "Nobody decided {key} within {days} working days, so a5s let it go: {change} Ask again if "
    "it's still needed.":
        "ไม่มีใครตัดสิน {key} ภายใน {days} วันทำการ a5s จึงปล่อยคำขอนี้ไป: {change} "
        "หากยังต้องการ โปรดขออีกครั้ง",
    "{by} approved {key}, but a5s didn't make it, since {what} changed after it was asked for: "
    "{change} Ask again if it's still needed.":
        "{by} อนุมัติ {key} แล้ว แต่ a5s ไม่ได้ดำเนินการ เพราะ {what} เปลี่ยนไปหลังจากมีการขอ: {change} "
        "หากยังต้องการ โปรดขออีกครั้ง",
    "{by} approved {key}, but a5s couldn't make it, since {why}: {change}":
        "{by} อนุมัติ {key} แล้ว แต่ a5s ดำเนินการไม่ได้ เพราะ {why}: {change}",
    "{by} approved {key}, but the records system didn't take it ({error}): {change}":
        "{by} อนุมัติ {key} แล้ว แต่ระบบระเบียนไม่รับ ({error}): {change}",
    "a5s stopped part way through making {key}, so it may or may not have been made, and {by} "
    "has ended it, having checked the records system: {change} Ask again if it's still needed.":
        "a5s หยุดกลางคันระหว่างดำเนินการ {key} จึงอาจดำเนินการแล้วหรือยังก็ได้ และ {by} "
        "ได้ปิดรายการนี้หลังจากตรวจสอบระบบระเบียนแล้ว: {change} หากยังต้องการ โปรดขออีกครั้ง",
    "What became of {key}, which you decided: {text}": "ผลของ {key} ที่คุณตัดสิน: {text}",
    "It can be undone until {until}, on its page: {link}":
        "ยกเลิกการเปลี่ยนแปลงนี้ได้จนถึง {until} ที่หน้าของรายการนี้: {link}",
    # a5s's own items in someone's digest (core/digests.py, core/gateway.py)
    "Your day from the {agent}, {day}.": "สรุปวันของคุณจาก {agent} {day}",
    "Your day from a5s, {day}.": "สรุปวันของคุณจาก a5s {day}",
    "From a5s:": "จาก a5s:",
    "From the {agent}:": "จาก {agent}:",
    "The {agent} made a change itself, at level 2, for {whom}: {change}":
        "{agent} ดำเนินการเปลี่ยนแปลงเองที่ระดับ 2 แทน {whom}: {change}",
    "a5s made the change the {agent} asked for, at level 2: {change}":
        "a5s ดำเนินการเปลี่ยนแปลงที่ {agent} ขอ ที่ระดับ 2 แล้ว: {change}",
    "a5s didn't undo the change the {agent} made, as you asked on its page: {why}. {said}":
        "a5s ไม่ได้ยกเลิกการเปลี่ยนแปลงที่ {agent} ทำ ตามที่คุณขอที่หน้าของรายการนี้: {why} {said}",
    "a5s couldn't undo the change the {agent} made, as you asked: the records system didn't "
    "take it. {said}":
        "a5s ยกเลิกการเปลี่ยนแปลงที่ {agent} ทำตามที่คุณขอไม่ได้: ระบบระเบียนไม่รับ {said}",
    "{name} undid a change the {agent} made: {said}":
        "{name} ยกเลิกการเปลี่ยนแปลงที่ {agent} ทำ: {said}",
    "a5s's cap on {instance} for {action} in {part} is now {cap}: {why}, on {graded} grades, "
    "{errors} of them wrong.":
        "เพดานของ a5s สำหรับ {instance} ใน {action} ที่ {part} ตอนนี้คือ {cap}: {why} "
        "จากการให้คะแนน {graded} ครั้ง ผิด {errors} ครั้ง",
    "a5s's cap on {instance} for {action} in {part} is now {cap}: {why}.":
        "เพดานของ a5s สำหรับ {instance} ใน {action} ที่ {part} ตอนนี้คือ {cap}: {why}",
    "a critical error": "มีข้อผิดพลาดร้ายแรง",
    "the part has no threshold": "ส่วนงานนี้ไม่มีเกณฑ์ความแม่นยำ",
    "the part's threshold rose past what its grades show":
        "เกณฑ์ของส่วนงานสูงขึ้นเกินกว่าที่ผลการให้คะแนนแสดง",
    "graded samples show it falls short": "ตัวอย่างที่ให้คะแนนแล้วแสดงว่ายังไม่ถึงเกณฑ์",
    "graded samples show it meets the threshold": "ตัวอย่างที่ให้คะแนนแล้วแสดงว่าถึงเกณฑ์",
    "lowered by {by}": "ลดลงโดย {by}",
    "On {day}, you asked the {agent} to remind you now: {about}. The {agent} is {status}, so a5s "
    "is reminding you itself.":
        "เมื่อ {day} คุณขอให้ {agent} เตือนคุณในตอนนี้: {about} ขณะนี้ {agent} {status} "
        "a5s จึงเตือนคุณเอง",
    "unable to act": "ทำงานไม่ได้",
    "retired": "เลิกใช้แล้ว",
    "agent": "เอเจนต์",
    "{record}, {title}, is due by {time} on {day} and is still open. The {agent} couldn't write "
    "to you about it, as {why}, so a5s is telling you itself.":
        "{record} {title} ครบกำหนดภายในเวลา {time} น. วันที่ {day} และยังเปิดอยู่ "
        "{agent} เขียนถึงคุณเรื่องนี้ไม่ได้ เพราะ{why} a5s จึงแจ้งคุณเอง",
    "it couldn't finish": "ทำงานไม่เสร็จ",
    "unable to write to you just now, as {why}": "เขียนถึงคุณไม่ได้ในตอนนี้ เพราะ{why}",
    "its model isn't answering": "โมเดลไม่ตอบสนอง",
    "it has used its budget for today": "ใช้งบประมาณของวันนี้หมดแล้ว",
    "a5s didn't let its message through": "a5s ไม่อนุญาตให้ส่งข้อความนั้น",
    "it stopped before it finished": "หยุดไปก่อนทำเสร็จ",
    # A sign-in a5s refused to seal, as whoever made it hears in their digest (core/sealing.py)
    "Your approval of version {serial} of the settings didn't count: {why}. If it still waits for "
    "you, approve it again on the settings page, signing in afresh.":
        "การอนุมัติการตั้งค่าเวอร์ชัน {serial} ของคุณไม่นับ: {why} หากยังรอคุณอยู่ "
        "โปรดอนุมัติอีกครั้งที่หน้าการตั้งค่า โดยลงชื่อเข้าใช้ใหม่",
    "Your decision on {named} didn't count: {why}. If it still waits for you, decide it again on "
    "a5s's own page, signing in afresh.":
        "การตัดสินใจของคุณเรื่อง {named} ไม่นับ: {why} หากยังรอคุณอยู่ "
        "โปรดตัดสินใจอีกครั้งที่หน้าของ a5s โดยลงชื่อเข้าใช้ใหม่",
    "Your grades of {n} samples didn't count: {why}. They wait to be graded again, on a5s's own "
    "page.":
        "การให้คะแนนตัวอย่าง {n} รายการของคุณไม่นับ: {why} ตัวอย่างเหล่านั้นรอให้คะแนนใหม่ที่หน้าของ a5s",
    "a5s didn't suspend {instance}, as you asked on its page in the studio: {why}.":
        "a5s ไม่ได้ระงับ {instance} ตามที่คุณขอที่หน้าของอินสแตนซ์ในสตูดิโอ: {why}",
    "a5s didn't resume {instance}, as you asked on its page in the studio: {why}.":
        "a5s ไม่ได้ให้ {instance} กลับมาทำงาน ตามที่คุณขอที่หน้าของอินสแตนซ์ในสตูดิโอ: {why}",
    "the core can't check sign-ins here: it has no identity provider":
        "ระบบหลักตรวจสอบการลงชื่อเข้าใช้ที่นี่ไม่ได้ เพราะไม่มีผู้ให้บริการยืนยันตัวตน",
    "nothing records the sign-in that made it": "ไม่มีบันทึกการลงชื่อเข้าใช้ที่ทำรายการนี้",
    "the sign-in isn't recorded as itself, so it may have been used already":
        "การลงชื่อเข้าใช้ไม่ได้ถูกบันทึกตามจริง จึงอาจถูกใช้ไปแล้ว",
    "the sign-in's salt isn't one the studio makes": "ค่า salt ของการลงชื่อเข้าใช้ไม่ได้มาจากสตูดิโอ",
    "the sign-in is more than a day old, and the identity provider couldn't be reached to check "
    "it":
        "การลงชื่อเข้าใช้เก่ากว่าหนึ่งวัน และติดต่อผู้ให้บริการยืนยันตัวตนเพื่อตรวจสอบไม่ได้",
    "the sign-in is for something else": "การลงชื่อเข้าใช้นี้เป็นของรายการอื่น",
    "the sign-in wasn't to do what was recorded": "การลงชื่อเข้าใช้ไม่ได้ทำเพื่อสิ่งที่บันทึกไว้",
    "the sign-in wasn't made afresh for it": "ไม่ได้ลงชื่อเข้าใช้ใหม่สำหรับรายการนี้",
    "the sign-in wasn't made with a second factor, which this deployment asks for":
        "การลงชื่อเข้าใช้ไม่ได้ใช้การยืนยันตัวตนขั้นที่สอง ซึ่งระบบนี้กำหนดไว้",
    "the sign-in is more than a day old": "การลงชื่อเข้าใช้เก่ากว่าหนึ่งวัน",
    "the sign-in is someone else's": "การลงชื่อเข้าใช้นี้เป็นของคนอื่น",
}


def say(language: str, text: str, /, **given: object) -> str:
    """Words in someone's language, as the catalogue has them, with what changes put in: by any
    name, {text} and {language} among them, as its own two are given only by place."""
    said = TH.get(text, text) if language == THAI else text
    return said.format(**given) if given else said
