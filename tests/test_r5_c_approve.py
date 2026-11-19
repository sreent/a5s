"""Round 5, reviewer c: what the approval page tells an approver once they've approved.

A version that has an instance work in two parts needs both parts' owners. After the first
approves, the page says "You approved version N. a5s puts it in force within a minute."
(studio/src/pages/Approve.tsx), and on a later visit "You've approved it. a5s puts it in force
within a minute.", beside the line that says it still waits for the other owner. Nothing
goes in force until the other owner approves, and the answer the page gets from the core
doesn't say what's still missing."""

from pathlib import Path

from test_approvals import decide, look, proposed, sign_in

PAGE = Path(__file__).resolve().parents[1] / "studio" / "src" / "pages" / "Approve.tsx"


def test_an_approver_hears_what_a_version_still_waits_for(stack, approving, provider):
    asked = proposed(stack, serves=["ana", "ben", "omar"], parts=["billing", "orders"])
    assert sorted(asked["asked"]) == ["ana", "omar"]
    token, salt = sign_in(approving, provider, asked["digest"], person="ana")
    approved = decide(approving, asked["digest"], token, salt)
    assert approved.status_code == 200
    stack.scheduler().apply_approved()
    seen = look(approving, provider, asked["digest"], person="ana")  # as the studio reads it
    assert seen["status"] == "waiting" and seen["you_approved"]
    assert seen["needs"] == ["the owner of orders hasn't approved it"]  # not in force, rightly
    assert "needs" in approved.json(), (
        "the approval's answer doesn't say the version still waits for Omar, so the page "
        f"tells Ana it goes in force within a minute: {approved.json()}")


def test_the_page_says_in_force_within_a_minute_only_when_nothing_more_is_missing():
    script = PAGE.read_text(encoding="utf-8")
    words = "puts it in force within a minute"
    assert script.count(words) == 1, f"the page says {words!r} other than where it weighs what's missing"
    weighs = script[script.index("const missing = (needs: string[]) => (needs.length"):]
    assert words in weighs[:weighs.index(");\n")], (
        "the page says it goes in force within a minute whatever it still needs")
