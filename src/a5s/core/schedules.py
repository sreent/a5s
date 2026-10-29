"""Schedules: when an agent works on its own, as its release says.

The core works out each schedule's latest time, in the time zone of the
instance's owner, and fires it once. A time more than an hour past is let go,
so a5s never works through a backlog, and a time that falls while the instance
is suspended is recorded as skipped, and isn't made up after it resumes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from a5s.contract import Scenario
from a5s.definitions import DAYS, Schedule

GRACE = timedelta(hours=1)  # how late a schedule may still fire, such as after a restart [TBC]


def zone(scenario: Scenario, owner: str | None) -> ZoneInfo:
    """The time zone an instance's schedules keep: its owner's."""
    person = scenario.person(owner) if owner else None
    return ZoneInfo(person.timezone if person else "UTC")


def latest(schedule: Schedule, where: ZoneInfo, now: datetime) -> datetime | None:
    """The last time the schedule was due, at or before now, within the past week."""
    here = now.astimezone(where)
    for back in range(8):
        on = here.date() - timedelta(days=back)
        if DAYS[on.weekday()] in schedule.days:
            for at in sorted(schedule.at, reverse=True):
                due = datetime.combine(on, time.fromisoformat(at), tzinfo=where)
                if due <= here:
                    return due
    return None


def due_now(schedule: Schedule, where: ZoneInfo, now: datetime) -> datetime | None:
    """The time the schedule is due to fire for, now, if it's due."""
    due = latest(schedule, where, now)
    return due if due is not None and now - due <= GRACE else None
