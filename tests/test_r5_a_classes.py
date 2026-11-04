"""Round 5, reviewer a: a field of a class of its own reaches a model not approved for it.

The settings may name any field of the records as a class of its own. The core hands such a
field to the model as a handle in what tools return, and leaves it out of a record's fields
in briefs and reports. But a record's title isn't among its fields there: briefs, reports and
the tasks for chases put it in as it is. The sample's fake model is approved for synthetic
data alone.
"""

from test_classes import resettle

TITLE = "Invoice sent to the wrong address"  # Q-1001's title


def test_a_classified_title_isnt_in_a_case_brief(stack):
    resettle(stack, classified={"title": "confidential"})
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("Tell me about Q-1001")
    tool_result = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert TITLE not in tool_result  # what the tool returned holds a handle for it
    assert TITLE not in str(stack.model.requests)  # today: the case's brief holds it


def test_a_classified_title_isnt_in_a_chase(stack):
    resettle(stack, classified={"title": "confidential"})
    stack.at("2026-11-02T09:30:00+00:00")  # half of Q-1001's time has passed: Ana is reminded
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    assert TITLE not in str(stack.model.requests)


def test_a_classified_title_isnt_in_a_report(stack):
    stack.with_watcher(serves=("ana",))
    resettle(stack, classified={"title": "confidential"})
    stack.at("2026-10-29T09:30:00+00:00")  # the watcher's first morning
    stack.model.reply("Ana, you have Q-1001 open.")
    stack.scheduler().work_due()
    assert stack.model.requests and TITLE not in str(stack.model.requests)
