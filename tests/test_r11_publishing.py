"""Round 11, reviewer C (C-2): a publish takes back nothing merged since its draft began. A
draft's first publish set the agent's folder on its branch to the draft's files alone, so a
change merged to the agent since the draft began, a security fix among them, was reverted by its
pull request, whose words said nothing of it. Now a draft keeps the folder it began from, and a
publish merges it file by file with what's merged: what only the branch changed stays, what only
the draft changed comes in, and where both changed a file, the publish is refused."""

from a5s.core import publishing
from test_drafts import as_
from test_publishing import github, published  # noqa: F401 - a fixture

SKILL = "agents/assistant/skills/refunds/SKILL.md"


def merged_since(hub, *, agents_md: str = "\nMERGED-SINCE.\n") -> None:
    """A colleague's change to the assistant, reviewed and merged on main meanwhile."""
    main = hub.files("main")
    merged = {**main, SKILL: "---\nname: refunds\ndescription: How refunds go.\n---\nAsk billing.\n",
              "agents/assistant/AGENTS.md": main["agents/assistant/AGENTS.md"] + agents_md}
    hub.refs["heads/main"] = hub._commit(hub._tree(merged), [hub.refs["heads/main"]],
                                         "Add the refunds skill", "omar-gh")


def test_a_publish_keeps_what_was_merged_since_its_draft_began(
        stack, github, approving, provider):  # noqa: F811
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    merged_since(github)
    files = {**draft["files"], "agent.yaml": draft["files"]["agent.yaml"].replace(
        "Keeps one conversation", "Keeps a conversation")}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    done = published(priya, github, draft["id"], login="priya-gh")
    there = github.files(done["branch"])
    assert SKILL in there  # what only main changed stays
    assert "MERGED-SINCE." in there["agents/assistant/AGENTS.md"]
    assert "Keeps a conversation" in there["agents/assistant/agent.yaml"]  # and hers comes in


def test_a_publish_that_would_take_back_a_change_both_made_is_refused(
        stack, github, approving, provider):  # noqa: F811
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    merged_since(github)
    files = {**draft["files"], "AGENTS.md": draft["files"]["AGENTS.md"] + "\nPRIYA'S OWN.\n"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    asked = priya("POST", f"/studio/api/drafts/{draft['id']}/publish").json()
    github.grant(asked["user_code"], "priya-gh")
    done = priya("GET", f"/studio/api/publishes/{asked['id']}").json()
    assert done["status"] == "refused" and "AGENTS.md changed on main" in done["problem"]
    assert github.pulls == []


def test_a_merge_keeps_each_side_where_the_other_left_a_file_alone():
    base = {"a": "1", "b": "1", "c": "1", "d": "1"}
    merged = {"a": publishing.blob("1"), "b": publishing.blob("2"), "c": publishing.blob("1"),
              "e": publishing.blob("new there")}  # b changed there, d gone there, e added there
    draft = {"a": "2", "b": "1", "c": "1", "d": "1"}  # a changed in the draft
    result, conflicts = publishing.merge(base, merged, draft)
    assert conflicts == [] and result["a"] == "2" and result["c"] == "1"
    assert result["b"] == publishing.Kept(publishing.blob("2"))
    assert result["e"] == publishing.Kept(publishing.blob("new there")) and "d" not in result
    _, both = publishing.merge(base, merged, {**draft, "b": "3"})
    assert both == ["b"]
