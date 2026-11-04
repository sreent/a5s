"""Round 5, reviewer a: a version of the settings someone writes in the settings app is read
as YAML, and nothing checks the types or the size of what it holds before code works with it.

Any part owner or instance approver can use the settings app. What they ask for is stored,
and the gateway works on it in its settings sweep, in the same transaction that applies the
versions everyone has approved.
"""

import yaml

from test_approvals import CHEN_TOO, decide, proposed, serves, sign_in
from test_settings_app import api


def in_force(url: str, provider, person: str = "ana") -> dict:
    return yaml.safe_load(api(url, provider, "/settings/api", person=person).json()["in_force"]["text"])


def test_a_request_with_a_level_in_words_doesnt_stop_approved_settings_being_applied(
        stack, approving, provider):
    # Omar owns orders, so he may use the settings app. He asks for a version whose level is
    # a string, which YAML gives for a quoted number.
    edited = in_force(approving, provider, "omar")
    edited["instances"]["assistant-finance"]["level"] = "1"
    api(approving, provider, "/settings/api/requests", person="omar", text=yaml.safe_dump(edited))

    # Meanwhile a version Ana approves properly waits to be applied.
    asked = proposed(stack, serves=CHEN_TOO)
    token, salt = sign_in(approving, provider, asked["digest"])
    assert decide(approving, asked["digest"], token, salt).status_code == 200

    with stack.client() as c:
        swept = c.post("/settings/sweep")
    assert swept.status_code == 200, swept.text  # today: 500, every minute, for good
    assert serves(stack) == CHEN_TOO  # today: never applied


def test_a_request_with_people_of_two_kinds_doesnt_stop_the_sweep(stack, approving, provider):
    edited = in_force(approving, provider, "omar")
    edited["instances"]["assistant-finance"]["serves"] = ["ana", "ben", "chen", 7]
    api(approving, provider, "/settings/api/requests", person="omar", text=yaml.safe_dump(edited))
    with stack.client() as c:
        swept = c.post("/settings/sweep")
    assert swept.status_code == 200, swept.text


def test_a_small_request_doesnt_make_the_core_build_a_huge_one(stack, approving, provider):
    """YAML aliases nest the same list in itself: str() of it is 2**(depth+1) times the leaf.
    Under 2 KB asked for here comes back as about 24 MB; each level doubles it, so a depth
    of 30 is about 100 GB, built while holding the GIL, in the channels' endpoint as it
    reviews or records the request, and in the gateway's sweep if it's recorded."""
    depth = 17
    leaf = "x" * 40
    anchors = [f"  l0: &l0 [{leaf}, {leaf}]"] + [
        f"  l{i}: &l{i} [*l{i - 1}, *l{i - 1}]" for i in range(1, depth + 1)]
    body = yaml.safe_dump({k: v for k, v in in_force(approving, provider).items()
                           if k != "data_class"})
    text = "bomb:\n" + "\n".join(anchors) + f"\ndata_class: *l{depth}\n" + body
    assert len(text) < 2000
    reviewed = api(approving, provider, "/settings/api/review", text=text)
    assert len(reviewed.content) < 100_000, f"{len(reviewed.content):,} bytes back"  # today: ~25 MB
    assert reviewed.json()["problems"], "a class of data that isn't a word should be refused"

