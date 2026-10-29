"""a5s's own tools: typed tools that work on a5s's own records, never a scenario's.

They change no part's data, so an agent may use them at any level. Each is about the
person the run is answering, and theirs alone: only a run answering a message of
theirs can use one, and never a run that has read content from outside.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from a5s.contract import Person, Scenario


class Refused(Exception):
    """Why a5s won't do what the agent asked, in words the agent passes on."""


@dataclass(frozen=True)
class Call:
    """A call to one of a5s's own tools, with what the core knows of the run."""

    conn: psycopg.Connection
    run: dict[str, Any]  # the run, with its instance
    args: dict[str, Any]
    now: datetime
    scenario: Scenario

    @property
    def asked_at(self) -> datetime:
        """When the core received the message the run answers."""
        return self.conn.execute("select received_at from inbound where id = %s",
                                 (self.run["trigger"].get("inbound"),)).fetchone()["received_at"]

    @property
    def person(self) -> Person:
        """Whose these are: the person who wrote the message the run answers."""
        if self.run["trigger"].get("kind") != "message" or len(self.run["acts_for"]) != 1:
            raise Refused("it's the person's own, so it's set only in answer to a message of "
                          "theirs")
        if self.run["read_outside"]:
            raise Refused("this run has read content from outside, which can't set what's "
                          "theirs")
        person = self.scenario.person(self.run["acts_for"][0])
        if person is None:
            raise Refused("the directory doesn't know them")
        return person


@dataclass(frozen=True)
class CoreTool:
    """One of a5s's own tools, run in the core on its own records."""

    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[Call], Any]
    text_fields: tuple[str, ...] = ()

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "schema": self.schema,
                "risk": dict.fromkeys(("reads", "writes", "destructive", "sends_outside"), False),
                "text_fields": list(self.text_fields)}
