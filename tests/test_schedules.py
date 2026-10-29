"""Schedules: they come with the release, fire once for each time, and act for nobody.

The assistant's owner, Ana, works in London, so its schedules keep London time:
09:00 there is 08:00 UTC until 25 October 2026, and 09:00 UTC after it.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import yaml

from a5s import db, definitions
from a5s.core import registry, schedules

MORNING = {"name": "morning", "at": "09:00", "days": "weekdays",
           "task": "Look through the open questions, and save a draft summary of them."}


def with_schedule(stack, **schedule) -> None:
    """A new release of the assistant with a schedule, signed in and applied."""
    spec = stack.cfg.agents_dir / "assistant" / "agent.yaml"
    data = yaml.safe_load(spec.read_text())
    data["schedules"] = [{**MORNING, **schedule}]
    spec.write_text(yaml.safe_dump(data, sort_keys=False))
    stack.gateway.definitions = definitions.load_all(stack.cfg.agents_dir)
    assert not stack.settle().refused


def fires(stack) -> list[tuple[str, str]]:
    with db.transaction(stack.admin) as conn:
        rows = conn.execute("select due_at, outcome from schedule_fires order by due_at").fetchall()
    return [(r["due_at"].astimezone(UTC).isoformat(timespec="minutes"), r["outcome"]) for r in rows]


def test_a_schedule_fires_once_at_its_time_acting_for_nobody(stack):
    with_schedule(stack)
    stack.at("2026-10-29T08:59:00+00:00")
    assert stack.scheduler().work_due() == 0
    stack.at("2026-10-29T09:00:30+00:00")
    stack.model.reply("Saved a summary of the two open questions.")
    assert stack.scheduler().work_due() == 1
    stack.at("2026-10-29T09:10:00+00:00")
    assert stack.scheduler().work_due() == 0  # once for each time

    [request] = stack.model.requests
    [asked] = request["body"]["messages"][1:]  # the instructions, then the task: no conversation
    assert asked["content"].endswith("from a5s, not the person] " + MORNING["task"])
    [opened] = [e for e in stack.ledger() if e["action"] == "open"]
    assert opened["acts_for"] == [] and opened["args"]["trigger"] == "schedule"
    assert fires(stack) == [("2026-10-29T09:00+00:00", "run")]
    assert stack.inbox("ana") == []  # it writes to nobody


def test_a_schedule_keeps_its_owners_time_zone(stack):
    with_schedule(stack)
    stack.at("2026-10-23T08:00:30+00:00")  # 09:00 in London, in summer time
    stack.model.reply("Done.")
    assert stack.scheduler().work_due() == 1
    assert fires(stack) == [("2026-10-23T08:00+00:00", "run")]


def test_a_missed_time_is_let_go_not_worked_through(stack):
    with_schedule(stack)
    stack.at("2026-10-29T10:30:00+00:00")  # Thursday's time was more than an hour ago
    assert stack.scheduler().work_due() == 0
    stack.at("2026-10-31T09:00:00+00:00")  # Saturday isn't a day it works
    assert stack.scheduler().work_due() == 0
    assert fires(stack) == [] and not stack.model.requests


def test_a_suspended_instance_misses_its_time_and_doesnt_make_it_up(stack):
    with_schedule(stack)
    stack.suspend(by="ben")
    stack.at("2026-10-29T09:01:00+00:00")
    assert stack.scheduler().work_due() == 0
    with db.transaction(stack.admin) as conn:
        registry.set_status(conn, "assistant-finance", by="ben", suspend=False)
    stack.at("2026-10-29T09:20:00+00:00")
    assert stack.scheduler().work_due() == 0
    assert fires(stack) == [("2026-10-29T09:00+00:00", "suspended")]
    [skipped] = [e for e in stack.ledger() if e["action"] == "open"]
    assert skipped["decision"] == "deny" and skipped["reasons"] == ["assistant-finance is suspended"]

    stack.at("2026-10-30T09:00:00+00:00")  # and the next time it fires as usual
    stack.model.reply("Done.")
    assert stack.scheduler().work_due() == 1


def test_two_schedulers_fire_it_once(stack):
    with_schedule(stack)
    stack.at("2026-10-29T09:00:00+00:00")
    first, second = stack.scheduler(), stack.scheduler()
    seen = first.due(), second.due()
    assert seen[0] == seen[1] == [{"kind": "schedule", "schedule": "morning",
                                  "instance": "assistant-finance", "agent": "assistant"}]
    stack.model.reply("Done.")
    for scheduler, [item] in zip((first, second), seen, strict=True):
        scheduler._answer(scheduler._take(item))
    assert len(stack.model.requests) == 1
    assert fires(stack) == [("2026-10-29T09:00+00:00", "run")]


def test_the_core_decides_each_run_on_a_schedule(stack):
    with_schedule(stack)

    def fire(name: str = "morning"):
        with stack.client() as c:
            return c.post("/runs", json={"instance": "assistant-finance",
                                         "trigger": {"kind": "schedule", "schedule": name}})

    stack.at("2026-10-29T08:30:00+00:00")
    assert fire().json()["detail"]["reasons"] == ["morning isn't due"]
    assert fire("midnight").json()["detail"]["reasons"] == [
        "assistant-finance's release has no schedule midnight"]
    stack.at("2026-10-29T09:00:00+00:00")
    opened = fire()
    assert opened.status_code == 200 and opened.json()["task"] == MORNING["task"]
    assert fire().json()["detail"]["answered"]  # fired already

    with stack.client(opened.json()["token"]) as c:
        denied = c.post("/run/messages", json={"to": "ana", "text": "Here's the summary."})
    assert denied.status_code == 403  # a run that acts for nobody writes to nobody


def test_a_schedule_needs_real_times_and_days():
    with pytest.raises(ValueError, match="isn't a time in quotes"):
        definitions.Schedule(name="morning", at=540, task="x")  # what YAML makes of 9:00
    with pytest.raises(ValueError, match="isn't a day"):
        definitions.Schedule(name="morning", at="09:00", days=["someday"], task="x")


def test_latest_time_across_days_and_times():
    twice = definitions.Schedule(name="twice", at=["09:00", "13:30"], days=["mon", "wed"], task="x")
    london = ZoneInfo("Europe/London")

    def latest(when: str) -> str | None:
        found = schedules.latest(twice, london, datetime.fromisoformat(when))
        return found.isoformat() if found else None

    assert latest("2026-11-02T13:29:00+00:00") == "2026-11-02T09:00:00+00:00"  # Monday
    assert latest("2026-11-02T13:30:00+00:00") == "2026-11-02T13:30:00+00:00"
    assert latest("2026-11-03T12:00:00+00:00") == "2026-11-02T13:30:00+00:00"  # Tuesday
    assert latest("2026-11-04T08:00:00+00:00") == "2026-11-02T13:30:00+00:00"
