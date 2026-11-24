"""The language each person reads (core/languages.py): the one the directory gives them, or
English; each agent told to answer them in it, whatever it is; and a5s's own words, on its pages
and in chat, in English alone. Ocean, the look a5s shares, still draws Thai letters, which people
and agents may write, in faces of its own."""

import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx

from a5s.contract import parse_settings
from a5s.core import languages, words
from conftest import ROOT


def reads(stack, person: str, language: str) -> None:
    """Someone reads a language, as the directory says."""
    found = stack.gateway.scenario._people[person]
    stack.gateway.scenario._people[person] = replace(found, language=language)


def told(stack) -> str:
    """Everything the model was sent, for what a5s told it."""
    return json.dumps([r["body"] for r in stack.model.requests], ensure_ascii=False)


def test_the_language_someone_reads_is_the_directorys_or_english(stack):
    assert languages.of(stack.gateway.scenario.person("ana")) == "en"
    reads(stack, "ana", "ja-JP")
    assert languages.of(stack.gateway.scenario.person("ana")) == "ja"
    assert languages.primary("") == "en" and languages.primary("zh_Hant") == "zh"
    assert languages.told("en") is None
    assert languages.told("ja").startswith("They read Japanese: write to them in Japanese")


def test_an_agent_answers_each_person_in_the_language_they_read(stack):
    stack.model.reply("Hello.")
    stack.say("hello")  # Ana reads English: the agent is told nothing of it
    assert "They read" not in told(stack)
    reads(stack, "ana", "ja")
    stack.model.reply("こんにちは")
    stack.say("hello again")
    assert ("They read Japanese: write to them in Japanese, unless they write to you in another "
            "language") in json.dumps(stack.model.requests[-1]["body"])


def test_a5s_s_own_words_are_in_english_whatever_someone_reads(stack, approving, provider):
    """Its pages and notes speak English alone, so nobody chooses another for them, and the
    sidebar and someone's own page name no language."""
    reads(stack, "ana", "ja")
    signed = {"Authorization": f"Bearer {provider.id_token(person='ana')}"}
    shell = httpx.get(f"{approving}/shell/api", timeout=30, headers=signed).json()
    you = httpx.get(f"{approving}/studio/api/you", timeout=30, headers=signed).json()
    assert shell["pages"] and "language" not in shell
    assert you["id"] == "ana" and "language" not in you and "languages" not in you
    chose = httpx.post(f"{approving}/studio/api/you/language", json={"language": "ja"},
                       timeout=30, headers=signed)
    assert chose.status_code in (404, 405)
    assert words.say("ja", "{first} and {last}", first="Ana", last="Ben") == "Ana and Ben"
    assert not list((ROOT / "studio" / "src").glob("i18n/**/*.ts"))  # no catalogue beside


def test_ocean_draws_thai_letters_in_faces_of_its_own():
    """What people and agents write may be in Thai, though a5s's own words aren't: Ocean draws
    those letters alone in IBM Plex Sans Thai."""
    tokens = (ROOT / "src" / "a5s" / "core" / "webchat" / "ocean" / "css" / "tokens.css").read_text(encoding="utf-8")
    faces = re.findall(r'@font-face \{ font-family: "IBM Plex Sans Thai";[^}]*\}', tokens)
    assert len(faces) == 4 and all("unicode-range: U+0E01-0E5B" in f for f in faces)
    assert '--font-sans: "IBM Plex Sans", "IBM Plex Sans Thai",' in tokens
    for weight in (400, 500, 600, 700):
        assert Path(ROOT / "src" / "a5s" / "core" / "webchat" / "ocean" / "fonts" /
                    f"plex-sans-thai-{weight}.woff2").read_bytes()[:4] == b"wOF2"
    assert parse_settings(b"serial: 1\n").instances == ()  # the settings don't hold a language


def test_a_moment_is_written_in_its_readers_own_time_zone():
    """Round 14 (E-L3): until when, as someone reads a moment: in their own time zone, which it
    names."""
    at = datetime(2026, 11, 18, 7, 8, tzinfo=UTC)
    assert languages.when(at) == "18 Nov 2026, 07:08 UTC"
    assert languages.when(at, "Asia/Bangkok") == "18 Nov 2026, 14:08 UTC+07"
    assert languages.when(at, "Europe/London") == "18 Nov 2026, 07:08 GMT"
    assert languages.when(at, "Not/A_Zone") == "18 Nov 2026, 07:08 UTC"  # as UTC
