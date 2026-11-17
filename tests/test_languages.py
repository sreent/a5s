"""Thai alongside English (core/languages.py): the language each person reads, from the
directory or their own choice; each agent told to answer them in it; the studio's and the web
chat's own words in it; and Ocean's IBM Plex Sans Thai for its letters."""

import json
import re
from dataclasses import replace
from pathlib import Path

import httpx
from playwright.sync_api import expect

from a5s import db
from a5s.config import Prices
from a5s.contract import parse_settings
from a5s.core import languages
from conftest import ROOT, accessible

STUDIO = ROOT / "studio" / "src"


def as_person(approving: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})


def reads(stack, person: str, language: str) -> None:
    """Someone reads a language, as the directory says."""
    found = stack.gateway.scenario._people[person]
    stack.gateway.scenario._people[person] = replace(found, language=language)


def told(stack) -> str:
    """Everything the model was sent, for what a5s told it."""
    return json.dumps([r["body"] for r in stack.model.requests], ensure_ascii=False)


def test_the_language_someone_reads_is_theirs_then_the_directorys_then_english(stack):
    ana = stack.gateway.scenario.person("ana")
    with db.transaction(stack.admin) as conn:
        assert languages.of(conn, ana) == "en"
        reads(stack, "ana", "th-TH")
        assert languages.of(conn, stack.gateway.scenario.person("ana")) == "th"
        languages.choose(conn, ana, "en", stack.gateway.clock())  # theirs comes first
        assert languages.of(conn, stack.gateway.scenario.person("ana")) == "en"
    assert languages.primary("") == "en" and languages.primary("zh_Hant") == "zh"
    assert languages.told("en") is None
    assert languages.told("ja").startswith("They read Japanese: write to them in Japanese")


def test_an_agent_answers_each_person_in_the_language_they_read(stack):
    stack.model.reply("Hello.")
    stack.say("hello")  # Ana reads English: the agent is told nothing of it
    assert "They read" not in told(stack)
    reads(stack, "ana", "th")
    stack.model.reply("สวัสดีค่ะ")
    stack.say("hello again")
    assert "They read Thai: write to them in Thai, unless they write to you in another language" \
        in json.dumps(stack.model.requests[-1]["body"])


def test_someone_chooses_the_language_they_read_on_their_own_page(stack, approving, provider):
    you = as_person(approving, provider, "ana", "GET", "/studio/api/you").json()
    assert you["language"] == "en"
    assert you["languages"] == [{"code": "en", "name": "English"}, {"code": "th", "name": "ไทย"}]
    chosen = as_person(approving, provider, "ana", "POST", "/studio/api/you/language",
                       {"language": "th"})
    assert chosen.status_code == 200 and chosen.json() == {"language": "th"}
    shell = as_person(approving, provider, "ana", "GET", "/shell/api").json()
    assert shell["language"] == "th"
    names = {p["page"]: (p["name"], p["group"]) for p in shell["pages"]}
    assert names["studio"] == ("สตูดิโอ", "สร้าง") and names["spending"] == ("ค่าใช้จ่าย", "กำกับดูแล")
    assert as_person(approving, provider, "ben", "GET", "/shell/api").json()["language"] == "en"
    wrong = as_person(approving, provider, "ana", "POST", "/studio/api/you/language",
                      {"language": "fr"})
    assert wrong.status_code == 400 and "English and ไทย" in wrong.json()["detail"]
    with db.transaction(stack.admin) as conn:  # one of their preferences, in their export
        [row] = conn.execute("select value from preferences where person = 'ana' "
                             "and name = 'language'").fetchall()
    assert row["value"] == "th"
    [noted] = [e for e in stack.ledger() if e.get("action") == "choose-language"]  # it changes
    assert noted["acts_for"] == ["ana"] and noted["args"] == {"language": "th"}  # what agents
    # are told, as connecting an account does, so the ledger keeps it


def test_the_catalogue_has_every_word_the_studio_puts_through_it():
    said: set[str] = set()
    catalogues = [STUDIO / "i18n" / "th.ts", *sorted((STUDIO / "i18n" / "th").glob("*.ts"))]
    for path in [*STUDIO.rglob("*.tsx"), *STUDIO.rglob("*.ts")]:
        if path.name == "i18n.ts" or path in catalogues:
            continue  # the catalogue, and its own example, in a comment
        said |= {m.group(1).replace('\\"', '"')
                 for m in re.finditer(r'\bt\(\s*"((?:[^"\\]|\\.)*)"', path.read_text())}
    catalogue = "\n".join(path.read_text() for path in catalogues)
    keys = {m.group(1).replace('\\"', '"')
            for m in re.finditer(r'^\s*"((?:[^"\\]|\\.)*)":', catalogue, re.MULTILINE)}
    assert said, "the studio says nothing through t()"
    assert sorted(said - keys) == [], "words the studio says with no Thai"
    assert sorted(keys - said) == [], "Thai for words the studio no longer says"
    for key in keys:  # each keeps its {name}s
        thai = re.search(re.escape(json.dumps(key, ensure_ascii=False)) + r':\s*\n?\s*"((?:[^"\\]|\\.)*)"',
                         catalogue)
        assert thai, key
        assert sorted(re.findall(r"\{(\w+)\}", key)) == sorted(re.findall(r"\{(\w+)\}", thai.group(1))), key


def test_the_studio_and_the_web_chat_speak_thai_to_those_who_read_it(stack, approving, provider,
                                                                    browser):
    reads(stack, "ana", "th")
    assert not stack.settle(spending={"agents": {"assistant": 5}}, signers=("ana", "priya")).refused
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("h1 >> text=ยินดีต้อนรับ", timeout=30000)
    assert page.get_attribute("html", "lang") == "th"
    assert "สตูดิโอ" in page.inner_text("#pages") and "ค่าใช้จ่าย" in page.inner_text("#pages")
    # Thai letters in Ocean's Plex Sans Thai, loaded for them alone
    for _ in range(100):
        if "IBM Plex Sans Thai" in page.evaluate(
                "[...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family).join()"):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("the page drew Thai without Plex Sans Thai")
    accessible(page)
    page.goto(f"{approving}/studio/spending")
    page.wait_for_selector("#agent-assistant .cost-bars", timeout=30000)
    assert page.inner_text("h1") == "ค่าใช้จ่าย" and "UTC" in page.inner_text("#utc")
    assert "งบประมาณ" in page.inner_text("#agent-assistant")
    accessible(page)
    # Back to English on their own page, and the studio speaks it at once
    page.goto(f"{approving}/studio/you")
    page.wait_for_selector("#language input[value=en]", timeout=30000)
    assert page.eval_on_selector("#language label", "el => getComputedStyle(el).display") == "flex"
    page.check("#language input[value=en]")
    page.wait_for_selector("h1 >> text=What you may do", timeout=30000)
    expect(page.locator("#language input[value=en]")).to_be_focused(timeout=10000)  # the studio drawn again in it, the keyboard on the choice
    assert page.get_attribute("html", "lang") == "en"
    page.check("#language input[value=th]")
    page.wait_for_selector("h1 >> text=สิ่งที่คุณทำได้", timeout=30000)
    # The web chat's own words, in Thai too
    chat = browser.new_page()
    chat.goto(f"{approving}/chat/")
    chat.wait_for_selector("html[lang=th]", state="attached", timeout=30000)
    assert chat.get_attribute("#text", "placeholder").startswith("พิมพ์ถึงเอเจนต์")
    assert chat.inner_text("#compose button.primary") == "ส่ง"
    accessible(chat)


def test_ocean_gives_thai_its_own_faces_for_its_letters_alone():
    tokens = (ROOT / "src" / "a5s" / "core" / "webchat" / "ocean" / "css" / "tokens.css").read_text()
    faces = re.findall(r'@font-face \{ font-family: "IBM Plex Sans Thai";[^}]*\}', tokens)
    assert len(faces) == 4 and all("unicode-range: U+0E01-0E5B" in f for f in faces)
    assert '--font-sans: "IBM Plex Sans", "IBM Plex Sans Thai",' in tokens
    assert ":root:lang(th) { line-height: 1.7; }" in tokens
    for weight in (400, 500, 600, 700):
        assert Path(ROOT / "src" / "a5s" / "core" / "webchat" / "ocean" / "fonts" /
                    f"plex-sans-thai-{weight}.woff2").read_bytes()[:4] == b"wOF2"
    assert parse_settings(b"serial: 1\n").instances == ()  # the settings don't hold a language


def test_a5s_writes_its_own_words_in_the_language_someone_reads(stack, approving, provider):
    from a5s.core import administration, dependencies, feedback, home, words
    for english, thai in words.TH.items():  # each keeps its English's {name}s
        assert sorted(re.findall(r"\{(\w+)\}", english)) == sorted(re.findall(r"\{(\w+)\}", thai)), english
    for kept in (*home.MAY.values(), home.TEAM_MAY, feedback.NOTED, *administration.SCOPED.values(),
                 *dependencies.SAYS.values(), *dependencies.ABOUT.values(),
                 *dependencies.STATUS.values()):  # and the map's, every edge and thing on it
        assert kept in words.TH, kept  # what a role lets someone do, and the like, has its Thai
    owns = "the owner of {part} hasn't approved it"  # a template the module that writes it passes
    assert words.say("th", owns, part="billing") == "เจ้าของ billing ยังไม่ได้อนุมัติ"
    assert words.say("en", owns, part="billing") == "the owner of billing hasn't approved it"
    assert words.say("th", "something a5s has no Thai for") == "something a5s has no Thai for"
    # and no sentence is matched after it's written whole (round 14's deferral)
    assert not hasattr(words, "translated") and not hasattr(words, "PATTERNS")
    # On their home and their own page, in Thai, once they read it
    stack.gateway.models["fake"] = replace(stack.gateway.models["fake"], prices=Prices(2000.0, 8000.0))
    assert not stack.settle(spending={"agents": {"assistant": 0.05}}, signers=("ana", "priya")).refused
    stack.model.reply("Hello.")
    stack.say("hello")
    for person in ("ana", "priya"):  # Priya owns the assistant, so its budget is hers to hear of
        as_person(approving, provider, person, "POST", "/studio/api/you/language", {"language": "th"})
    waiting = as_person(approving, provider, "priya", "GET", "/studio/api/home").json()["waiting"]
    [spent] = [w for w in waiting if w["kind"] == "spending"]
    assert spent["what"].startswith("assistant ใช้ไปแล้ว")  # past the budget it set, never
    assert "เกินงบ\u2060ประมาณที่ตั้งไว้" in spent["what"]  # read as the overage (round 14)
    assert spent["why"] == ["คุณเป็นเจ้าของ assistant"]
    roles = as_person(approving, provider, "ana", "GET", "/studio/api/you").json()["roles"]
    owner = next(r for r in roles if r["role"] == "part-owner:billing")
    assert owner["name"] == "เจ้าของ billing" and owner["may"].startswith("อนุมัติอินสแตนซ์ที่ทำงานใน billing")
    # Ben reads English still
    ben = as_person(approving, provider, "ben", "GET", "/studio/api/you").json()["roles"]
    assert all(not re.search(r"[฀-๿]", r["may"]) for r in ben)


def test_a_moment_is_written_as_its_reader_reads_one():
    """Round 14 (E-L3): until when, as someone reads a moment: in Thai by its month's Thai name
    and the Buddhist era's year, and in their own time zone, which it names."""
    from datetime import UTC, datetime
    at = datetime(2026, 11, 18, 7, 8, tzinfo=UTC)
    assert languages.when(at, "en") == "18 Nov 2026, 07:08 UTC"
    assert languages.when(at, "en", "Asia/Bangkok") == "18 Nov 2026, 14:08 UTC+07"
    assert languages.when(at, "th", "Asia/Bangkok") == "18 พ.ย. 2569 เวลา 14:08 น. (UTC+07)"
    assert languages.when(at, "en", "Europe/London") == "18 Nov 2026, 07:08 GMT"
    assert languages.when(at, "en", "Not/A_Zone") == "18 Nov 2026, 07:08 UTC"  # as UTC


def test_a_group_reads_a5s_in_the_language_everyone_in_it_reads(stack):
    """Round 14 (E-L4): a5s writes to a group chat in the language its members all read, if
    they all read one, and in English if not."""
    people = stack.gateway.scenario
    ana, ben = people.person("ana"), people.person("ben")
    with db.transaction(stack.admin) as conn:
        assert languages.shared(conn, [ana, ben]) == "en"
        for who in (ana, ben):
            languages.choose(conn, who, "th", stack.gateway.clock())
        assert languages.shared(conn, [ana, ben]) == "th"
        assert languages.shared(conn, [ana, ben, None]) == "en"  # someone a5s doesn't know
        languages.choose(conn, ben, "en", stack.gateway.clock())
        assert languages.shared(conn, [ana, ben]) == "en"


def test_a_version_of_the_settings_reads_whole_in_thai():
    """Round 14's deferral (E-M5): what a version changes and the whole of it, in Thai for whoever
    reads Thai, each name, level and figure as the settings write it; in English as before."""
    from a5s.contract import Person
    from a5s.core import approvals
    people = {"ana": Person(id="ana", name="Ana Silva", team="finance")}
    before = parse_settings(b"serial: 1\ninstances:\n  assistant-finance: {definition: assistant, "
                            b"serves: [ana], parts: [billing], level: 1, owner: ana}\n")
    after = parse_settings(b"serial: 2\nlimits:\n  change-due-date: {per_run: 3}\nspending:\n"
                           b"  agents: {assistant: 30}\n  currency: GBP\ninstances:\n"
                           b"  assistant-finance: {definition: assistant, serves: [ana, 'team:finance'], "
                           b"parts: [billing, orders], level: 1, owner: ana, hands_to: [finance]}\n")
    en = [c["text"] for c in approvals.changes(before, after, {}, people.get)]
    th = [c["text"] for c in approvals.changes(before, after, {}, people.get, "th")]
    assert len(th) == len(en) and not any(re.search(r"[ก-๙]", e) for e in en), en
    assert all(re.search(r"[ก-๙]", t) for t in th), th  # each line, not a word of it English alone
    assert "ขีดจำกัดของ change-due-date เปลี่ยนเป็น 3 รายการต่อการทำงานหนึ่งครั้ง" in th
    assert any(t.startswith("งบประมาณของ assistant เปลี่ยนเป็น GBP 30 ต่อเดือน") for t in th), th
    assert "assistant-finance ให้บริการ ทุกคนในทีม finance ด้วย" in th
    assert "assistant-finance ส่งต่อการสนทนาให้คนในทีม financeได้" in " ".join(th)
    whole = approvals.described(after, {}, people.get, "th")
    assert all(re.search(r"[ก-๙]", line) for line in whole), whole
    assert whole[1].startswith("assistant-finance: assistant ทำงานใน billing ที่ระดับ 1 และ orders "
                               "ที่ระดับ 1 ให้บริการ Ana Silva และ ทุกคนในทีม finance ดูแลโดย Ana Silva")
