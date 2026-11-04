"""Round 5, reviewer c: the conversation a5s keeps, as the person and the agent see it.

- a5s writes escalations, and its own reminders, as the agent's bot, in the person's
  conversation with the agent, but never notes them in the conversation it keeps. So when
  the person answers one, the agent has no idea what they mean.
- The summary run is shown each turn with the day it was said, then refused for writing a
  date "nobody said" when it uses one of them, so the summary isn't kept, the turns that
  no longer fit reach no run, and every later run pays for another try.
"""

import json

from a5s import db
from a5s.core import registry, topics
from a5s.services import context


def sent_to_model(stack, request: int = -1) -> str:
    return "\n".join(str(m["content"]) for m in stack.model.requests[request]["body"]["messages"])


def test_an_escalation_a5s_wrote_in_the_agents_chat_is_in_the_conversation(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")  # she talks to the assistant, so a5s writes to her there
    stack.suspend(by="ben")  # nobody chases Ben, so his overdue Q-1002 goes up his line
    stack.at("2026-11-09T09:30:00+00:00")
    stack.scheduler().work_due()
    [escalated] = [m["text"] for m in stack.inbox("ana") if m["text"].startswith("Q-1002")]
    with db.transaction(stack.cfg.database_url) as conn:  # Ben resumes it
        assert not registry.set_status(conn, "assistant-finance", by="ben", suspend=False)
    stack.model.reply("I'm not sure what you mean.")
    stack.say("Why did you send me that just now? What do you want me to do?")
    assert "You're next in their reporting line" in sent_to_model(stack), (
        "a5s wrote this to Ana in her conversation with the assistant, but the assistant's "
        f"next run was never told it: {escalated!r}")


def test_a_summary_may_say_when_something_was_said(stack):
    with db.transaction(stack.admin) as conn:
        context.add_turn(conn, person="ana", agent="assistant", role="person",
                         content="Northwind wants the corrected invoice sent to their Leeds office.")
        context.add_turn(conn, person="ana", agent="assistant", role="agent", content="Noted.")
        for n in range(5):
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content=f"Note {n}: " + "the weekly sync went through invoices. " * 25)
    stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters
    stack.model.reply("Hello, Ana.")
    stack.model.reply("{}")  # replaced below, once the task shows the day it was said
    stack.model.on_request = lambda n: n == 2 and stack.model.script.__setitem__(0, (json.dumps({
        "decisions": [f"On {day}, Ana said Northwind wants the corrected invoice sent to Leeds."
                      for day in [_day_in(stack.model.requests[-1])]],
        "commitments": [], "open_questions": []}), []))
    stack.say("Hello")
    asked = stack.model.requests[-1]["body"]["messages"]
    assert asked[0]["content"] == topics.SUMMARY
    with db.transaction(stack.admin) as conn:
        kept = conn.execute("select * from summaries").fetchall()
        closed = conn.execute("select outcome from runs where trigger->>'kind' = 'summary'"
                              ).fetchall()
    assert kept, ("a5s showed the summary run the day each turn was said, then refused its "
                  f"summary for saying it: {closed}")


class Chat:
    """A stand-in for Matrix: it records what a5s sends, and as which agent's bot."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, reply_to: dict, text: str) -> None:
        self.sent.append((reply_to.get("bot", ""), text))

    def user_of(self, person) -> str:
        return f"@{person.id}:a5s.test"

    def start(self, user: str, agent: str) -> dict:
        return {"room": f"!{agent}:{user}", "bot": f"@a5s-{agent}:a5s.test"}


def test_a_digest_from_several_agents_isnt_sent_as_one_of_them(stack, monkeypatch):
    stack.with_watcher()
    records = stack.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
    chat = Chat()
    stack.gateway.matrix = chat  # Matrix is on, and Ana last wrote to the watcher there
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into inbound (id, channel, source_id, person, agent, text, reply_to, "
                     "answered_at) values (gen_random_uuid(), 'matrix', '$1', 'ana', 'watcher', "
                     "'Thanks', %s, now())",
                     (json.dumps({"room": "!w:a5s.test", "bot": "@a5s-watcher:a5s.test"}),))
    stack.at("2026-11-02T09:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")  # the assistant's chases
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.model.reply("Ana, you have Q-1001, waiting on the customer.")  # the watcher's reports
    stack.model.reply("Ben, you have Q-1002, waiting on finance.")
    stack.scheduler().work_due()
    [(bot, text)] = [s for s in chat.sent if "Q-1001 is due on Wednesday" in s[1]]
    assert bot == "@a5s-assistant:a5s.test", (
        "Ana's digest, with the assistant's chase in it, arrives as the watcher's bot, in her "
        "chat with the watcher, so her answer to the chase goes to the watcher, which keeps no "
        f"reminders and never saw the chase: {text!r}")


def _day_in(request: dict) -> str:
    """The day a5s wrote on the first turn it asked the summary run to fold, such as 31 Oct."""
    task = request["body"]["messages"][1]["content"]
    stamp = task.split("oldest first:\n[", 1)[1].split("]", 1)[0]  # such as Sat 31 Oct 2026
    _, day, month, _ = stamp.split()
    return f"{day} {month}"
