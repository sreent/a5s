// The studio's words in Thai for tasks, the notebook, deciding, grading, approving, the officer,
// the audit trail and administration, and the pieces of design those pages share (i18n.ts, th.ts).

export const DECIDE: Record<string, string> = {
  // Tasks
  "{task}, with the {agent}: {status}, {progress}% done": "{task} โดย {agent}: {status} เสร็จแล้ว {progress}%",
  "{task}, with the {agent}: {status}, {progress}% done, {parts}": "{task} โดย {agent}: {status} เสร็จแล้ว {progress}% · งานย่อย {parts}",
  "What it's for names records you may no longer see, so it isn't shown here.":
    "รายละเอียดของงานนี้อ้างถึงระเบียนที่คุณไม่มีสิทธิ์ดูแล้ว จึงไม่แสดงไว้ที่นี่",
  "What it found: {found}": "สิ่งที่พบ: {found}",
  "So far: {found}": "จนถึงตอนนี้: {found}",
  "Why: {why}": "เหตุผล: {why}",
  "It needed: {needed}. You said: {said}": "งานนี้ต้องการ: {needed} คุณตอบว่า: {said}",
  "It needed: you. You said: {said}": "งานนี้ต้องการคุณ คุณตอบว่า: {said}",
  "It has until {until}, and has spent {spent}. Last changed on {updated}.":
    "มีเวลาถึง {until} ใช้ไปแล้ว {spent} เปลี่ยนแปลงล่าสุดเมื่อ {updated}",
  "Cancel": "ยกเลิก",
  "Cancel {task}?": "ยกเลิก {task} หรือไม่",
  "It stops at its next step, with the parts of it still open, and keeps what it found so far. To change what it's for instead, write to the agent in your chat with it.":
    "งานจะหยุดที่ขั้นตอนถัดไปพร้อมงานย่อยที่ยังค้างอยู่ และเก็บสิ่งที่พบไว้จนถึงตอนนี้ หากต้องการเปลี่ยนจุดประสงค์ของงานแทน ให้เขียนถึงเอเจนต์ในแชทกับเอเจนต์นั้น",
  "Cancel it": "ยกเลิกงาน",
  "Cancelled {task}.": "ยกเลิก {task} แล้ว",
  "{repeat}, with the {agent}: {when}, {status}": "{repeat} โดย {agent}: {when} · {status}",
  "Its last task: {task}.": "งานล่าสุด: {task}",
  "Stop": "หยุด",
  "Stop {repeat}?": "หยุด {repeat} หรือไม่",
  "It makes no more tasks. Its last task, if one's going, goes on.":
    "จะไม่สร้างงานใหม่อีก แต่งานล่าสุดที่กำลังทำอยู่ (ถ้ามี) จะทำต่อไป",
  "Stop it": "หยุดการทำซ้ำ",
  "Stopped {repeat}.": "หยุด {repeat} แล้ว",
  "Your tasks": "งานของคุณ",
  "The long tasks you asked your agents for: how each stands, what it's waiting on, and what it has spent. To answer one that needs you, or to change what it's for, write to the agent in your chat with it. Stop any here.":
    "งานระยะยาวที่คุณขอให้เอเจนต์ทำ: แต่ละงานเป็นอย่างไร รออะไรอยู่ และใช้ไปเท่าไร หากต้องการตอบงานที่รอคุณ หรือเปลี่ยนจุดประสงค์ของงาน ให้เขียนถึงเอเจนต์ในแชทกับเอเจนต์นั้น หยุดงานใดก็ได้ที่นี่",
  "No tasks yet. Ask an agent for one in your chat with it.": "ยังไม่มีงาน ขอให้เอเจนต์ทำงานให้ได้ในแชทกับเอเจนต์นั้น",
  "Again and again": "ทำซ้ำเป็นประจำ",
  "The tasks you asked to be done again and again: each time one comes round, it's a task of its own, above. Stopping one leaves its last task to go on.":
    "งานที่คุณขอให้ทำซ้ำเป็นประจำ: ทุกครั้งที่ถึงรอบ จะเกิดเป็นงานแยกของตัวเองในรายการด้านบน การหยุดการทำซ้ำจะไม่หยุดงานล่าสุดที่กำลังทำอยู่",
  "None. Ask an agent to do a task every week, say, in your chat with it.":
    "ยังไม่มี ลองขอให้เอเจนต์ทำงานเป็นประจำ เช่น ทุกสัปดาห์ ในแชทกับเอเจนต์นั้น",

  // The notebook
  "Removed {entry}.": "ลบ {entry} แล้ว",
  "Removed {entry} from the notebook.": "ลบ {entry} ออกจากสมุดบันทึกแล้ว",
  "Notebook": "สมุดบันทึก",
  "What your agents noted from records, on their schedules, for their later runs: each note with the records it comes from. Remove any that's no longer worth keeping. A note whose records stop holding it goes on its own after 90 days.":
    "สิ่งที่เอเจนต์ของคุณบันทึกไว้จากระเบียนตามกำหนดเวลา เพื่อใช้ในการทำงานครั้งต่อไป: แต่ละบันทึกแสดงระเบียนที่เป็นที่มา ลบบันทึกที่ไม่ควรเก็บไว้แล้วได้ บันทึกที่ระเบียนไม่ยืนยันอีกต่อไปจะหายไปเองหลังจาก 90 วัน",
  "Nothing noted yet by {whom}.": "{whom} ยังไม่ได้บันทึกสิ่งใด",
  "or": "หรือ",
  "Kept by {whom}": "บันทึกของ {whom}",
  "{entry}, from": "{entry} จาก",
  ". Noted on {noted}; its records last checked on {checked}.": " บันทึกเมื่อ {noted} ตรวจสอบระเบียนล่าสุดเมื่อ {checked}",
  "Remove": "ลบ",
  "Remove {entry}?": "ลบ {entry} หรือไม่",
  "Its agent no longer has it in its later runs. The ledger keeps that you removed it, by its words' hash.":
    "เอเจนต์จะไม่มีบันทึกนี้ในการทำงานครั้งต่อไป เลดเจอร์จะเก็บไว้ว่าคุณลบบันทึกนี้ โดยเก็บเป็นค่าแฮชของข้อความ",
  "Remove it": "ลบบันทึก",
  "And {more} from records you may not see, which someone who may see them can remove.":
    "และอีก {more}จากระเบียนที่คุณดูไม่ได้ ซึ่งผู้ที่ดูระเบียนเหล่านั้นได้จะลบได้",
  "And {more} from records you may not see, which someone who may see them can remove: {others}, who run its instances, may be able to.":
    "และอีก {more}จากระเบียนที่คุณดูไม่ได้ ซึ่งผู้ที่ดูระเบียนเหล่านั้นได้จะลบได้: {others} ซึ่งดูแลอินสแตนซ์ของสมุดบันทึกนี้อาจลบได้",

  // Deciding held changes (Approve is also the decision card's, below)
  "for {whom}": "สำหรับ {whom}",
  "and": "และ",
  "asked {day}": "ขอเมื่อ {day}",
  "The {agent} asks": "{agent} ขออนุมัติ",
  "What to know": "สิ่งที่ควรรู้",
  "The change and its records are in their system's words, which a5s seals with your decision.":
    "การเปลี่ยนแปลงและระเบียนของรายการนี้เป็นถ้อยคำของระบบที่รายการอยู่ ซึ่ง a5s ผนึกไว้กับการตัดสินใจของคุณ",
  "It's decided on its own, never with others.": "ต้องตัดสินใจรายการนี้แยกต่างหาก ไม่รวมกับรายการอื่น",
  "Open {record}": "เปิด {record}",
  "It lapses on {day} unless someone decides it.": "จะหมดอายุในวันที่ {day} หากไม่มีใครตัดสินใจ",
  "You can see it, as you were told it waits, but only its deciders decide it.":
    "คุณเห็นรายการนี้เพราะได้รับแจ้งว่ารายการนี้รออยู่ แต่มีเพียงผู้ตัดสินใจของรายการนี้เท่านั้นที่ตัดสินใจได้",
  "Why, if you reject it (optional)": "เหตุผล หากคุณปฏิเสธ (ไม่บังคับ)",
  "Why you reject {key}, if you do": "เหตุผลที่คุณปฏิเสธ {key} (ถ้ามี)",
  "Approve": "อนุมัติ",
  "Reject": "ปฏิเสธ",
  "Decide it with the others ticked": "ตัดสินใจพร้อมกับรายการอื่นที่เลือกไว้",
  "Deciding signs you in again, for this decision alone, and the ledger keeps it.":
    "การตัดสินใจจะให้คุณลงชื่อเข้าใช้อีกครั้งสำหรับการตัดสินใจนี้เท่านั้น และเลดเจอร์จะเก็บไว้",
  "You approved {which}.": "คุณอนุมัติ {which} แล้ว",
  "You rejected {which}.": "คุณปฏิเสธ {which} แล้ว",
  "a5s makes each change within a minute, once every part it touches has approved it, if its records haven't changed.":
    "a5s จะทำการเปลี่ยนแปลงแต่ละรายการภายใน 1 นาที เมื่อทุกส่วนงานที่เกี่ยวข้องอนุมัติแล้ว หากระเบียนยังไม่เปลี่ยน",
  "a5s tells whoever asked for it.": "a5s จะแจ้งผู้ที่ขอ",
  "Signing you in again, to approve this change alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่ออนุมัติการเปลี่ยนแปลงนี้เท่านั้น…",
  "Signing you in again, to approve these changes alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่ออนุมัติการเปลี่ยนแปลงเหล่านี้เท่านั้น…",
  "Signing you in again, to reject this change alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่อปฏิเสธการเปลี่ยนแปลงนี้เท่านั้น…",
  "Signing you in again, to reject these changes alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่อปฏิเสธการเปลี่ยนแปลงเหล่านี้เท่านั้น…",
  "Changes to decide": "การเปลี่ยนแปลงที่รอการตัดสินใจ",
  "An agent asked for each of these, and it waits for you. Decide only what you mean: deciding signs you in again, and your sign-in decides once.":
    "เอเจนต์ขอการเปลี่ยนแปลงแต่ละรายการเหล่านี้ และรายการเหล่านี้รอคุณอยู่ ตัดสินใจเฉพาะสิ่งที่คุณตั้งใจ: การตัดสินใจจะให้คุณลงชื่อเข้าใช้อีกครั้ง และการลงชื่อเข้าใช้นั้นใช้ตัดสินใจได้ครั้งเดียว",
  "Nothing waits for your decision.": "ไม่มีสิ่งใดรอการตัดสินใจของคุณ",
  "Approve the ticked ones": "อนุมัติรายการที่เลือก",
  "Reject the ticked ones": "ปฏิเสธรายการที่เลือก",
  "Decided lately": "ตัดสินใจไปเมื่อเร็วๆ นี้",
  "{key}: you've decided it, and a5s acts on it within a minute.": "{key}: คุณตัดสินใจแล้ว และ a5s จะดำเนินการภายใน 1 นาที",
  "Look again": "ดูอีกครั้ง",

  // Grading samples: the grades' names on their buttons, while what's sent stays right, wrong or critical
  "Right": "ถูกต้อง",
  "Wrong": "ผิด",
  "Critical": "ร้ายแรง",
  "Graded right.": "ให้คะแนนว่าถูกต้องแล้ว",
  "Graded wrong.": "ให้คะแนนว่าผิดแล้ว",
  "Graded critical.": "ให้คะแนนว่าร้ายแรงแล้ว",
  "Graded {grade}.": "ให้คะแนนว่า {grade} แล้ว",
  "Graded {samples}.": "ให้คะแนน {samples}แล้ว",
  "approved": "อนุมัติแล้ว",
  "rejected": "ปฏิเสธแล้ว",
  "made at level 2": "ทำเองที่ระดับ 2",
  "The {agent} asked": "{agent} ขออนุมัติไว้",
  "The {agent} acted on its own": "{agent} ดำเนินการเอง",
  "{action} in {part} · sampled {day}": "{action} ใน {part} · สุ่มเมื่อ {day}",
  "What code flagged": "สิ่งที่โค้ดตั้งข้อสังเกต",
  "What they asked": "สิ่งที่ผู้ขอบอกไว้",
  "Your grade for: {what}": "การให้คะแนนของคุณสำหรับ: {what}",
  "{n} chosen: send them when you're ready.": "เลือกไว้ {n} รายการ: ส่งได้เมื่อคุณพร้อม",
  "Choose a grade for a sample first.": "เลือกการให้คะแนนให้ตัวอย่างก่อน",
  "A sample you chose no longer waits for a grade: it lapsed, or someone else graded it, so it's out of your grades.":
    "ตัวอย่างที่คุณเลือกไว้ไม่รอการให้คะแนนแล้ว เพราะหมดเวลาหรือมีผู้อื่นให้คะแนนไปแล้ว จึงนำออกจากการให้คะแนนของคุณ",
  "{samples} you chose no longer wait for a grade: they lapsed, or someone else graded them, so they're out of your grades.":
    "{samples}ที่คุณเลือกไว้ไม่รอการให้คะแนนแล้ว เพราะหมดเวลาหรือมีผู้อื่นให้คะแนนไปแล้ว จึงนำออกจากการให้คะแนนของคุณ",
  "Signing you in again, to give this grade alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่อส่งการให้คะแนนนี้เท่านั้น…",
  "Signing you in again, to give these grades alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่อส่งการให้คะแนนเหล่านี้เท่านั้น…",
  "Nothing waits for you to grade.": "ไม่มีสิ่งใดรอให้คุณให้คะแนน",
  "Nothing else waits for you to grade.": "ไม่มีสิ่งอื่นรอให้คุณให้คะแนน",
  "Agents' work to grade": "งานของเอเจนต์ที่รอการให้คะแนน",
  "Each is a change an agent asked for or made. Grade it right if it's what a careful colleague would have done with what they knew, wrong if not, and critical if it could have done real harm. Your grades decide whether agents may act on their own.":
    "แต่ละรายการคือการเปลี่ยนแปลงที่เอเจนต์ขอหรือทำไปแล้ว ให้คะแนนว่าถูกต้องหากเป็นสิ่งที่เพื่อนร่วมงานที่รอบคอบจะทำด้วยข้อมูลที่มีในตอนนั้น ผิดหากไม่ใช่ และร้ายแรงหากอาจก่อความเสียหายจริง การให้คะแนนของคุณเป็นตัวตัดสินว่าเอเจนต์จะทำงานเองได้หรือไม่",
  "Send the grades you chose": "ส่งการให้คะแนนที่คุณเลือก",
  "You sign in again to send them, so your sign-in covers exactly these grades.":
    "คุณต้องลงชื่อเข้าใช้อีกครั้งเพื่อส่ง การลงชื่อเข้าใช้นั้นจึงครอบคลุมเฉพาะการให้คะแนนเหล่านี้",

  // Approving a version of the settings
  "It goes in force once nothing more is missing: {needs}.": "จะมีผลบังคับใช้เมื่อไม่มีสิ่งใดขาดแล้ว: {needs}",
  "a5s puts it in force within a minute, as it needs nothing more.": "a5s จะให้มีผลบังคับใช้ภายใน 1 นาที เพราะไม่ต้องการสิ่งใดเพิ่มแล้ว",
  "in force": "มีผลบังคับใช้",
  "It's been approved and applied already.": "เวอร์ชันนี้ได้รับการอนุมัติและนำไปใช้แล้ว",
  "superseded": "ถูกแทนที่แล้ว",
  "A newer version is in force, so this one can't be approved any more.": "มีเวอร์ชันที่ใหม่กว่ามีผลบังคับใช้อยู่ จึงอนุมัติเวอร์ชันนี้ไม่ได้อีกแล้ว",
  "refused": "ถูกปฏิเสธ",
  "a5s couldn't apply it: {why}": "a5s นำไปใช้ไม่ได้: {why}",
  "you approved it": "คุณอนุมัติแล้ว",
  "You've approved it.": "คุณอนุมัติแล้ว",
  "waiting for you": "รอคุณอยู่",
  "You approved version {serial}.": "คุณอนุมัติเวอร์ชัน {serial} แล้ว",
  "Signing you in again, to approve this version alone…": "กำลังลงชื่อเข้าใช้อีกครั้ง เพื่ออนุมัติเวอร์ชันนี้เท่านั้น…",
  "Settings to approve": "การตั้งค่าที่รอการอนุมัติ",
  "A version of the settings waits for your approval. Read what it changes, and all of it; approving signs you in again, for this version alone.":
    "การตั้งค่าเวอร์ชันหนึ่งรอการอนุมัติจากคุณ อ่านสิ่งที่เปลี่ยนแปลงและเนื้อหาทั้งหมด การอนุมัติจะให้คุณลงชื่อเข้าใช้อีกครั้งสำหรับเวอร์ชันนี้เท่านั้น",
  "This link doesn't name a version of the settings. Open the one on your card.":
    "ลิงก์นี้ไม่ได้ระบุเวอร์ชันของการตั้งค่า เปิดลิงก์บนการ์ดของคุณแทน",
  "{who} asked for it": "{who} เป็นผู้ขอ",
  "proposed {when}": "เสนอเมื่อ {when}",
  "Proposed {when}": "เสนอเมื่อ {when}",
  "Version {serial} of the settings": "การตั้งค่าเวอร์ชัน {serial}",
  "What it sets, with nothing in force yet": "สิ่งที่เวอร์ชันนี้กำหนด ขณะที่ยังไม่มีเวอร์ชันใดมีผลบังคับใช้",
  "What it changes from version {serial}, the one in force": "สิ่งที่เปลี่ยนจากเวอร์ชัน {serial} ซึ่งมีผลบังคับใช้อยู่",
  "widens what agents do": "ขยายสิ่งที่เอเจนต์ทำได้",
  "Approved so far by": "อนุมัติแล้วโดย",
  "nobody yet": "ยังไม่มีใคร",
  "What's missing": "สิ่งที่ยังขาด",
  "The whole version, as it would be": "ทั้งเวอร์ชัน ตามที่จะมีผลบังคับใช้",
  "Approve version {serial}": "อนุมัติเวอร์ชัน {serial}",
  "Approve only if you mean these changes. Approving signs you in again, for this version alone, and only once.":
    "อนุมัติเฉพาะเมื่อคุณตั้งใจให้เกิดการเปลี่ยนแปลงเหล่านี้ การอนุมัติจะให้คุณลงชื่อเข้าใช้อีกครั้งสำหรับเวอร์ชันนี้เท่านั้น และได้เพียงครั้งเดียว",

  // The data protection officer's requests: export and erase as the officer's choice, while what's sent stays the action
  "export": "ส่งออก",
  "erase": "ลบ",
  "You asked to {action} all a5s keeps about {whom}.": "คุณขอ{action}ข้อมูลทั้งหมดที่ a5s เก็บเกี่ยวกับ {whom} แล้ว",
  "Someone from the team that runs a5s carries it out, once, within {lasts}: {command}":
    "สมาชิกในทีมที่ดูแล a5s จะดำเนินการให้ครั้งเดียวภายใน {lasts}: {command}",
  "a5s didn't take your request: {why}": "a5s ไม่รับคำขอของคุณ: {why}",
  "Name the person: by their id in the directory, an archive's name, or, for someone outside the directory, such as a customer who wrote to a shared mailbox, their address.":
    "ระบุบุคคล: ด้วยรหัสในไดเรกทอรี ชื่อของข้อมูลที่เก็บถาวร หรือสำหรับบุคคลภายนอกไดเรกทอรี เช่น ลูกค้าที่เขียนถึงกล่องจดหมายที่ใช้ร่วมกัน ให้ใช้ที่อยู่อีเมลของบุคคลนั้น",
  "Type their id again, the same, to confirm it: an erasure can't be undone.":
    "พิมพ์รหัสของบุคคลนั้นอีกครั้งให้ตรงกันเพื่อยืนยัน เพราะการลบย้อนกลับไม่ได้",
  "A request for someone's data": "คำขอเกี่ยวกับข้อมูลของบุคคล",
  "Ask to export, or erase, all a5s keeps about someone, at their request. You sign in afresh for that request alone, and someone from the team that runs a5s carries it out.":
    "ขอส่งออกหรือลบข้อมูลทั้งหมดที่ a5s เก็บเกี่ยวกับบุคคลหนึ่ง ตามคำขอของบุคคลนั้น คุณลงชื่อเข้าใช้ใหม่สำหรับคำขอนั้นเท่านั้น และสมาชิกในทีมที่ดูแล a5s จะเป็นผู้ดำเนินการ",
  "Ask about someone else": "ส่งคำขอสำหรับบุคคลอื่น",
  "Ask to": "ขอ",
  "all a5s keeps about": "ข้อมูลทั้งหมดที่ a5s เก็บเกี่ยวกับ",
  "an id, an archive's name, or an address": "รหัส ชื่อของข้อมูลที่เก็บถาวร หรือที่อยู่อีเมล",
  "Their id again, since an erasure can't be undone:": "รหัสของบุคคลนั้นอีกครั้ง เพราะการลบย้อนกลับไม่ได้:",
  "You sign in afresh, for this request alone. Someone from the team that runs a5s then carries it out, once, within ten minutes: your sign-in does nothing else.":
    "คุณลงชื่อเข้าใช้ใหม่สำหรับคำขอนี้เท่านั้น จากนั้นสมาชิกในทีมที่ดูแล a5s จะดำเนินการให้ครั้งเดียวภายใน 10 นาที การลงชื่อเข้าใช้ของคุณไม่ได้ใช้ทำสิ่งอื่น",
  "Sign in and ask": "ลงชื่อเข้าใช้และส่งคำขอ",

  // The audit trail (the ledger's own kinds and decisions, allow, deny and record, stay as it says them)
  "Reading the ledger…": "กำลังอ่านเลดเจอร์…",
  "No entries in that period, as asked.": "ไม่มีรายการในช่วงเวลานั้นตามที่ค้นหา",
  "Exported {n} entries. Check them yourself, against the ledger's locked copies, with: a5s audit verify a5s-audit.jsonl":
    "ส่งออกแล้ว {n} รายการ ตรวจสอบเองเทียบกับสำเนาที่ล็อกไว้ของเลดเจอร์ได้ด้วยคำสั่ง: a5s audit verify a5s-audit.jsonl",
  "Audit trail": "บันทึกการตรวจสอบ",
  // Whether the trail checks out (round 15, E8)
  "Whether the trail checks out": "บันทึกการตรวจสอบถูกต้องหรือไม่",
  "It checks out": "ถูกต้อง",
  "It doesn't check out": "ไม่ถูกต้อง",
  "Not checked yet": "ยังไม่ได้ตรวจ",
  "a5s keeps no locked copies of the ledger here, so nothing shows whether anyone rewrote it.":
    "ที่นี่ a5s ไม่ได้เก็บสำเนาที่ล็อกไว้ของเลดเจอร์ จึงไม่มีสิ่งใดแสดงว่ามีใครเขียนทับเลดเจอร์หรือไม่",
  "What a5s found wrong with the ledger and its locked copies:":
    "สิ่งที่ a5s พบว่าผิดปกติในเลดเจอร์และสำเนาที่ล็อกไว้:",
  "Tell assurance and the team that runs a5s: until they know why, take what this page shows as unproven.":
    "แจ้งผู้ตรวจรับรองและทีมที่ดูแล a5s จนกว่าจะทราบสาเหตุ ให้ถือว่าสิ่งที่หน้านี้แสดงยังพิสูจน์ไม่ได้",
  "Every entry follows the one before it, and the ledger matched its locked copies when a5s last checked it whole, {when}.":
    "ทุกรายการต่อเนื่องจากรายการก่อนหน้า และเลดเจอร์ตรงกับสำเนาที่ล็อกไว้เมื่อ a5s ตรวจทั้งหมดครั้งล่าสุด {when}",
  "{n} ago": "เมื่อ {n} ที่แล้ว",
  "just now": "เมื่อสักครู่",
  "Not checked lately": "ไม่ได้ตรวจมาสักพัก",
  "a5s last checked the whole ledger against its locked copies {when}, though it checks once a day: its copier may have stopped. Tell the team that runs a5s.":
    "a5s ตรวจเลดเจอร์ทั้งหมดเทียบกับสำเนาที่ล็อกไว้ครั้งล่าสุด{when} ทั้งที่ตรวจวันละครั้ง ตัวคัดลอกอาจหยุดทำงาน โปรดแจ้งทีมที่ดูแล a5s",
  "Those entries have waited longer than they should: tell the team that runs a5s.":
    "รายการเหล่านั้นรอนานกว่าที่ควร โปรดแจ้งทีมที่ดูแล a5s",
  "a5s checks the whole ledger against its locked copies when its copier starts, and once a day: it hasn't yet.":
    "a5s ตรวจเลดเจอร์ทั้งหมดเทียบกับสำเนาที่ล็อกไว้เมื่อตัวคัดลอกเริ่มทำงาน และวันละครั้ง แต่ยังไม่ได้ตรวจ",
  "Nothing is copied yet.": "ยังไม่มีการคัดลอก",
  "The locked copies hold every entry through #{seq}, copied {when}.":
    "สำเนาที่ล็อกไว้มีทุกรายการจนถึง #{seq} คัดลอก{when}",
  "Entries written since aren't copied yet: what people decided is copied within a minute, and the rest within 15 minutes. Until they are, someone with the database's own powers could rewrite them unseen.":
    "รายการที่เขียนหลังจากนั้นยังไม่ได้คัดลอก สิ่งที่ผู้คนตัดสินใจจะถูกคัดลอกภายในหนึ่งนาที และรายการอื่นภายใน 15 นาที จนกว่าจะคัดลอกแล้ว ผู้ที่มีสิทธิ์ระดับฐานข้อมูลอาจเขียนทับได้โดยไม่มีใครเห็น",
  "The copier's last try failed: it tries again each minute.":
    "ตัวคัดลอกพยายามครั้งล่าสุดไม่สำเร็จ และจะลองใหม่ทุกนาที",
  "doesn't check out": "ตรวจแล้วไม่ถูกต้อง",
  "not copied yet": "ยังไม่ได้คัดลอก",
  "The ledger, as an auditor reads it: everything a5s did and decided, in the order it happened, and never what anyone said, which it keeps by hash alone. Whoever approved, decided, signed or read the trail shows as themselves. Each search here is itself in the ledger.":
    "เลดเจอร์ในแบบที่ผู้ตรวจสอบอ่าน: ทุกสิ่งที่ a5s ทำและตัดสินใจ ตามลำดับที่เกิดขึ้น โดยไม่มีสิ่งที่ใครพูด ซึ่งเก็บไว้เป็นค่าแฮชเท่านั้น ผู้ที่อนุมัติ ตัดสินใจ ลงนาม หรืออ่านบันทึกนี้จะแสดงเป็นตัวตนจริง การค้นหาแต่ละครั้งที่นี่ก็อยู่ในเลดเจอร์ด้วย",
  "Whom agents acted for shows by name, as the data protection officer agreed.":
    "ผู้ที่เอเจนต์ทำงานแทนจะแสดงด้วยชื่อ ตามที่เจ้าหน้าที่คุ้มครองข้อมูลตกลงไว้",
  "Whom agents acted for, told or asked about shows as a stand-in, the same one each time, until the data protection officer agrees to names.":
    "ผู้ที่เอเจนต์ทำงานแทน แจ้ง หรือสอบถามถึง จะแสดงเป็นนามแฝงที่เหมือนเดิมทุกครั้ง จนกว่าเจ้าหน้าที่คุ้มครองข้อมูลจะตกลงให้แสดงชื่อ",
  "Sign in again, with a second factor": "ลงชื่อเข้าใช้อีกครั้งด้วยปัจจัยที่สอง",
  "Find entries": "ค้นหารายการ",
  "From": "ตั้งแต่",
  "to before": "ถึงก่อน",
  "in UTC": "ตามเวลา UTC",
  "Kind": "ประเภท",
  "any": "ทั้งหมด",
  "action": "การกระทำ",
  "decision": "การตัดสินใจ",
  "acting for": "ทำแทน",
  "by": "โดย",
  "Find": "ค้นหา",
  "Who holds each role, and who did what": "ใครมีบทบาทใด และใครทำอะไร",
  "Export the period": "ส่งออกช่วงเวลานี้",
  "By": "โดย",
  "Later entries": "รายการถัดไป",
  "Who holds each role now": "ใครมีบทบาทใดอยู่ในตอนนี้",
  "nobody": "ไม่มีใคร",
  "What was done in the period": "สิ่งที่ทำในช่วงเวลานี้",
  "when, unknown": "ไม่ทราบเวลา",
  "Nothing was done in the period.": "ไม่มีการดำเนินการใดในช่วงเวลานี้",

  // Administration
  "Administration": "การดูแลระบบ",
  "Who holds each role in a5s, and what gave it them: the directory, or a group in your identity provider. Then what waits for whom, what nobody answers for, and what was done lately. This page only shows: to change anything, use the settings, or `a5s release` for a release.":
    "ใครมีบทบาทใดใน a5s และได้มาจากที่ใด: ไดเรกทอรี หรือกลุ่มในผู้ให้บริการยืนยันตัวตนของคุณ จากนั้นคือสิ่งที่รอใครอยู่ สิ่งที่ไม่มีใครรับผิดชอบ และสิ่งที่ทำไปเมื่อเร็วๆ นี้ หน้านี้แสดงข้อมูลเท่านั้น หากต้องการเปลี่ยนแปลงสิ่งใด ให้ใช้การตั้งค่า หรือ `a5s release` สำหรับรีลีส",
  "Who holds each role": "ใครมีบทบาทใด",
  "Held by": "ผู้ที่มีบทบาทนี้",
  "Groups that give roles": "กลุ่มที่ให้บทบาท",
  "Sign-ins show their groups in the {claim} claim. A role a group gives counts from someone's latest sign-in.":
    "การลงชื่อเข้าใช้แสดงกลุ่มไว้ใน claim {claim} บทบาทที่กลุ่มให้จะนับตั้งแต่การลงชื่อเข้าใช้ล่าสุดของแต่ละคน",
  "This deployment reads no groups from sign-ins, so the directory alone gives roles.":
    "ระบบที่ติดตั้งนี้ไม่ได้อ่านกลุ่มจากการลงชื่อเข้าใช้ จึงมีเพียงไดเรกทอรีที่ให้บทบาท",
  "None: the settings in force give no group a role.": "ไม่มี: การตั้งค่าที่มีผลบังคับใช้ไม่ได้ให้บทบาทแก่กลุ่มใด",
  "{group}: {roles}, for {people} as their latest sign-ins showed": "{group}: {roles} สำหรับ {people} ตามที่การลงชื่อเข้าใช้ล่าสุดแสดง",
  "What waits for whom": "สิ่งที่รอใครอยู่",
  "Nothing waits.": "ไม่มีสิ่งใดรออยู่",
  "Settings, version {serial}: {needs}": "การตั้งค่า เวอร์ชัน {serial}: {needs}",
  "Settings, version {serial}: approved, for a5s to apply": "การตั้งค่า เวอร์ชัน {serial}: อนุมัติแล้ว รอ a5s นำไปใช้",
  "The release: {problem}": "รีลีส: {problem}",
  "{changes} in {part}, for {deciders} to decide": "{changes} ใน {part} ให้ {deciders} ตัดสินใจ",
  "{changes} in {part}, for nobody to decide": "{changes} ใน {part} ซึ่งไม่มีใครตัดสินใจได้",
  "Nobody answers for": "สิ่งที่ไม่มีใครรับผิดชอบ",
  "Everything has someone who answers for it.": "ทุกอย่างมีผู้รับผิดชอบแล้ว",
  "The {agent}: {what}. To do: {do}.": "{agent}: {what} สิ่งที่ต้องทำ: {do}",
  "{instance}, of the {agent}: {what}. To do: {do}.": "{instance} ของ {agent}: {what} สิ่งที่ต้องทำ: {do}",
  "{part}: {what}. To do: {do}.": "{part}: {what} สิ่งที่ต้องทำ: {do}",
  "The latest acts, over the last {days} days": "การดำเนินการล่าสุดในช่วง {days} วันที่ผ่านมา",
  "Nothing was done.": "ไม่มีการดำเนินการใด",

  // The pieces those pages share (design/): asking before what can't be undone, a value traced to its
  // record, a decision's card, an agent's facts, its ladder of autonomy, and the way from a draft
  "Keep it": "เก็บไว้",
  "(where it comes from)": "(แหล่งที่มา)",
  "Where it comes from": "แหล่งที่มา",
  "Why:": "เหตุผล:",
  "You approved it.": "คุณอนุมัติแล้ว",
  "You declined it.": "คุณปฏิเสธแล้ว",
  "Decline": "ปฏิเสธ",
  "Your decision is signed and kept in the ledger.": "การตัดสินใจของคุณได้รับการลงนามและเก็บไว้ในเลดเจอร์",
  "{name}'s facts": "ข้อมูลของ {name}",
  "Agent facts": "ข้อมูลเอเจนต์",
  "Suggests": "เสนอแนะ",
  "Reads and drafts. A person does the rest.": "อ่านและร่างให้ คนทำส่วนที่เหลือ",
  "Asks": "ขออนุมัติ",
  "Changes wait for a person's yes.": "การเปลี่ยนแปลงต้องรอให้คนตอบตกลง",
  "Acts": "ลงมือทำ",
  "One type of change on its own, within limits, sampled and graded.":
    "ทำการเปลี่ยนแปลงประเภทเดียวได้เองภายในขอบเขต โดยมีการสุ่มตัวอย่างและให้คะแนน",
  "Autonomy": "ความเป็นอิสระ",
  "level {n} · now": "ระดับ {n} · ตอนนี้",
  "level {n} · not in its release": "ระดับ {n} · ไม่อยู่ในรีลีส",
  "level {n}": "ระดับ {n}",
  "{what} toward level {level}: {graded} of {needed} graded samples. The part's owner decides.":
    "{what} สู่ระดับ {level}: ให้คะแนนตัวอย่างแล้ว {graded} จาก {needed} ตัวอย่าง เจ้าของส่วนงานเป็นผู้ตัดสินใจ",
  "{what} toward level {level}": "{what} สู่ระดับ {level}",
  ", done": " เสร็จแล้ว",
  ", to do now": " ต้องทำตอนนี้",
  "From a draft to an agent at work": "จากฉบับร่างสู่เอเจนต์ที่ทำงานจริง",
  // A change to undo (Undo.tsx)
  "A change an agent made": "การเปลี่ยนแปลงที่เอเจนต์ทำ",
  "A change the {agent} made": "การเปลี่ยนแปลงที่ {agent} ทำ",
  "Whoever it was for, and whoever decides changes like it in its record's part, may undo it for a while after it's made. Undoing it counts against the agent's accuracy, as a wrong grade of its work.": "ผู้ที่ได้รับการเปลี่ยนแปลงนี้ และผู้ตัดสินใจการเปลี่ยนแปลงแบบนี้ในส่วนงานของระเบียน ยกเลิกได้ภายในช่วงเวลาหนึ่งหลังทำ การยกเลิกจะนับเป็นความแม่นยำที่ลดลงของเอเจนต์ เป็นการให้คะแนนว่าผิด",
  "Made": "ทำเมื่อ",
  "Can be undone until": "ยกเลิกได้จนถึง",
  "Undone": "ยกเลิกแล้ว",
  "by {person}": "โดย {person}",
  "a5s is undoing it, as {person} asked: within a minute, once it has checked that sign-in again.": "a5s กำลังยกเลิกตามที่ {person} ขอ ภายในหนึ่งนาที เมื่อตรวจสอบการลงชื่อเข้าใช้นั้นอีกครั้งแล้ว",
  "a5s didn't undo it: {why}": "a5s ไม่ได้ยกเลิก: {why}",
  "You asked to undo it: a5s does it within a minute.": "คุณขอยกเลิกแล้ว a5s จะยกเลิกภายในหนึ่งนาที",
  "Undo it": "ยกเลิกการเปลี่ยนแปลง",
  "Undo this change to {record}?": "ยกเลิกการเปลี่ยนแปลงนี้ของ {record} หรือไม่",
  "a5s puts it back as it was before, so long as nobody has changed it since. It counts against the {agent}'s accuracy, as a wrong grade of its work. You'll sign in again, for this alone.": "a5s จะคืนค่าเป็นเหมือนก่อนหน้า หากยังไม่มีใครเปลี่ยนแปลงหลังจากนั้น และนับเป็นความแม่นยำที่ลดลงของ {agent} เป็นการให้คะแนนว่าผิด คุณจะลงชื่อเข้าใช้อีกครั้งเพื่อการนี้เท่านั้น",
  "You can't undo it: {why}.": "คุณยกเลิกไม่ได้: {why}",
  // New versions answering beside those at work, for graders to compare (core/shadows.py)
  "New versions, answering beside": "เวอร์ชันใหม่ที่ตอบคู่ขนาน",
  "A new version of an agent answers what people ask an instance, beside it, sending and changing nothing. Compare its answer with the one sent, never knowing whose it was, and say which is better: its owners decide from your grades whether to put it to work.": "เวอร์ชันใหม่ของเอเจนต์ตอบสิ่งที่ผู้คนถามอินสแตนซ์คู่ขนานไปกับอินสแตนซ์นั้น โดยไม่ส่งและไม่เปลี่ยนแปลงสิ่งใด เทียบคำตอบของเวอร์ชันใหม่กับคำตอบที่ส่งไปแล้ว โดยไม่รู้ว่าเป็นของใคร แล้วบอกว่าคำตอบใดดีกว่า เจ้าของจะตัดสินจากคะแนนของคุณว่าจะนำเวอร์ชันใหม่ไปใช้งานหรือไม่",
  "Nothing waits for you to compare now.": "ตอนนี้ไม่มีสิ่งใดรอให้คุณเทียบ",
  "The {agent}, and the {shadow} beside it": "{agent} และ {shadow} ที่ตอบคู่ขนาน",
  "The answer sent": "คำตอบที่ส่งไปแล้ว",
  "The new version's answer, which went nowhere": "คำตอบของเวอร์ชันใหม่ ซึ่งไม่ได้ส่งไปที่ใด",
  "Grade the new version's answer": "ให้คะแนนคำตอบของเวอร์ชันใหม่",
  "Better": "ดีกว่า",
  "As good": "ดีพอกัน",
  "Worse": "แย่กว่า",
  "Graded: thank you.": "ให้คะแนนแล้ว ขอบคุณ",
  "How each new version does": "ผลของเวอร์ชันใหม่แต่ละเวอร์ชัน",
  "Counts of graders' grades, and its judge's apart, never what was said.": "จำนวนคะแนนจากผู้ให้คะแนน และของผู้ตัดสินแยกต่างหาก โดยไม่แสดงสิ่งที่พูด",
  "Answering beside {instance}": "ตอบคู่ขนานกับ {instance}",
  "{n} so far": "{n} จนถึงตอนนี้",
  "a shadow, answering beside another": "เวอร์ชันทดลองที่ตอบคู่ขนานกับอีกอินสแตนซ์",
  "Graded: {better} better, {same} as good, {worse} worse, {wrong} wrong": "คะแนน: ดีกว่า {better} ดีพอกัน {same} แย่กว่า {worse} ผิด {wrong}",
  "Its judge: {better} better, {same} as good, {worse} worse, {wrong} wrong": "ผู้ตัดสิน: ดีกว่า {better} ดีพอกัน {same} แย่กว่า {worse} ผิด {wrong}",
};
