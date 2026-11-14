"""Urgent messages: what a5s and its agents write to someone at once, when they aren't
waiting for it, such as an escalation.

Up to five a day go at once, in the person's own day, across all the agents. After that, they
wait, and go together once the oldest has waited an hour, in their working hours, so urgent
stays urgent without becoming noise. A batch of one goes as itself, from its agent; more go as
one message from a5s, each under its agent. Answers to people's own messages aren't urgent
messages, since they're waiting for them, and neither are reminders they asked for at a
particular time, nor what waits for their digest, nor a request to an approver to approve
settings, which comes from a5s, not an agent, and only when someone proposes new settings.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from a5s import db
from a5s.contract import Scenario
from a5s.core.budgets import day_of

CAP = 5  # urgent messages a day that go to someone at once [TBC]
EVERY = timedelta(hours=1)  # how long the rest wait, at most, to go together


def counted(conn: db.Connection, scenario: Scenario, person: str, now: datetime) -> bool:
    """Count one more urgent message going to someone at once today. False if they've had
    today's five, so it waits for a batch."""
    return conn.execute(
        "insert into urgent_sent (person, day, sent) values (%s, %s, 1) "
        "on conflict (person, day) do update set sent = urgent_sent.sent + 1 "
        "where urgent_sent.sent < %s returning sent",
        (person, day_of(scenario, person, now), CAP)).fetchone() is not None


def hold(conn: db.Connection, person: str, agent: str | None, instance: str | None,
         run: str | None, text: str, now: datetime) -> None:
    """An urgent message that waits for the person's next batch."""
    conn.execute("insert into urgent_held (person, agent, instance_id, run_id, text, at) "
                 "values (%s, %s, %s, %s, %s, %s)", (person, agent, instance, run, text, now))


def due(conn: db.Connection, now: datetime) -> dict[str, list[dict]]:
    """The batches that go now, by person: everything held for someone whose oldest held
    message has waited an hour."""
    batches: dict[str, list[dict]] = {}
    for row in conn.execute(
            "select * from urgent_held where sent_at is null and person in ("
            "  select person from urgent_held where sent_at is null "
            "  group by person having min(at) <= %s) "
            "order by person, id for update", (now - EVERY,)).fetchall():
        batches.setdefault(row["person"], []).append(row)
    return batches


def compose(items: list[dict]) -> str:
    """One message from several agents' urgent messages, each under the agent that wrote it."""
    parts = [f"{len(items)} messages that waited, as you've had today's {CAP} at once:"]
    for item in items:
        parts.append(f"From the {item['agent']}:\n{item['text']}" if item["agent"]
                     else f"From a5s:\n{item['text']}")
    return "\n\n".join(parts)


def sent(conn: db.Connection, items: list[dict], now: datetime) -> None:
    conn.execute("update urgent_held set sent_at = %s where id = any(%s)",
                 (now, [i["id"] for i in items]))
