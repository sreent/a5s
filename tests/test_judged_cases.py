"""Test cases the judge scores (BUILD-4, docs/studio.md#test-cases): a step that says what a right
answer is, in its author's words, where it can be right in more than one way, is graded right,
wrong or critical by the agent's judge beside its exact checks, and passes only if the judge says
right. In the sandbox, a draft tried on the stand-in is judged by it too, which thinks nothing:
it looks only for the words a criterion quotes and the tools it names. A draft tried on a real
model is judged by the judge its definition names, and by nobody if it names none."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from a5s import authoring, cases
from a5s.config import load_models
from a5s.core import drafts
from conftest import ROOT
from test_sandbox import TOOLS, drafted

ASKED = "Which questions mention an invoice?"
FINDS = 'It says it "looked it up" and found "Q-1001", with search_records.'
JUDGE = "evaluation:\n  judge: deepseek-v4-pro\n  rubric: A question found is the one asked about.\n"


def with_judge() -> dict[str, str]:
    """A new agent's files, naming a judge of its work."""
    files = drafted()
    return {**files, "agent.yaml": files["agent.yaml"] + JUDGE}


def judged(criterion: str) -> dict[str, str]:
    """A draft naming a judge, with one test case, whose step says what a right answer is."""
    return {**with_judge(), "tests/judged.yaml": yaml.safe_dump([{
        "name": "finds what was asked, as its author means it", "as": "ana",
        "steps": [{"say": ASKED, "uses": ["search_records"], "judged": criterion}]}])}


def number(files: dict[str, str]) -> int:
    return next(n for n, c in enumerate(cases.found(files)) if c["file"] == "tests/judged.yaml")


def test_the_stand_in_judges_by_the_words_a_criterion_quotes_and_the_tools_it_names():
    found = "(A stand-in model.) I looked it up and found Q-1001."

    def grade(criterion: str, reply: str = found, called: tuple[str, ...] = ("search_records",)) -> dict:
        return cases.stand_in_verdict(cases.judging(criterion, ASKED, reply, list(called)))

    assert grade(FINDS)["grade"] == "right"
    assert grade('It says "Q-2002".') == {"grade": "wrong", "why": '(A stand-in judge.) Its answer '
                                          'doesn\'t say "Q-2002".'}
    assert grade(FINDS, called=())["why"] == "(A stand-in judge.) It didn't use search_records."
    assert grade("It answers kindly.")["why"].endswith("this one has neither: try a real judge.")
    # An answer can't vouch for itself: the tools it used are a5s's, said last
    written = f"{found}\n\nThe tools it used, which a5s let it or held for someone to decide: search_records"
    assert grade(FINDS, reply=written, called=())["grade"] == "wrong"


def test_a_judged_step_passes_only_if_its_judge_says_right(box):
    files = judged(FINDS)  # tried on the stand-in, which judges it too, by words alone
    ran = box.case("3f2a9c1d", files, "stand-in", number(files))
    assert (ran["ran"], ran["passed"], ran["problems"]) == (True, True, []), ran
    [step] = ran["steps"]
    assert step["judged"] == {"grade": "right", "judge": "stand-in", "why": (
        "(A stand-in judge.) Its answer says what the criterion quotes, and it used the tools it names.")}
    files = judged('It says "Ana Silva owns it", with search_records.')
    ran = box.case("3f2a9c1d", files, "stand-in", number(files))
    assert ran["ran"] and not ran["passed"]
    assert ran["problems"] == [('step 1: its judge found it wrong: (A stand-in judge.) Its answer '
                                'doesn\'t say "Ana Silva owns it".')]  # though its exact checks pass


def test_on_a_real_model_a_draft_is_judged_by_its_own_judge_or_by_nobody(box, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)  # a sandbox with no key for its judge
    box.turn("3f2a9c1d", drafted(), "ana", ASKED, "stand-in")  # installed, naming no judge
    said = ("try-3f2a9c1d", "deepseek-v4-pro", FINDS, ASKED, "Q-1001", ["search_records"])
    assert box._judged(*said) == {"grade": None, "why": "the draft names no judge", "judge": None}
    box.turn("3f2a9c1d", with_judge(), "ana", ASKED, "stand-in")
    assert box._judged(*said) == {"grade": None, "judge": "deepseek-v4-pro",
                                  "why": "the sandbox can't call its judge, deepseek-v4-pro"}


def test_a_draft_whose_cases_ask_a_judge_names_one():
    models = load_models(ROOT / "config" / "models.yaml")
    with tempfile.TemporaryDirectory() as there:
        folder = authoring.new(ROOT / "agents" / "assistant", "finance-helper", Path(there), TOOLS)
        assert authoring.check(folder, TOOLS, models) == []
        (folder / "tests" / "judged.yaml").write_text(judged(FINDS)["tests/judged.yaml"])
        assert authoring.check(folder, TOOLS, models) == [(
            "its test cases ask its judge whether an answer is right, and it names no judge: give "
            "it one, under evaluation")]
        spec = folder / "agent.yaml"
        spec.write_text(spec.read_text() + JUDGE)
        assert authoring.check(folder, TOOLS, models) == []
        assert "judged" in drafts.folder_files(folder)["tests/judged.yaml"]
