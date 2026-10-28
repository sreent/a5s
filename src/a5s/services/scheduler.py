"""The scheduler: turns a trigger into a run, one at a time per conversation.

Phase 1's first trigger is a message. For each one, it leases the
conversation, opens a run through the core, gives the worker the conversation,
sends the reply through the gateway, and closes the run.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

import httpx

from a5s import db
from a5s.config import Config
from a5s.contract import Scenario
from a5s.services import channels, context
from a5s.worker import run_agent

log = logging.getLogger(__name__)
Worker = Callable[[str, str, list[dict]], str]


class Scheduler:
    def __init__(self, cfg: Config, scenario: Scenario, worker: Worker = run_agent,
                 http: httpx.Client | None = None):
        self.cfg = cfg
        self.scenario = scenario
        self.worker = worker
        self.gw = http or httpx.Client(base_url=cfg.gateway_url, timeout=600)
        self.service = {"Authorization": f"Bearer {cfg.service_token}"}

    def _tell(self, person: str, channel: str, text: str, instance: str | None = None) -> str:
        with db.transaction(self.cfg.database_url) as conn:
            return channels.say(conn, person=person, text=text, channel=channel, instance=instance)

    def _lease(self, key: str, holder: str, seconds: int = 900) -> bool:
        with db.transaction(self.cfg.database_url) as conn:
            row = conn.execute(
                """
                insert into leases (key, holder, expires_at)
                values (%s, %s, now() + make_interval(secs => %s))
                on conflict (key) do update set holder = excluded.holder,
                  expires_at = excluded.expires_at
                where leases.expires_at < now()
                returning key
                """,
                (key, holder, seconds),
            ).fetchone()
        return row is not None

    def _release(self, key: str, holder: str) -> None:
        with db.transaction(self.cfg.database_url) as conn:
            conn.execute("delete from leases where key = %s and holder = %s", (key, holder))

    def _owner_name(self, owner: str | None) -> str:
        person = self.scenario.person(owner) if owner else None
        return person.name if person else "the platform owner"

    def handle_message(self, *, person: str, agent: str, text: str, channel: str = "local") -> str:
        if self.scenario.person(person) is None:
            return "a5s doesn't know who you are, so no agent can help."
        with db.transaction(self.cfg.database_url) as conn:
            inst = conn.execute(
                "select * from instances where definition = %s and %s = any(serves) "
                "and status <> 'retired' order by id limit 1",
                (agent, person),
            ).fetchone()
        if inst is None:
            return self._tell(person, channel, f"There's no {agent} for you yet.")

        key, holder = f"{person}/{agent}/{context.GENERAL}", str(uuid.uuid4())
        if not self._lease(key, holder):
            return self._tell(person, channel,
                              "I'm still working on your last message, so I'll get to this next.",
                              inst["id"])
        try:
            return self._run(person, agent, text, channel, inst)
        finally:
            self._release(key, holder)

    def _run(self, person: str, agent: str, text: str, channel: str, inst: dict) -> str:
        with db.transaction(self.cfg.database_url) as conn:
            context.add_turn(conn, person=person, agent=agent, role="person", content=text)
        try:
            opened = self.gw.post("/runs", headers=self.service, json={
                "instance": inst["id"],
                "trigger": {"kind": "message", "channel": channel, "sender": person},
            })
        except httpx.HTTPError:
            log.exception("the gateway can't be reached")
            opened = None
        if opened is None or opened.status_code >= 500:
            return self._tell(person, channel,
                              "a5s can't run agents right now. Try again in a few minutes.",
                              inst["id"])
        if opened.status_code == 409:
            status = opened.json()["detail"].get("status", "unavailable")
            return self._tell(
                person, channel,
                f"The {agent} is {status} at the moment, so it can't help. "
                f"Ask {self._owner_name(inst['owner'])}.",
                inst["id"],
            )
        opened.raise_for_status()
        run, token = opened.json()["run"], opened.json()["token"]
        outcome = "failed"
        try:
            with db.transaction(self.cfg.database_url) as conn:
                history = context.recent(conn, person=person, agent=agent)
            reply = self.worker(self.cfg.gateway_url, token, history)
            sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                                json={"to": person, "text": reply})
            if sent.status_code == 403:
                outcome = "reply denied"
                return self._tell(person, channel, "I couldn't send you my reply, sorry.",
                                  inst["id"])
            sent.raise_for_status()
            delivered = sent.json()["text"]
            with db.transaction(self.cfg.database_url) as conn:
                context.add_turn(conn, person=person, agent=agent, role="agent",
                                 content=delivered, run=run)
            outcome = "done"
            return delivered
        except Exception:
            log.exception("run %s failed", run)
            return self._tell(
                person, channel,
                f"I couldn't finish that. Try again, or ask {self._owner_name(inst['owner'])}.",
                inst["id"],
            )
        finally:
            self.gw.post(f"/runs/{run}/close", headers=self.service, json={"outcome": outcome})
