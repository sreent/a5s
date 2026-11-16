// The studio's words in Thai (i18n.ts): each as its pages write it in English, and in Thai, with
// the same {name}s, kept a file for each part of the studio in th/. Words a page has that aren't
// here stay in English. tests/test_languages.py holds the catalogue to every t() the studio's pages
// say, so none is left out, and none is kept that no page says.
//
// The same thing is called the same everywhere: agent เอเจนต์, instance อินสแตนซ์, run การทำงาน
// (counted ครั้ง), part ส่วนงาน, settings การตั้งค่า, version เวอร์ชัน, release รีลีส, draft ฉบับร่าง,
// tool เครื่องมือ, record ระเบียน, owner เจ้าของ, deputy ผู้แทน, approver ผู้อนุมัติ, decision
// การตัดสินใจ, grade การให้คะแนน (right ถูกต้อง, wrong ผิด, critical ร้ายแรง), sample ตัวอย่าง, level
// ระดับ, cap เพดาน, budget งบประมาณ, model โมเดล, task งาน, notebook สมุดบันทึก, ledger เลดเจอร์,
// sign in ลงชื่อเข้าใช้, studio สตูดิโอ, map แผนผัง, sandbox แซนด์บ็อกซ์, test case กรณีทดสอบ, judge
// ผู้ประเมิน, suspend ระงับ, resume กลับมาทำงานต่อ, data protection officer เจ้าหน้าที่คุ้มครองข้อมูล,
// served ให้บริการ, watch ติดตาม. Ids, such as an agent's or a record's key, stay as they are.

import { BUILD } from "./th/build";
import { DECIDE } from "./th/decide";
import { FRAME } from "./th/frame";
import { WATCH } from "./th/watch";

export const TH: Record<string, string> = { ...FRAME, ...WATCH, ...DECIDE, ...BUILD };

// Nouns counted by plural() (ui.tsx), which Thai doesn't change for many: each word after its
// number, as a count of them is written in Thai
export const TH_NOUNS: Record<string, string> = {
  message: "ข้อความ", run: "ครั้ง", person: "คน", answer: "คำตอบ", sample: "ตัวอย่าง",
  change: "รายการ", instance: "อินสแตนซ์", agent: "เอเจนต์", tool: "เครื่องมือ", day: "วัน",
  note: "บันทึก", task: "งาน", more: "รายการ", token: "โทเค็น", file: "ไฟล์", record: "ระเบียน",
  part: "ส่วนงาน", version: "เวอร์ชัน", case: "กรณี", step: "ขั้นตอน", call: "ครั้ง",
  minute: "นาที", hour: "ชั่วโมง", week: "สัปดาห์", month: "เดือน",
};
