// The studio's words in Thai for a new agent, a draft and its designer, trying it, publishing it, and the settings' forms (i18n.ts, th.ts).

export const BUILD: Record<string, string> = {
  // A new agent
  "Start from one of the agents a5s ships. It's a draft, yours alone, until you publish it as a pull request: nothing runs it, and its first release needs the release approver.":
    "เริ่มจากเอเจนต์ตัวหนึ่งที่มากับ a5s เอเจนต์นี้จะเป็นฉบับร่างของคุณคนเดียวจนกว่าคุณจะเผยแพร่เป็น pull request ระหว่างนั้นไม่มีสิ่งใดเรียกใช้ และรีลีสแรกต้องผ่านผู้อนุมัติรีลีส",
  "Its name": "ชื่อ",
  "Lower case letters and digits, with single hyphens between": "ตัวอักษรพิมพ์เล็กและตัวเลข คั่นด้วยขีดกลางทีละตัว",
  "Start from": "เริ่มจาก",
  "{n} tools · {model}": "{n} เครื่องมือ · {model}",
  "needs {tools}, which this scenario hasn't got": "ต้องใช้ {tools} ซึ่งซีนาริโอนี้ไม่มี",
  "Making it…": "กำลังสร้าง…",
  "Make the draft": "สร้างฉบับร่าง",
  "Or describe it": "หรืออธิบายเอเจนต์",
  "Describing it needs the sandbox, which drafts it there: {problem}":
    "การอธิบายต้องใช้แซนด์บ็อกซ์ ซึ่งเป็นที่ร่างเอเจนต์: {problem}",
  "Say what it's for, in your own words. The sandbox's model proposes what it needs of what this scenario offers, and a5s gives it the least of that, never level 2, each with the reason, for you to check and change by hand. What you write goes to the model you choose, as what's said in the sandbox does.":
    "บอกด้วยคำพูดของคุณว่าเอเจนต์มีไว้ทำอะไร โมเดลของแซนด์บ็อกซ์จะเสนอสิ่งที่เอเจนต์ต้องใช้จากสิ่งที่ซีนาริโอนี้มีให้ และ a5s จะให้เท่าที่จำเป็นน้อยที่สุด ไม่ให้ระดับ 2 เด็ดขาด พร้อมเหตุผลของแต่ละรายการ ให้คุณตรวจสอบและแก้ไขเอง สิ่งที่คุณเขียนจะส่งไปยังโมเดลที่คุณเลือก เช่นเดียวกับสิ่งที่พูดในแซนด์บ็อกซ์",
  "What it's for, and for whom": "มีไว้ทำอะไร และให้ใคร",
  "Tracks each new joiner's equipment and access requests in the ITSM against their start date, and answers their questions before day one.":
    "ติดตามคำขออุปกรณ์และสิทธิ์เข้าถึงของพนักงานใหม่แต่ละคนใน ITSM เทียบกับวันเริ่มงาน และตอบคำถามของพวกเขาก่อนวันแรก",
  "On the model": "ใช้โมเดล",
  "the stand-in, which thinks nothing": "โมเดลจำลอง ซึ่งไม่ได้คิดอะไรเลย",
  "Drafting it…": "กำลังร่าง…",
  "Draft it from my words": "ร่างจากคำอธิบายของฉัน",

  // A draft, on the workbench: its views, what stops its release, where it stands, and handing it over
  "Design": "ออกแบบ",
  "Instructions": "คำสั่ง",
  "Try it": "ทดลอง",
  "Files": "ไฟล์",
  "Its files": "ไฟล์ของฉบับร่าง",
  "a5s pins its tools as the scenario has them each time it's kept, as `a5s pin` does.":
    "a5s ตรึงเครื่องมือไว้ตามที่ซีนาริโอมีทุกครั้งที่บันทึก เช่นเดียวกับ `a5s pin`",
  "Drafted from your words": "ร่างจากคำอธิบายของคุณ",
  "On {model}, from:": "ร่างโดย {model} จากข้อความ:",
  "the sandbox's stand-in, which thinks nothing": "โมเดลจำลองของแซนด์บ็อกซ์ ซึ่งไม่ได้คิดอะไรเลย",
  "It was given the least it needs of what the scenario offers, each for the reason the model gave. Check each: take away what it doesn't need, and add by hand what it does.":
    "เอเจนต์ได้รับเท่าที่จำเป็นน้อยที่สุดจากสิ่งที่ซีนาริโอมีให้ แต่ละรายการตามเหตุผลที่โมเดลให้ไว้ ตรวจสอบทุกรายการ: เอาสิ่งที่ไม่จำเป็นออก และเพิ่มสิ่งที่จำเป็นเอง",
  "given": "ได้รับ",
  "left out": "ไม่ได้ให้",
  "What stops its release": "สิ่งที่ทำให้ยังรีลีสไม่ได้",
  "passed": "ผ่าน",
  "Nothing would stop its release here, by the checks": "ไม่มีสิ่งใดทำให้รีลีสที่นี่ไม่ได้ ตามการตรวจสอบที่",
  "makes.": "ทำ",
  "draft": "ฉบับร่าง",
  "read only": "อ่านอย่างเดียว",
  "Make a copy of your own": "ทำสำเนาเป็นของคุณเอง",
  "{author}'s draft, from {release}, kept {when}. You may author the {agent} too, so you may read it: copy it into a draft of your own to change it.":
    "ฉบับร่างของ {author} จาก {release} บันทึกเมื่อ {when} คุณเขียน {agent} ได้เช่นกัน จึงอ่านฉบับร่างนี้ได้: ทำสำเนาเป็นฉบับร่างของคุณเองเพื่อแก้ไข",
  "Its map shows once its definition loads.": "แผนผังจะแสดงเมื่อโหลดนิยามเสร็จ",
  "{name} handed it over {when}": "{name} ส่งต่อมาเมื่อ {when}",
  "it copies a draft {name} wrote": "คัดลอกมาจากฉบับร่างที่ {name} เขียน",
  "Before you, {went}.": "ก่อนถึงคุณ {went}",
  "; then ": " จากนั้น ",
  "Hand it over": "ส่งต่อ",
  "Nobody else may take it: they may author its agent, and have no draft of it.":
    "ไม่มีใครรับต่อได้: ผู้รับต้องเขียนเอเจนต์นี้ได้ และยังไม่มีฉบับร่างของเอเจนต์นี้",
  "Hand it over to": "ส่งต่อให้",
  "Hand it over to them": "ส่งต่อให้คนนี้",
  "Shape and try it": "ปรับแต่งและทดลอง",
  "One thing stops its release.": "มี 1 ข้อที่ทำให้ยังรีลีสไม่ได้",
  "{n} things stop its release.": "มี {n} ข้อที่ทำให้ยังรีลีสไม่ได้",
  "Nothing stops its release, and {cases} kept from the sandbox.":
    "ไม่มีสิ่งใดทำให้รีลีสไม่ได้ และเก็บ {cases} จากแซนด์บ็อกซ์ไว้แล้ว",
  "Nothing stops its release. Try it in the sandbox, and keep what it should do as test cases.":
    "ไม่มีสิ่งใดทำให้รีลีสไม่ได้ ลองใช้ในแซนด์บ็อกซ์ แล้วเก็บสิ่งที่เอเจนต์ควรทำไว้เป็นกรณีทดสอบ",
  "Nothing stops its release. There's no sandbox here to try it in.":
    "ไม่มีสิ่งใดทำให้รีลีสไม่ได้ ที่นี่ไม่มีแซนด์บ็อกซ์ให้ทดลอง",
  "Nothing stops its release.": "ไม่มีสิ่งใดทำให้รีลีสไม่ได้",
  "Publish it": "เผยแพร่",
  "As a pull request, which a5s opens as you.": "เป็น pull request ที่ a5s เปิดในนามของคุณ",
  "As a pull request, which you open with the words a5s gives.":
    "เป็น pull request ที่คุณเปิดเองด้วยข้อความที่ a5s ให้",
  "Have its release signed": "ให้ลงนามรีลีส",
  "It's released here as it is, and a5s deployed it.": "รีลีสที่นี่ตามที่เป็นอยู่แล้ว และ a5s ปรับใช้แล้ว",
  "By {who}. a5s deploys it once they have.": "โดย {who} a5s จะปรับใช้เมื่อลงนามครบแล้ว",
  "whoever its release needs": "ผู้ที่รีลีสนี้ต้องการ",
  "An instance runs it.": "มีอินสแตนซ์ทำงานอยู่",
  "An instance in the settings, for a few people first, at level 0 or 1.":
    "อินสแตนซ์ในการตั้งค่า สำหรับคนไม่กี่คนก่อน ที่ระดับ 0 หรือ 1",
  "Watch it": "ติดตาม",
  "Its runs and how they end, on its page.": "การทำงานและผลลัพธ์ ในหน้าของเอเจนต์",
  "Watch it on its page": "ติดตามในหน้าของเอเจนต์",
  "Put it to work, from its page": "นำไปใช้งานจากหน้าของเอเจนต์",
  "See what stops its release": "ดูสิ่งที่ทำให้ยังรีลีสไม่ได้",
  "Open its pull request": "เปิด pull request",
  "Try it in the sandbox": "ทดลองในแซนด์บ็อกซ์",
  "Publish it without trying it": "เผยแพร่โดยไม่ทดลอง",
  "Where it stands": "สถานะ",
  "What you'd changed and a5s hadn't kept is back, and kept now.":
    "สิ่งที่คุณแก้ไขไว้ซึ่ง a5s ยังไม่ได้บันทึกกลับมาแล้ว และบันทึกแล้ว",
  "The draft of {agent} is gone.": "ลบฉบับร่างของ {agent} แล้ว",
  "the agent": "เอเจนต์",
  "Keeping…": "กำลังบันทึก…",
  "Kept": "บันทึกแล้ว",
  "A draft": "ฉบับร่าง",
  "No problems": "ไม่มีปัญหา",
  "The draft": "ฉบับร่าง",
  "Drop the draft": "ทิ้งฉบับร่าง",
  "Drop the draft of {agent}?": "ทิ้งฉบับร่างของ {agent} หรือไม่",
  "this agent": "เอเจนต์นี้",
  "Its files, its plan and what was tried on it go, and can't be had back. The agent itself, and any release of it, stay as they are.":
    "ไฟล์ แผน และสิ่งที่ทดลองไว้จะหายไป และกู้คืนไม่ได้ ตัวเอเจนต์และรีลีสใดๆ ของเอเจนต์ยังคงอยู่เหมือนเดิม",
  "From {release}, started {when}.": "จาก {release} เริ่มเมื่อ {when}",
  "Yours to change, and readable by the agent's other owners and authors: nothing runs it until it's published and its release signed.":
    "คุณแก้ไขได้ และเจ้าของกับผู้เขียนคนอื่นของเอเจนต์อ่านได้: ไม่มีสิ่งใดเรียกใช้จนกว่าจะเผยแพร่และรีลีสได้รับการลงนาม",
  "One thing stops its release": "มี 1 ข้อที่ทำให้ยังรีลีสไม่ได้",
  "{n} things stop its release": "มี {n} ข้อที่ทำให้ยังรีลีสไม่ได้",
  "{cases} kept": "เก็บ {cases} แล้ว",
  "Nothing stops its release": "ไม่มีสิ่งใดทำให้รีลีสไม่ได้",
  "What it's told at the start of each run, its AGENTS.md":
    "สิ่งที่เอเจนต์ได้รับแจ้งเมื่อเริ่มการทำงานแต่ละครั้ง คือ AGENTS.md",

  // The designer: the agent on its canvas or as a list, what to add, each part's panel, and what follows
  "Now it offers reminders, and keeps those people confirm.":
    "ตอนนี้เอเจนต์เสนอการเตือน และเก็บการเตือนที่ผู้คนยืนยันไว้",
  "It no longer offers reminders.": "เอเจนต์ไม่เสนอการเตือนอีกต่อไป",
  "Now it searches its conversation with the person it acts for, and corrects its summaries at their word.":
    "ตอนนี้เอเจนต์ค้นหาในบทสนทนากับผู้ที่เอเจนต์ทำงานแทน และแก้บทสรุปตามคำของผู้นั้น",
  "It no longer searches its conversation with the person it acts for.":
    "เอเจนต์ไม่ค้นหาในบทสนทนากับผู้ที่เอเจนต์ทำงานแทนอีกต่อไป",
  "Now it asks a5s's reader about documents from outside its run has read.":
    "ตอนนี้เอเจนต์ถามตัวอ่านของ a5s เกี่ยวกับเอกสารจากภายนอกที่การทำงานได้อ่านมา",
  "It no longer asks a5s's reader about documents from outside its run has read.":
    "เอเจนต์ไม่ถามตัวอ่านของ a5s เกี่ยวกับเอกสารจากภายนอกที่การทำงานได้อ่านมาอีกต่อไป",
  "Now it asks other agents questions, those the settings name.":
    "ตอนนี้เอเจนต์ถามคำถามเอเจนต์อื่นได้ เฉพาะที่การตั้งค่าระบุ",
  "It no longer asks other agents questions.": "เอเจนต์ไม่ถามคำถามเอเจนต์อื่นอีกต่อไป",
  "Now it notes what it learns from records, on its schedules, for its later runs.":
    "ตอนนี้เอเจนต์จดสิ่งที่เรียนรู้จากระเบียนตามกำหนดเวลา ไว้ใช้ในการทำงานครั้งต่อไป",
  "It no longer notes what it learns from records.": "เอเจนต์ไม่จดสิ่งที่เรียนรู้จากระเบียนอีกต่อไป",
  "Now it takes on long tasks people ask for, over more than one run, once they say yes.":
    "ตอนนี้เอเจนต์รับงานระยะยาวที่ผู้คนขอ ซึ่งใช้การทำงานมากกว่าหนึ่งครั้ง เมื่อผู้นั้นตอบตกลง",
  "It no longer takes on long tasks.": "เอเจนต์ไม่รับงานระยะยาวอีกต่อไป",
  "Now it lets people set when their daily digest comes.": "ตอนนี้ผู้คนตั้งเวลารับสรุปประจำวันได้",
  "It no longer lets people set when their daily digest comes.": "ผู้คนตั้งเวลารับสรุปประจำวันไม่ได้อีกต่อไป",
  "Now it keeps what people tell it of how they like to work, at their word.":
    "ตอนนี้เอเจนต์เก็บสิ่งที่ผู้คนบอกเกี่ยวกับวิธีทำงานที่ชอบ ตามคำของผู้นั้น",
  "It no longer keeps what people tell it of how they like to work.":
    "เอเจนต์ไม่เก็บสิ่งที่ผู้คนบอกเกี่ยวกับวิธีทำงานที่ชอบอีกต่อไป",
  "no channel": "ไม่มีช่องทาง",
  "from {who}, on {channels}": "จาก {who} ทาง {channels}",
  "a schedule": "กำหนดเวลา",
  "{at}, {days}": "{at} {days}",
  "no time": "ยังไม่กำหนดเวลา",
  "changes {action}": "เปลี่ยน {action}",
  "no model": "ไม่มีโมเดล",
  "{model}, {levels}, in {parts}": "{model}, {levels}, ใน {parts}",
  "policy, need-to-know, limits": "นโยบาย หลักรู้เท่าที่จำเป็น ขีดจำกัด",
  "{ability} and {more}": "{ability} และอีก {more}",
  "asks it": "ถามอินสแตนซ์นี้",
  "asks it: the {agent}, in {parts}": "ถามอินสแตนซ์นี้: {agent} ใน {parts}",
  "asks it: the {agent}": "ถามอินสแตนซ์นี้: {agent}",
  "What to add": "สิ่งที่เพิ่มได้",
  "Find a tool": "ค้นหาเครื่องมือ",
  "Add": "เพิ่ม",
  "It has each of the scenario's tools.": "มีเครื่องมือของซีนาริโอครบทุกตัวแล้ว",
  "It {does}.": "{does}",
  "What starts it": "สิ่งที่เริ่มการทำงาน",
  "A schedule": "กำหนดเวลา",
  "It works on its own, at times you set.": "ทำงานเองตามเวลาที่คุณตั้ง",
  "People write to it.": "ผู้คนเขียนถึงเอเจนต์",
  "What people owe, in the {kind}": "สิ่งที่ผู้คนค้างอยู่ใน {kind}",
  "It reminds its people of what falls due.": "เตือนผู้คนถึงสิ่งที่ถึงกำหนด",
  "A daily report on the {kind}": "รายงานประจำวันเรื่อง {kind}",
  "Each working day, it tells each person it serves what changed in their own.":
    "ทุกวันทำการ จะแจ้งแต่ละคนที่ให้บริการว่ามีอะไรเปลี่ยนไปในรายการของตน",
  "Drag a tool onto the canvas, or press Enter on one to add it.":
    "ลากเครื่องมือมาวางบนแคนวาส หรือกด Enter ที่เครื่องมือเพื่อเพิ่ม",
  "What follows": "ผลที่ตามมา",
  "Took {tool} away. It changes no records now, so nobody decides anything it does.":
    "นำ {tool} ออกแล้ว ตอนนี้เอเจนต์ไม่ได้เปลี่ยนระเบียนใด จึงไม่มีใครต้องตัดสินใจสิ่งที่เอเจนต์ทำ",
  "Took {tool} away.": "นำ {tool} ออกแล้ว",
  "the scenario's tool": "เครื่องมือของซีนาริโอ",
  "not the scenario's": "ไม่ใช่ของซีนาริโอ",
  "The scenario hasn't got a tool called {tool}, so nothing would release it: take it away, or ask the scenario's engineers for it.":
    "ซีนาริโอไม่มีเครื่องมือชื่อ {tool} จึงไม่มีทางรีลีสได้: นำออก หรือขอเครื่องมือนี้จากวิศวกรของซีนาริโอ",
  "Take {tool} away": "นำ {tool} ออก",
  "a schedule: it works on its own": "กำหนดเวลา: ทำงานเอง",
  "Lowercase letters, digits and hyphens.": "ตัวอักษรพิมพ์เล็ก ตัวเลข และขีดกลาง",
  "At": "เวลา",
  "Such as 09:00, 13:30, in its instance owner's time zone.": "เช่น 09:00, 13:30 ตามเขตเวลาของเจ้าของอินสแตนซ์",
  "On": "ใน",
  "What a5s asks it each time": "สิ่งที่ a5s สั่งในแต่ละครั้ง",
  "Took the schedule {name} away.": "นำกำหนดเวลา {name} ออกแล้ว",
  "Take it away": "นำออก",
  "people write to it": "ผู้คนเขียนถึงเอเจนต์",
  "People can no longer write to it: only what else starts its runs does.":
    "ผู้คนเขียนถึงเอเจนต์ไม่ได้อีกต่อไป: การทำงานจะเริ่มจากสิ่งอื่นเท่านั้น",
  "Stop people writing to it": "หยุดให้ผู้คนเขียนถึงเอเจนต์",
  "the agent, {levels}": "เอเจนต์, {levels}",
  "Works for": "ทำงานให้",
  "Its model is {model} now.": "ตอนนี้ใช้โมเดล {model}",
  "Of those the deployment approves.": "จากโมเดลที่ระบบนี้อนุมัติ",
  "Level it starts at": "ระดับเริ่มต้น",
  "Highest level": "ระดับสูงสุด",
  "Its first instance, as you plan it": "อินสแตนซ์แรกตามแผนของคุณ",
  "Kept with the draft, and never in force: where it works, and for whom, are the settings', which its parts' owners approve once its release is signed. Putting it to work starts from this.":
    "เก็บไว้กับฉบับร่าง และไม่มีผลบังคับใช้: ทำงานที่ไหนและให้ใครเป็นเรื่องของการตั้งค่า ซึ่งเจ้าของส่วนงานจะอนุมัติเมื่อรีลีสได้รับการลงนามแล้ว การนำไปใช้งานจะเริ่มจากแผนนี้",
  "Works in": "ทำงานใน",
  "No parts the settings know, so none, and an instance approver approves it.":
    "ไม่มีส่วนงานที่การตั้งค่ารู้จัก จึงไม่มีส่วนงาน และผู้อนุมัติอินสแตนซ์เป็นผู้อนุมัติ",
  "Serves, a few people first": "ให้บริการ เริ่มจากไม่กี่คนก่อน",
  "Those the settings name already, and you.": "ผู้ที่การตั้งค่าระบุไว้แล้ว และคุณ",
  "May ask": "ถามได้",
  "Instances you may see at work.": "อินสแตนซ์ที่คุณดูการทำงานได้",
  "an instance": "อินสแตนซ์",
  "Its first instance may ask {id} questions, for the people it acts for, once the settings name it: the owners of its parts approve that with the rest of it.":
    "อินสแตนซ์แรกจะถามคำถาม {id} แทนผู้ที่ทำงานให้ได้ เมื่อการตั้งค่าระบุไว้: เจ้าของส่วนงานจะอนุมัติเรื่องนี้พร้อมกับส่วนอื่น",
  "{id} answers only with what those people may see, and its answers come back as what {id} said, never as records.":
    "{id} ตอบเฉพาะสิ่งที่ผู้คนเหล่านั้นเห็นได้ และคำตอบจะกลับมาเป็นสิ่งที่ {id} พูด ไม่ใช่ระเบียน",
  "Stop it asking {id}": "หยุดถาม {id}",
  "a5s's own abilities": "ความสามารถของ a5s เอง",
  "a5s's tools, held to its own rules": "เครื่องมือของ a5s ที่อยู่ภายใต้กฎของ a5s เอง",
  "Tokens a task may spend": "โทเค็นที่งานหนึ่งใช้ได้",
  "Days a task has": "จำนวนวันของงาน",
  "No model judges its work now: people's grades alone.": "ตอนนี้ไม่มีโมเดลประเมินงาน: ใช้การให้คะแนนของคนเท่านั้น",
  "{model} judges each sample of its work beside people's grades, never instead of them: no verdict moves a level.":
    "{model} ประเมินตัวอย่างงานแต่ละชิ้นควบคู่กับการให้คะแนนของคน ไม่ใช่แทนที่: ผลการประเมินไม่เคยเปลี่ยนระดับ",
  "through a5s's gateway": "ผ่านเกตเวย์ของ a5s",
  "Its model": "โมเดลที่ใช้",
  "Of those the deployment approves, for the data the settings say it may see.":
    "จากโมเดลที่ระบบนี้อนุมัติ สำหรับข้อมูลที่การตั้งค่าระบุว่าเอเจนต์เห็นได้",
  "Its judge, beside people's grades": "ผู้ประเมิน ควบคู่กับการให้คะแนนของคน",
  "none: people's grades alone": "ไม่มี: ใช้การให้คะแนนของคนเท่านั้น",
  "What a right change is, for its judge": "การเปลี่ยนแปลงที่ถูกต้องเป็นอย่างไร สำหรับผู้ประเมิน",
  "In its owners' words. The judge never moves a level: people's grades do.":
    "ตามคำของเจ้าของ ผู้ประเมินไม่เคยเปลี่ยนระดับ: การให้คะแนนของคนเท่านั้นที่เปลี่ยนได้",
  "every call to a tool passes them": "ทุกการเรียกใช้เครื่องมือต้องผ่าน",
  "Its tool must be its release's, pinned as the scenario has it; the record in a part its instance works in, and one everyone the run acts for may see; and a change waits, or is made, as its level and the scenario's limits say.":
    "เครื่องมือต้องเป็นของรีลีส และตรึงไว้ตามที่ซีนาริโอมี ระเบียนต้องอยู่ในส่วนงานที่อินสแตนซ์ทำงาน และทุกคนที่การทำงานทำแทนต้องเห็นได้ ส่วนการเปลี่ยนแปลงจะรอหรือทำได้ตามที่ระดับและขีดจำกัดของซีนาริโอกำหนด",
  "Tokens a run may spend": "โทเค็นที่การทำงานหนึ่งครั้งใช้ได้",
  "For each person a day": "ต่อคนต่อวัน",
  "Tokens of its conversation each run is given": "โทเค็นของบทสนทนาที่การทำงานแต่ละครั้งได้รับ",
  "Its limits": "ขีดจำกัด",
  "what each run ends in": "ผลสุดท้ายของการทำงานแต่ละครั้ง",
  "Each run writes only to the people it acts for, in the conversation it was started in, and a run a schedule starts acts for nobody, so it writes to nobody. a5s checks what it sends: links only to the scenario's records, and any value it worked out itself marked as its own.":
    "การทำงานแต่ละครั้งเขียนถึงเฉพาะผู้ที่ทำงานแทน ในบทสนทนาที่เริ่มการทำงานนั้น ส่วนการทำงานที่เริ่มตามกำหนดเวลาไม่ได้ทำแทนใคร จึงไม่เขียนถึงใคร a5s ตรวจสอบสิ่งที่ส่ง: ลิงก์ได้เฉพาะระเบียนของซีนาริโอ และค่าใดที่เอเจนต์คำนวณเองจะถูกระบุว่าเป็นของเอเจนต์เอง",
  "Each run writes only to the people it acts for, in the conversation it was started in. a5s checks what it sends: links only to the scenario's records, and any value it worked out itself marked as its own.":
    "การทำงานแต่ละครั้งเขียนถึงเฉพาะผู้ที่ทำงานแทน ในบทสนทนาที่เริ่มการทำงานนั้น a5s ตรวจสอบสิ่งที่ส่ง: ลิงก์ได้เฉพาะระเบียนของซีนาริโอ และค่าใดที่เอเจนต์คำนวณเองจะถูกระบุว่าเป็นของเอเจนต์เอง",
  "It reminds its people of what falls due in the {kinds}, each run acting for the person it's for.":
    "เตือนผู้คนถึงสิ่งที่ถึงกำหนดใน {kinds} โดยการทำงานแต่ละครั้งทำแทนผู้ที่เกี่ยวข้อง",
  "Once a day, it tells each person it serves what changed in their own {kind}, in their digest: code works the facts out, and the run, acting for them, puts them into words.":
    "วันละครั้ง จะแจ้งแต่ละคนที่ให้บริการว่ามีอะไรเปลี่ยนไปใน {kind} ของตน ผ่านสรุปประจำวัน: โค้ดหาข้อเท็จจริง และการทำงานซึ่งทำแทนผู้นั้นจะเรียบเรียงเป็นถ้อยคำ",
  "A start": "จุดเริ่มต้น",
  "what starts its runs": "สิ่งที่เริ่มการทำงาน",
  "Change it under Files, in agent.yaml.": "แก้ไขได้ที่ไฟล์ ใน agent.yaml",
  "Who decides its changes": "ใครตัดสินใจการเปลี่ยนแปลง",
  "Nobody: it changes no records a part decides.": "ไม่มีใคร: เอเจนต์ไม่ได้เปลี่ยนระเบียนที่ส่วนงานต้องตัดสินใจ",
  "Nobody yet: its release keeps it at level 0, which only observes, so a5s refuses every change it asks for, {actions}.":
    "ยังไม่มีใคร: รีลีสกำหนดให้อยู่ที่ระดับ 0 ซึ่งสังเกตการณ์อย่างเดียว a5s จึงปฏิเสธทุกการเปลี่ยนแปลงที่เอเจนต์ขอ ได้แก่ {actions}",
  "Below level 2, each change it asks for, {actions}, waits for a yes from a decider of its record's part, in the parts you plan its first instance in, and its release keeps it below level 2:":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอ ได้แก่ {actions} จะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง ในส่วนงานที่คุณวางแผนให้อินสแตนซ์แรกทำงาน และรีลีสกำหนดให้อยู่ต่ำกว่าระดับ 2:",
  "Below level 2, each change it asks for, {actions}, waits for a yes from a decider of its record's part, in the parts you plan its first instance in:":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอ ได้แก่ {actions} จะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง ในส่วนงานที่คุณวางแผนให้อินสแตนซ์แรกทำงาน:",
  "Below level 2, each change it asks for, {actions}, waits for a yes from a decider of its record's part, and its release keeps it below level 2:":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอ ได้แก่ {actions} จะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง และรีลีสกำหนดให้อยู่ต่ำกว่าระดับ 2:",
  "Below level 2, each change it asks for, {actions}, waits for a yes from a decider of its record's part:":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอ ได้แก่ {actions} จะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง:",
  "its owners and their delegates, as the settings and the directory name them.":
    "เจ้าของส่วนงานและผู้ได้รับมอบหมาย ตามที่การตั้งค่าและไดเรกทอรีระบุ",
  "{tools} run only at level 2, which only the settings give.":
    "{tools} ทำงานได้เฉพาะที่ระดับ 2 ซึ่งมีแต่การตั้งค่าที่ให้ได้",
  "Who puts it to work": "ใครนำไปใช้งาน",
  "Its parts' owners approve it, as a version of the settings, once its release is signed: {owners}.":
    "เจ้าของส่วนงานจะอนุมัติในรูปเวอร์ชันของการตั้งค่า เมื่อรีลีสได้รับการลงนามแล้ว: {owners}",
  "{who}, for {part}": "{who} สำหรับ {part}",
  "With no part, an instance approver approves it, as a version of the settings, once its release is signed: {approvers}.":
    "เมื่อไม่มีส่วนงาน ผู้อนุมัติอินสแตนซ์จะอนุมัติในรูปเวอร์ชันของการตั้งค่า เมื่อรีลีสได้รับการลงนามแล้ว: {approvers}",
  "Its parts' owners approve it, as a version of the settings, once its release is signed.":
    "เจ้าของส่วนงานจะอนุมัติในรูปเวอร์ชันของการตั้งค่า เมื่อรีลีสได้รับการลงนามแล้ว",
  "As planned, serving {who}, and asking {instances}.": "ตามแผน ให้บริการ {who} และถาม {instances}",
  "As planned, serving {who}.": "ตามแผน ให้บริการ {who}",
  "As planned, asking {instances}.": "ตามแผน ถาม {instances}",
  "Who signs its release": "ใครลงนามรีลีส",
  "Once its definition loads.": "เมื่อโหลดนิยามเสร็จ",
  "Nobody more than for any release: it changes nothing of what's released here.":
    "ไม่มีใครเพิ่มจากรีลีสทั่วไป: ไม่ได้เปลี่ยนสิ่งใดที่รีลีสไว้ที่นี่",
  ", because {why}.": " เพราะ {why}",
  ", because {why}": " เพราะ {why}",
  "Nobody holds that role in the directory yet: its release can't be approved until the directory names someone.":
    "ยังไม่มีใครในไดเรกทอรีที่มีบทบาทนี้: จะอนุมัติรีลีสไม่ได้จนกว่าไดเรกทอรีจะระบุผู้รับบทบาท",
  "As": "เป็น",
  "works it out, from what it changes of the agents released here. The pull request it's published as names them.":
    "ที่คำนวณรายชื่อนี้จากสิ่งที่เปลี่ยนในเอเจนต์ที่รีลีสไว้ที่นี่ และ pull request ที่เผยแพร่จะระบุชื่อเหล่านี้",
  "Show it": "มุมมอง",
  "Canvas": "แคนวาส",
  "List": "รายการ",
  "What starts its runs": "สิ่งที่เริ่มการทำงาน",
  "The agent": "เอเจนต์",
  "What it works with": "สิ่งที่ใช้ทำงาน",
  "Add to it": "เพิ่ม",
  "Add a tool, an ability or a start": "เพิ่มเครื่องมือ ความสามารถ หรือจุดเริ่มต้น",
  "Now {who} must sign its release: {why}.": "ตอนนี้ {who} ต้องลงนามรีลีส: {why}",
  "{who} needn't sign it now.": "{who} ไม่ต้องลงนามแล้ว",
  "Added {tool}. {follows}": "เพิ่ม {tool} แล้ว {follows}",
  "Added a schedule, {name}. {follows}": "เพิ่มกำหนดเวลา {name} แล้ว {follows}",
  "Now it reminds its people of what falls due in the {kind}, each run acting for the person it's for.":
    "ตอนนี้เอเจนต์เตือนผู้คนถึงสิ่งที่ถึงกำหนดใน {kind} โดยการทำงานแต่ละครั้งทำแทนผู้ที่เกี่ยวข้อง",
  "Each working day, it tells each person it serves what changed in their own {kind}, in their digest.":
    "ทุกวันทำการ จะแจ้งแต่ละคนที่ให้บริการว่ามีอะไรเปลี่ยนไปใน {kind} ของตน ผ่านสรุปประจำวัน",
  "It no longer reminds its people of what falls due.": "เอเจนต์ไม่เตือนผู้คนถึงสิ่งที่ถึงกำหนดอีกต่อไป",
  "It no longer reports on the {kind} each day.": "เอเจนต์ไม่รายงานเรื่อง {kind} ทุกวันอีกต่อไป",
  "It would work first in {parts}: {deciders} would decide its changes there.":
    "อินสแตนซ์แรกจะทำงานใน {parts} ก่อน: {deciders} จะตัดสินใจการเปลี่ยนแปลงที่นั่น",
  "It would work first in {parts}.": "อินสแตนซ์แรกจะทำงานใน {parts} ก่อน",
  "It would work in no part's records first.": "ในช่วงแรกจะไม่ทำงานกับระเบียนของส่วนงานใด",
  "It would serve {who} first.": "จะให้บริการ {who} ก่อน",
  "It would serve nobody yet.": "ยังจะไม่ให้บริการใคร",
  "It won't ask {instance}.": "จะไม่ถาม {instance}",
  "Its first instance may ask {instance}, once the settings name it. Its release now lets it ask other agents, those the settings name, so its release approver signs that.":
    "อินสแตนซ์แรกจะถาม {instance} ได้เมื่อการตั้งค่าระบุไว้ ตอนนี้รีลีสอนุญาตให้ถามเอเจนต์อื่นที่การตั้งค่าระบุ ผู้อนุมัติรีลีสจึงต้องลงนามเรื่องนี้",
  "Its first instance may ask {instance}, once the settings name it.":
    "อินสแตนซ์แรกจะถาม {instance} ได้เมื่อการตั้งค่าระบุไว้",
  "Add a tool": "เพิ่มเครื่องมือ",
  "Add what starts it": "เพิ่มสิ่งที่เริ่มการทำงาน",
  "+ Add": "+ เพิ่ม",
  "What's chosen": "สิ่งที่เลือก",
  "The draft as a whole": "ภาพรวมของฉบับร่าง",

  // What follows from what an agent may do, as the designer says it (consequences.ts)
  "{list} or {last}": "{list} หรือ {last}",
  "{list} and {last}": "{list} และ {last}",
  "{n} tokens": "{n} โทเค็น",
  "Mondays": "วันจันทร์",
  "Tuesdays": "วันอังคาร",
  "Wednesdays": "วันพุธ",
  "Thursdays": "วันพฤหัสบดี",
  "Fridays": "วันศุกร์",
  "Saturdays": "วันเสาร์",
  "Sundays": "วันอาทิตย์",
  "on weekdays": "ทุกวันจันทร์ถึงวันศุกร์",
  "on {days}": "ทุก{days}",
  "nobody yet, so none is made there": "ยังไม่มีใคร จึงไม่มีการเปลี่ยนแปลงที่นั่น",
  "Its release keeps it at level 0, which only observes, so a5s refuses every change it asks for. At level 1, each would wait for a yes from a decider of its record's part.":
    "รีลีสกำหนดให้อยู่ที่ระดับ 0 ซึ่งสังเกตการณ์อย่างเดียว a5s จึงปฏิเสธทุกการเปลี่ยนแปลงที่เอเจนต์ขอ ที่ระดับ 1 แต่ละรายการจะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง",
  "{who} in {part}": "{who} ใน {part}",
  "Below level 2, each change it asks for waits for a yes from a decider of its record's part: {deciders}.":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอจะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง: {deciders}",
  "Below level 2, each change it asks for waits for a yes from a decider of its record's part, its owners and their delegates.":
    "ต่ำกว่าระดับ 2 การเปลี่ยนแปลงแต่ละรายการที่เอเจนต์ขอจะรอให้ผู้ตัดสินใจของส่วนงานที่ระเบียนนั้นอยู่ตอบตกลง คือเจ้าของส่วนงานและผู้ได้รับมอบหมาย",
  "{n} in a run": "{n} รายการต่อการทำงานหนึ่งครั้ง",
  "{n} for each person in 30 days": "{n} รายการต่อคนใน 30 วัน",
  "The settings allow {most}: past that, each waits for its decider, whatever the level.":
    "การตั้งค่าอนุญาต {most}: เกินกว่านั้น แต่ละรายการจะรอผู้ตัดสินใจ ไม่ว่าจะอยู่ระดับใด",
  "The settings set no limit for {action}, so at level 2 nothing caps how many it makes.":
    "การตั้งค่าไม่ได้กำหนดขีดจำกัดของ {action} ที่ระดับ 2 จึงไม่มีอะไรจำกัดจำนวนที่ทำได้",
  "Its release goes no higher than level {max}, so every one waits for its decider.":
    "รีลีสให้สูงสุดแค่ระดับ {max} ทุกรายการจึงต้องรอผู้ตัดสินใจ",
  "{share} in {part}": "{share} ใน {part}",
  "never in {part}, which sets no bar": "ไม่ทำเลยใน {part} ซึ่งไม่ได้กำหนดเกณฑ์",
  "a5s makes one alone only at level 2, which the settings give for {action} in one part at a time, never in a run that has read outside content, and only once graded samples show enough of its changes there right: {bars}.":
    "a5s จะทำการเปลี่ยนแปลงเองเฉพาะที่ระดับ 2 ซึ่งการตั้งค่าให้สำหรับ {action} ทีละส่วนงาน ไม่ทำในการทำงานที่อ่านเนื้อหาจากภายนอกมาแล้ว และทำเฉพาะเมื่อตัวอย่างที่ให้คะแนนแล้วแสดงว่าการเปลี่ยนแปลงในส่วนงานนั้นถูกต้องมากพอ: {bars}",
  "a5s makes one alone only at level 2, which the settings give for {action} in one part at a time, never in a run that has read outside content, and only once graded samples show enough of its changes there right.":
    "a5s จะทำการเปลี่ยนแปลงเองเฉพาะที่ระดับ 2 ซึ่งการตั้งค่าให้สำหรับ {action} ทีละส่วนงาน ไม่ทำในการทำงานที่อ่านเนื้อหาจากภายนอกมาแล้ว และทำเฉพาะเมื่อตัวอย่างที่ให้คะแนนแล้วแสดงว่าการเปลี่ยนแปลงในส่วนงานนั้นถูกต้องมากพอ",
  "What it does can't be undone, so a5s lets it run only at level 2, which only the settings give, and never in a run that has read outside content.":
    "สิ่งที่เครื่องมือนี้ทำย้อนกลับไม่ได้ a5s จึงให้ทำงานเฉพาะที่ระดับ 2 ซึ่งมีแต่การตั้งค่าที่ให้ได้ และไม่ทำในการทำงานที่อ่านเนื้อหาจากภายนอกมาแล้ว",
  "It sends outside the organisation, so a5s lets it run only at level 2, which only the settings give, and never in a run that has read outside content.":
    "เครื่องมือนี้ส่งข้อมูลออกนอกองค์กร a5s จึงให้ทำงานเฉพาะที่ระดับ 2 ซึ่งมีแต่การตั้งค่าที่ให้ได้ และไม่ทำในการทำงานที่อ่านเนื้อหาจากภายนอกมาแล้ว",
  "Its release goes no higher than level {max}, so a5s refuses every call to it.":
    "รีลีสให้สูงสุดแค่ระดับ {max} a5s จึงปฏิเสธทุกการเรียกใช้เครื่องมือนี้",
  "It writes, but changes nothing a part decides: from level 1 it runs without anyone's yes, and the ledger keeps each call. At level 0, which only observes, a5s refuses it.":
    "เครื่องมือนี้เขียนข้อมูล แต่ไม่ได้เปลี่ยนสิ่งที่ส่วนงานต้องตัดสินใจ: ตั้งแต่ระดับ 1 จะทำงานได้โดยไม่ต้องรอใครตอบตกลง และเลดเจอร์จะเก็บทุกการเรียกใช้ ที่ระดับ 0 ซึ่งสังเกตการณ์อย่างเดียว a5s จะปฏิเสธ",
  "Its release keeps it at level 0, so a5s refuses every call to it.":
    "รีลีสกำหนดให้อยู่ที่ระดับ 0 a5s จึงปฏิเสธทุกการเรียกใช้เครื่องมือนี้",
  "It reads: a5s passes on only the records everyone the run acts for may see, in the parts its instance works in.":
    "เครื่องมือนี้อ่านข้อมูล: a5s ส่งต่อเฉพาะระเบียนที่ทุกคนที่การทำงานนั้นทำแทนเห็นได้ ในส่วนงานที่อินสแตนซ์ทำงานอยู่",
  "What it brings from outside the organisation, its {what}, goes to a5s's reader first: the agent reads only what the reader takes from it, and the run is marked, so it never acts at level 2.":
    "สิ่งที่เครื่องมือนี้นำเข้ามาจากภายนอกองค์กร ได้แก่ {what} จะผ่านตัวอ่านของ a5s ก่อน: เอเจนต์อ่านเฉพาะสิ่งที่ตัวอ่านดึงออกมา และการทำงานนั้นจะถูกทำเครื่องหมายไว้ จึงไม่ทำงานที่ระดับ 2",
  "What it brings holds a few words written outside the organisation, such as titles, which the agent reads as they are: so the run is marked, and never acts at level 2.":
    "สิ่งที่เครื่องมือนี้นำมามีถ้อยคำสั้น ๆ ที่เขียนขึ้นภายนอกองค์กร เช่น ชื่อเอกสาร ซึ่งเอเจนต์อ่านตามที่เป็นอยู่ การทำงานนั้นจึงถูกทำเครื่องหมายไว้ และไม่ทำงานที่ระดับ 2",
  "It hands {what} over as handles: the model never sees the values, and a5s puts them back where they go.":
    "เครื่องมือนี้ส่ง {what} เป็นตัวอ้างอิง: โมเดลไม่เคยเห็นค่าจริง และ a5s จะใส่ค่ากลับไปในที่ที่ควรอยู่",
  "no time yet": "ยังไม่ได้กำหนดเวลา",
  "a5s starts a run at {at}, {days}, in its instance owner's time zone, and asks it: “{task}”":
    "a5s เริ่มการทำงานเวลา {at} {days} ตามเขตเวลาของเจ้าของอินสแตนซ์ และสั่งว่า: “{task}”",
  "A run a schedule starts acts for nobody, so it writes to nobody, and what it learns from records it may note in its notebook, checked against them, for its later runs.":
    "การทำงานที่เริ่มตามกำหนดเวลาไม่ได้ทำแทนใคร จึงไม่เขียนถึงใคร และสิ่งที่เรียนรู้จากระเบียนอาจจดไว้ในสมุดบันทึก โดยตรวจกับระเบียนนั้น เพื่อใช้ในการทำงานครั้งต่อไป",
  "A run a schedule starts acts for nobody, so it writes to nobody.":
    "การทำงานที่เริ่มตามกำหนดเวลาไม่ได้ทำแทนใคร จึงไม่เขียนถึงใคร",
  "People write to it on {channels}. Each run acts for whoever wrote, sees only what they may see, and writes to them alone.":
    "ผู้คนเขียนถึงเอเจนต์ทาง {channels} การทำงานแต่ละครั้งทำแทนผู้ที่เขียนมา เห็นเฉพาะสิ่งที่ผู้นั้นเห็นได้ และเขียนตอบผู้นั้นเท่านั้น",
  "no channel yet": "ยังไม่มีช่องทาง",
  "Its instances start at level {start}: it only observes: a5s refuses any tool that writes.":
    "อินสแตนซ์เริ่มที่ระดับ {start}: สังเกตการณ์อย่างเดียว a5s ปฏิเสธเครื่องมือใดก็ตามที่เขียนข้อมูล",
  "Its instances start at level {start}: it may write, and each change it asks for waits for its decider.":
    "อินสแตนซ์เริ่มที่ระดับ {start}: เขียนข้อมูลได้ และการเปลี่ยนแปลงแต่ละรายการที่ขอจะรอผู้ตัดสินใจ",
  "It goes no higher.": "ไม่สูงไปกว่านี้",
  "It may go as far as level 1, so a person decides every change it asks for.":
    "ขึ้นได้สูงสุดถึงระดับ 1 คนจึงเป็นผู้ตัดสินใจทุกการเปลี่ยนแปลงที่เอเจนต์ขอ",
  "It may reach level 2, making changes alone, only where the settings give it for a type of change in a part, and graded samples of its work there bear it out.":
    "ขึ้นถึงระดับ 2 ซึ่งทำการเปลี่ยนแปลงเองได้ เฉพาะเมื่อการตั้งค่าให้สำหรับการเปลี่ยนแปลงประเภทหนึ่งในส่วนงานหนึ่ง และตัวอย่างงานที่ให้คะแนนแล้วในส่วนงานนั้นยืนยันได้",
  "Each run may spend {run}, and its instance {person} for each person a day, a fifth of it kept for chases and reminders.":
    "การทำงานแต่ละครั้งใช้ได้ {run} และอินสแตนซ์ใช้ได้ {person} ต่อคนต่อวัน โดยกันไว้หนึ่งในห้าสำหรับการติดตามและการเตือน",
  "Each run is given {tokens} of its conversation, split by part.":
    "การทำงานแต่ละครั้งได้รับบทสนทนา {tokens} แบ่งตามส่วนงาน",
  "A long task may spend {tokens}, over {days} at most.": "งานระยะยาวใช้ได้ {tokens} ภายในเวลาไม่เกิน {days}",
  "{action}: {limits}, then each waits.": "{action}: {limits} จากนั้นแต่ละรายการต้องรอ",
  "{n} a run": "{n} รายการต่อครั้ง",
  "offers reminders, and keeps those people confirm": "เสนอการเตือน และเก็บการเตือนที่ผู้คนยืนยันไว้",
  "searches its conversation with the person it acts for, and corrects its summaries at their word":
    "ค้นหาในบทสนทนากับผู้ที่เอเจนต์ทำงานแทน และแก้บทสรุปตามคำของผู้นั้น",
  "Documents from outside": "เอกสารจากภายนอก",
  "asks a5s's reader about documents from outside its run has read":
    "ถามตัวอ่านของ a5s เกี่ยวกับเอกสารจากภายนอกที่การทำงานได้อ่านมา",
  "Other agents": "เอเจนต์อื่น",
  "asks other agents questions: the settings name which, and their owners approve it":
    "ถามคำถามเอเจนต์อื่น: การตั้งค่าระบุว่าตัวใด และเจ้าของเอเจนต์เหล่านั้นอนุมัติ",
  "Its notebook": "สมุดบันทึก",
  "notes what it learns from records, on its schedules, for its later runs":
    "จดสิ่งที่เรียนรู้จากระเบียนตามกำหนดเวลา ไว้ใช้ในการทำงานครั้งต่อไป",
  "Long tasks": "งานระยะยาว",
  "takes on work people ask for over more than one run, once they say yes":
    "รับงานที่ผู้คนขอซึ่งใช้การทำงานมากกว่าหนึ่งครั้ง เมื่อผู้นั้นตอบตกลง",
  "Their digest's time": "เวลาของสรุปประจำวัน",
  "lets people set when their daily digest comes": "ให้ผู้คนตั้งเวลารับสรุปประจำวัน",
  "How they like to work": "วิธีทำงานที่ผู้คนชอบ",
  "keeps what people tell it of how they like to work, at their word":
    "เก็บสิ่งที่ผู้คนบอกเกี่ยวกับวิธีทำงานที่ชอบ ตามคำของผู้นั้น",

  // Trying it in the sandbox, its test cases, and comparing models on them
  "Case {n} of {total} on {model}…": "กรณีที่ {n} จาก {total} บน {model}…",
  "Compare models on them": "เปรียบเทียบโมเดลด้วยกรณีทดสอบเหล่านี้",
  "Run them on each model you choose, one after another, and see how many each passes, how long they take, and what they cost at its prices, to pick the cheapest that's good enough. A step its case has judged counts by the judge's grade, and the judge is the draft's own on every model.":
    "รันกรณีทดสอบบนแต่ละโมเดลที่คุณเลือกทีละโมเดล แล้วดูว่าแต่ละโมเดลผ่านกี่กรณี ใช้เวลานานเท่าใด และมีค่าใช้จ่ายเท่าใดตามราคาของโมเดลนั้น เพื่อเลือกโมเดลที่ถูกที่สุดที่ดีพอ ขั้นตอนที่กรณีทดสอบให้ผู้ประเมินตัดสินจะนับตามคะแนนของผู้ประเมิน และผู้ประเมินเป็นของฉบับร่างเองในทุกโมเดล",
  "Models to compare": "โมเดลที่จะเปรียบเทียบ",
  " (how it's wired, not what it would say)": " (ดูการเชื่อมต่อ ไม่ใช่สิ่งที่จะตอบ)",
  "Compare two or more models": "เปรียบเทียบตั้งแต่ 2 โมเดลขึ้นไป",
  "Compare {n} models": "เปรียบเทียบ {n} โมเดล",
  "Passed": "ผ่าน",
  "Cost, at its prices": "ค่าใช้จ่ายตามราคาของโมเดล",
  "{passed} of {total}": "{passed} จาก {total}",
  "{n} couldn't run": "รันไม่ได้ {n} กรณี",
  "its prices aren't known": "ไม่ทราบราคา",
  "{model} passed every case for the least: {cost} at its prices.":
    "{model} ผ่านทุกกรณีด้วยค่าใช้จ่ายต่ำสุด: {cost} ตามราคาของโมเดล",
  "No model with known prices passed every case.": "ไม่มีโมเดลที่ทราบราคาผ่านครบทุกกรณี",
  "Its test cases": "กรณีทดสอบ",
  "Running them…": "กำลังรัน…",
  "Run the {n} the sandbox can": "รัน {n} กรณีที่แซนด์บ็อกซ์รันได้",
  "It has none yet: keep what you said to it as one, above.":
    "ยังไม่มี: เก็บสิ่งที่คุณพูดกับเอเจนต์เป็นกรณีทดสอบได้ที่ด้านบน",
  "On the stand-in, a case shows how the draft is wired, not what it would say: run them on a real model for that.":
    "บนโมเดลจำลอง กรณีทดสอบแสดงการเชื่อมต่อของฉบับร่าง ไม่ใช่สิ่งที่จะตอบ: หากต้องการดูคำตอบ ให้รันบนโมเดลจริง",
  "{passed} of {total} passed": "ผ่าน {passed} จาก {total}",
  "its suite alone": "เฉพาะชุดทดสอบ",
  "running…": "กำลังรัน…",
  "not run": "ไม่ได้รัน",
  "It needs {what}, which the agent's suite runs, on a stack of its own.":
    "ต้องใช้ {what} ซึ่งชุดทดสอบของเอเจนต์รันบนสแต็กของตัวเอง",
  "What it was told, and answered": "ข้อความที่ได้รับ และคำตอบ",
  "Told": "ข้อความ",
  "Answered": "คำตอบ",
  "used {tools}": "ใช้ {tools}",
  "The stand-in judged it": "โมเดลจำลองประเมินแล้ว",
  "Its judge, {judge}, found it": "ผู้ประเมิน {judge} ให้ผลว่า",
  "Nobody judged it": "ไม่มีใครประเมิน",
  "{name} answered": "{name} ตอบ",
  "What the model was sent and said, once": "สิ่งที่ส่งให้โมเดลและสิ่งที่โมเดลตอบ 1 ครั้ง",
  "What the model was sent and said, {n} times": "สิ่งที่ส่งให้โมเดลและสิ่งที่โมเดลตอบ {n} ครั้ง",
  "Call {n}, with {tools} tools offered: all call {before} was sent, then":
    "ครั้งที่ {n} เสนอเครื่องมือ {tools} รายการ: ส่งทุกอย่างที่ส่งในครั้งที่ {before} แล้วตามด้วย",
  "Call {n}, with {tools} tools offered": "ครั้งที่ {n} เสนอเครื่องมือ {tools} รายการ",
  "Call {n}: all call {before} was sent, then": "ครั้งที่ {n}: ส่งทุกอย่างที่ส่งในครั้งที่ {before} แล้วตามด้วย",
  "Call {n}": "ครั้งที่ {n}",
  "Asking the sandbox…": "กำลังถามแซนด์บ็อกซ์…",
  "Kept as {name}, in {file}.": "เก็บเป็น {name} ใน {file} แล้ว",
  "The sandbox is a deployment of its own: its records and its people are made up, and nothing said here reaches anyone's real records. It tries the draft as it was last kept. Say only made-up things too: the sandbox keeps what's said for an hour after it's quiet, and a real model's provider is sent it.":
    "แซนด์บ็อกซ์เป็นระบบที่แยกต่างหาก: ระเบียนและผู้คนในนั้นเป็นข้อมูลสมมติ และสิ่งที่พูดที่นี่จะไม่ไปถึงระเบียนจริงของใคร แซนด์บ็อกซ์ทดลองฉบับร่างตามที่บันทึกไว้ล่าสุด พูดแต่เรื่องสมมติเช่นกัน: แซนด์บ็อกซ์เก็บสิ่งที่พูดไว้หนึ่งชั่วโมงหลังจากเงียบไป และส่งให้ผู้ให้บริการของโมเดลจริง",
  "Say it as": "พูดในนามของ",
  "{name} said": "{name} พูดว่า",
  "The sandbox is running it…": "แซนด์บ็อกซ์กำลังรัน…",
  "Keep what {name} said to it as a test case, which its suite runs on its model: on the stand-in, what they said alone, since what the stand-in used isn't the agent's choice":
    "เก็บสิ่งที่ {name} พูดกับเอเจนต์ไว้เป็นกรณีทดสอบ ซึ่งชุดทดสอบจะรันบนโมเดลของเอเจนต์: บนโมเดลจำลอง จะเก็บเฉพาะสิ่งที่พูด เพราะเครื่องมือที่โมเดลจำลองใช้ไม่ใช่การเลือกของเอเจนต์",
  "Keep what {name} said to it as a test case, which its suite runs on its model, with the tools it used":
    "เก็บสิ่งที่ {name} พูดกับเอเจนต์ไว้เป็นกรณีทดสอบ ซึ่งชุดทดสอบจะรันบนโมเดลของเอเจนต์ พร้อมเครื่องมือที่ใช้",
  "Tools it must never use here, whatever it's told": "เครื่องมือที่ห้ามใช้ในกรณีนี้ ไม่ว่าจะได้รับคำสั่งอย่างไร",
  "Words it must never say, apart by commas": "คำที่ห้ามพูด คั่นด้วยจุลภาค",
  "such as: closed, I've reset": "เช่น: ปิดแล้ว, รีเซ็ตให้แล้ว",
  "What a right answer is, in your words, where it can be right in more than one way: its judge grades it, beside the checks above":
    "คำตอบที่ถูกต้องเป็นอย่างไร ในคำพูดของคุณ เมื่อตอบถูกได้หลายแบบ: ผู้ประเมินจะให้คะแนน ควบคู่กับการตรวจสอบข้างต้น",
  "such as: it proposes \"EA\" as the base unit, with correct_value, and says the owner decides it":
    "เช่น: เสนอ \"EA\" เป็นหน่วยฐาน ด้วย correct_value และบอกว่าเจ้าของเป็นผู้ตัดสินใจ",
  "The stand-in judges by words alone: the words you quote, and the tools you name. The draft's own judge reads what you mean.":
    "โมเดลจำลองประเมินจากคำเท่านั้น: คำที่คุณยกมา และเครื่องมือที่คุณระบุ ผู้ประเมินของฉบับร่างจะอ่านสิ่งที่คุณหมายถึง",
  "Keep as a test case": "เก็บเป็นกรณีทดสอบ",
  "Say something to it": "พูดอะไรสักอย่างกับเอเจนต์",
  "Put right what would stop its release first": "แก้สิ่งที่ทำให้ยังรีลีสไม่ได้ก่อน",
  "Running…": "กำลังรัน…",
  "Say it": "ส่ง",

  // Publishing it, as a pull request
  "The description is copied.": "คัดลอกคำอธิบายแล้ว",
  "Select the description and copy it.": "เลือกคำอธิบายแล้วคัดลอกเอง",
  "You open its pull request: download its folder, put it in the agents' repository as":
    "คุณเปิด pull request เอง: ดาวน์โหลดโฟลเดอร์ แล้ววางไว้ใน repository ของเอเจนต์เป็น",
  "on a branch of your own, and open a pull request from it, titled as below, with this description, which tells its reviewers who must sign its release.":
    "บน branch ของคุณเอง แล้วเปิด pull request จาก branch นั้น โดยใช้ชื่อเรื่องด้านล่างและคำอธิบายนี้ ซึ่งบอกผู้ตรวจทานว่าใครต้องลงนามรีลีส",
  "Put right what would stop its release first: its description says what, as it stands.":
    "แก้สิ่งที่ทำให้ยังรีลีสไม่ได้ก่อน: คำอธิบายบอกว่ามีอะไรบ้างในตอนนี้",
  "Its title": "ชื่อเรื่อง",
  "Its description": "คำอธิบาย",
  "Download its folder": "ดาวน์โหลดโฟลเดอร์",
  "Copy the description": "คัดลอกคำอธิบาย",
  "its pull request": "pull request",
  ". CI runs its checks and test cases there, and the people above sign its release. Publishing it again adds a commit to it.":
    " CI จะรันการตรวจสอบและกรณีทดสอบที่นั่น และผู้ที่ระบุไว้ข้างต้นจะลงนามรีลีส การเผยแพร่อีกครั้งจะเพิ่ม commit ลงใน pull request นี้",
  "A pull request to the agents' repository, opened as you: a5s asks GitHub to let it act as you, for this alone, and keeps no token of yours.":
    "pull request ไปยัง repository ของเอเจนต์ ที่เปิดในนามของคุณ: a5s ขอให้ GitHub อนุญาตให้ทำในนามของคุณเฉพาะครั้งนี้ และไม่เก็บโทเค็นของคุณ",
  "Let a5s publish it as you: at": "ให้ a5s เผยแพร่ในนามของคุณ: ที่",
  "GitHub's sign-in": "หน้าลงชื่อเข้าใช้ของ GitHub",
  ", enter": " ให้ป้อนรหัสนี้",
  "a5s waits for GitHub for {minutes} minutes at most.": "a5s รอ GitHub นานสุด {minutes} นาที",
  "Waiting for GitHub…": "กำลังรอ GitHub…",
  "Publish again": "เผยแพร่อีกครั้ง",
  "Publish as a pull request": "เผยแพร่เป็น pull request",

  // The settings: the version in force, those waiting, the forms and the text, and asking for a change
  "level 0, suggests: it reads and drafts, and people do the rest":
    "ระดับ 0 เสนอแนะ: อ่านและร่าง ส่วนที่เหลือคนเป็นผู้ทำ",
  "level 1, asks: its changes wait for a person's yes": "ระดับ 1 ขออนุญาต: การเปลี่ยนแปลงจะรอให้คนตอบตกลง",
  "What you'd changed and hadn't asked for is back, from before you signed in again.":
    "สิ่งที่คุณแก้ไขไว้และยังไม่ได้ขอกลับมาแล้ว จากก่อนที่คุณลงชื่อเข้าใช้อีกครั้ง",
  "No settings are in force yet.": "ยังไม่มีการตั้งค่าที่มีผลบังคับใช้",
  "Settings": "การตั้งค่า",
  "everyone in the {team} team": "ทุกคนในทีม {team}",
  "everyone who holds the {role} role": "ทุกคนที่มีบทบาท {role}",
  "whatever level its release starts at, now level {level}": "ระดับที่รีลีสกำหนดให้เริ่ม ตอนนี้คือระดับ {level}",
  "whatever level its release starts at": "ระดับที่รีลีสกำหนดให้เริ่ม",
  "level 2, as written: a5s holds it at level 1 in a part, and gives level 2 only to a type of change, below":
    "ระดับ 2 ตามที่เขียนไว้: a5s คงไว้ที่ระดับ 1 ในส่วนงาน และให้ระดับ 2 เฉพาะการเปลี่ยนแปลงบางประเภทด้านล่าง",
  "It works at": "ทำงานที่",
  "its release allows level {level} at most": "รีลีสอนุญาตสูงสุดระดับ {level}",
  "In {part}, it works at": "ใน {part} ทำงานที่",
  "{id}'s level in {part}": "ระดับของ {id} ใน {part}",
  "the level above": "ระดับข้างต้น",
  "It makes these changes on its own, at level 2": "ทำการเปลี่ยนแปลงเหล่านี้เองที่ระดับ 2",
  "its release, {agent}, allows level {level} at most": "รีลีส {agent} อนุญาตสูงสุดระดับ {level}",
  "{part} needs no accuracy below, so it never earns level 2":
    "{part} ไม่ได้กำหนดความแม่นยำด้านล่าง จึงไม่มีทางได้ระดับ 2",
  "{action} in {part}": "{action} ใน {part}",
  "Each within its limits, below. a5s holds it at level 1 until graded samples of its work show the accuracy its part needs.":
    "แต่ละรายการอยู่ภายในขีดจำกัดด้านล่าง a5s คงไว้ที่ระดับ 1 จนกว่าตัวอย่างงานที่ให้คะแนนแล้วจะแสดงความแม่นยำที่ส่วนงานต้องการ",
  "It serves": "ให้บริการ",
  "an id, team:… or role:…": "id, team:… หรือ role:…",
  "Someone else {id} serves": "ผู้อื่นที่ {id} ให้บริการ",
  "Who runs it here": "ผู้ดูแล",
  "Owner": "เจ้าของ",
  "Deputy": "ผู้แทน",
  "Owner of {id}": "เจ้าของ {id}",
  "Deputy of {id}": "ผู้แทนของ {id}",
  "Its name is lowercase letters, digits and hyphens, starting with a letter or a digit.":
    "ชื่อต้องเป็นตัวอักษรพิมพ์เล็ก ตัวเลข และขีดกลาง โดยขึ้นต้นด้วยตัวอักษรหรือตัวเลข",
  "There's an instance called {id} already: give it another name.": "มีอินสแตนซ์ชื่อ {id} อยู่แล้ว: ตั้งชื่ออื่น",
  "Choose whom it serves: a few people first.": "เลือกผู้ที่จะให้บริการ: เริ่มจากไม่กี่คนก่อน",
  "{id} is in the forms: review it, with any other change, and ask its approvers.":
    "{id} อยู่ในแบบฟอร์มแล้ว: ตรวจทานพร้อมการเปลี่ยนแปลงอื่น แล้วขอผู้อนุมัติ",
  "Put an agent to work": "นำเอเจนต์ไปใช้งาน",
  "A new instance of an agent, for a few people first, at level 0 or 1, so it suggests, or asks before each change. Its part's owner approves it, as any change there; with no part, someone who approves instances does.":
    "อินสแตนซ์ใหม่ของเอเจนต์ สำหรับคนไม่กี่คนก่อน ที่ระดับ 0 หรือ 1 จึงทำได้แค่เสนอแนะ หรือขออนุญาตก่อนการเปลี่ยนแปลงแต่ละครั้ง เจ้าของส่วนงานจะอนุมัติเช่นเดียวกับการเปลี่ยนแปลงอื่นในส่วนงานนั้น หากไม่มีส่วนงาน ผู้อนุมัติอินสแตนซ์จะเป็นผู้อนุมัติ",
  "no part's records": "ไม่ใช้ระเบียนของส่วนงานใด",
  "Its name here": "ชื่ออินสแตนซ์",
  "It starts at": "เริ่มที่",
  "It works in {parts} too.": "ทำงานใน {parts} ด้วย",
  "It may ask {instances}.": "ถาม {instances} ได้",
  "As its draft's authors planned it: change the version's text for anything else.":
    "ตามที่ผู้เขียนฉบับร่างวางแผนไว้: แก้ข้อความของเวอร์ชันสำหรับเรื่องอื่น",
  "Owner of the new instance": "เจ้าของอินสแตนซ์ใหม่",
  "Deputy of the new instance": "ผู้แทนของอินสแตนซ์ใหม่",
  "Add it to the settings": "เพิ่มลงในการตั้งค่า",
  "Each type of change's limits": "ขีดจำกัดของการเปลี่ยนแปลงแต่ละประเภท",
  "How many one run may make, and how many for each person in 30 days. Past either, a change waits for a person to decide it, whatever the level. Empty means no limit.":
    "จำนวนที่การทำงานหนึ่งครั้งทำได้ และจำนวนต่อคนใน 30 วัน เมื่อเกินอย่างใดอย่างหนึ่ง การเปลี่ยนแปลงจะรอให้คนตัดสินใจ ไม่ว่าจะอยู่ระดับใด เว้นว่างไว้หมายถึงไม่จำกัด",
  "In one run": "ในการทำงานหนึ่งครั้ง",
  "For each person, in 30 days": "ต่อคน ใน 30 วัน",
  "The accuracy level 2 needs": "ความแม่นยำที่ระดับ 2 ต้องการ",
  "How accurate an agent's changes in a part must be, as graded samples show, before a5s raises its cap there to level 2. Empty means it never does.":
    "การเปลี่ยนแปลงของเอเจนต์ในส่วนงานต้องแม่นยำเพียงใด ตามที่ตัวอย่างที่ให้คะแนนแล้วแสดง ก่อนที่ a5s จะยกเพดานในส่วนงานนั้นเป็นระดับ 2 เว้นว่างไว้หมายถึงไม่ยกเลย",
  "The accuracy {part} needs, in percent": "ความแม่นยำที่ {part} ต้องการ เป็นเปอร์เซ็นต์",
  "a month": "ต่อเดือน",
  "The monthly budget for {part}": "งบประมาณรายเดือนของ {part}",
  "The monthly budget for the {agent}": "งบประมาณรายเดือนของ {agent}",
  "What agents' models may cost a month": "ค่าใช้จ่ายโมเดลของเอเจนต์ต่อเดือน",
  "A budget a5s shows each month's spending against, on the Spending page, at the prices models.yaml gives, and tells its owners of once a month is on course to pass it. It stops no work: the token budgets each release sets do. A part's owner approves its budget, and an agent's owner the agent's. Empty means none.":
    "งบประมาณที่ a5s ใช้เทียบกับค่าใช้จ่ายแต่ละเดือนในหน้าค่าใช้จ่าย ตามราคาที่ models.yaml กำหนด และแจ้งเจ้าของเมื่อเดือนใดมีแนวโน้มจะเกินงบ งบประมาณนี้ไม่ได้หยุดการทำงาน ซึ่งเป็นหน้าที่ของงบประมาณโทเค็นที่แต่ละรีลีสกำหนด เจ้าของส่วนงานอนุมัติงบประมาณของส่วนงาน และเจ้าของเอเจนต์อนุมัติงบประมาณของเอเจนต์ เว้นว่างไว้หมายถึงไม่มี",
  "{id}, the {agent}": "{id}, เอเจนต์ {agent}",
  "You asked for version {serial}. a5s asks its approvers within a minute, and puts it in force once they've all approved it.":
    "คุณขอเวอร์ชัน {serial} แล้ว a5s จะขอผู้อนุมัติภายในหนึ่งนาที และให้มีผลเมื่อทุกคนอนุมัติแล้ว",
  "You asked for version {serial}.": "คุณขอเวอร์ชัน {serial} แล้ว",
  "The instances at work: whom each serves, where it works and how far it may act there, and who runs it. A change is a new version, which those who must approve it approve on its own page; nothing changes until they do.":
    "อินสแตนซ์ที่ทำงานอยู่: แต่ละตัวให้บริการใคร ทำงานที่ไหนและทำได้แค่ไหน และใครดูแล การเปลี่ยนแปลงคือเวอร์ชันใหม่ ซึ่งผู้ที่ต้องอนุมัติจะอนุมัติในหน้าของเวอร์ชันนั้น ไม่มีอะไรเปลี่ยนจนกว่าจะอนุมัติ",
  "In force: version {serial}": "มีผลอยู่: เวอร์ชัน {serial}",
  "Waiting for approval": "รอการอนุมัติ",
  "Version {serial}": "เวอร์ชัน {serial}",
  ", approved so far by {who}.": " ซึ่งอนุมัติแล้วโดย {who}",
  ", which nobody has approved yet.": " ซึ่งยังไม่มีใครอนุมัติ",
  "It still waits because {needs}.": "ยังรออยู่เพราะ {needs}",
  "Ask for a change": "ขอเปลี่ยนแปลง",
  "Change the settings below, then review them. a5s gives the new version the next number, and once you ask for it, asks everyone who must approve it. Nothing changes until they do.":
    "เปลี่ยนการตั้งค่าด้านล่าง แล้วตรวจทาน a5s จะให้หมายเลขถัดไปกับเวอร์ชันใหม่ และเมื่อคุณขอ จะขอทุกคนที่ต้องอนุมัติ ไม่มีอะไรเปลี่ยนจนกว่าจะอนุมัติ",
  "How to write the change": "วิธีเขียนการเปลี่ยนแปลง",
  "Change it here": "เปลี่ยนที่นี่",
  "Edit the text": "แก้ไขข้อความ",
  "The whole version, as written, for whatever the forms don't change. What you review is the way you're using: these forms, or this text.":
    "เวอร์ชันทั้งหมดตามที่เขียนไว้ สำหรับสิ่งที่แบบฟอร์มไม่ได้เปลี่ยน สิ่งที่คุณตรวจทานคือวิธีที่คุณใช้อยู่: แบบฟอร์มเหล่านี้ หรือข้อความนี้",
  "The settings, as written": "การตั้งค่าตามที่เขียนไว้",
  "Review": "ตรวจทาน",
  "a5s can't propose this:": "a5s เสนอสิ่งนี้ไม่ได้:",
  "As version {serial}, a5s can't propose this:": "ในฐานะเวอร์ชัน {serial} a5s เสนอสิ่งนี้ไม่ได้:",
  "As version {serial}, it:": "ในฐานะเวอร์ชัน {serial} จะ:",
  "It needs the approval of {who}.": "ต้องได้รับการอนุมัติจาก {who}",
  "Nobody in the directory can approve it.": "ไม่มีใครในไดเรกทอรีอนุมัติได้",
  "The whole version": "เวอร์ชันทั้งหมด",
  "Ask its approvers": "ขอผู้อนุมัติ",
  "What you asked for": "สิ่งที่คุณขอ",
  "Version {serial}, asked for {when}: {outcome}.": "เวอร์ชัน {serial} ขอเมื่อ {when}: {outcome}",
};
