"""The scheduler: turns a trigger into a run, one at a time per conversation.

Phase 1's first trigger is a message. For each one, it leases the
conversation, opens a run through the core, gives the worker the conversation,
sends the reply through the gateway, and closes the run. Messages from Teams
reach it through the core, which received and checked them first.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg

from a5s import db
from a5s.config import Config
from a5s.contract import Scenario
from a5s.services import channels, context
from a5s.worker import run_agent

log = logging.getLogger(__name__)
Worker = Callable[[str, str, list[dict]], str]


def remote_worker(url: str) -> Worker:
    """Hand each run to a worker service, which holds nothing but the run's token."""

    def work(_gateway_url: str, token: str, history: list[dict]) -> str:
        response = httpx.post(f"{url}/work", json={"token": token, "history": history}, timeout=600)
        response.raise_for_status()
        return response.json()["reply"]

    return work


class Scheduler:
    def __init__(self, cfg: Config, scenario: Scenario, worker: Worker = run_agent,
                 http: httpx.Client | None = None, lease_wait: float = 600):
        self.cfg = cfg
        self.scenario = scenario
        self.worker = worker
        self.gw = http or httpx.Client(base_url=cfg.gateway_url, timeout=600)
        self.service = {"Authorization": f"Bearer {cfg.service_token}"}
        self.lease_wait = lease_wait  # how long a message waits for the one before it

    def _tell(self, person: str, channel: str, text: str, instance: str | None = None,
              inbound: str | None = None) -> str:
        """a5s's own words to someone. To Teams, they go through the core, which holds the bot."""
        if channel != "teams":
            with db.transaction(self.cfg.database_url) as conn:
                return channels.say(conn, person=person, text=text, channel=channel,
                                    instance=instance)
        try:
            sent = self.gw.post("/channels/teams/notices", headers=self.service, json={
                "person": person, "text": text, "inbound": inbound, "instance": instance})
            if sent.status_code >= 400:
                log.warning("Teams didn't get a notice for %s: %s", person, sent.text[:200])
        except httpx.HTTPError:
            log.exception("the gateway can't be reached to tell %s", person)
        return text

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

    def handle_message(self, *, person: str, agent: str, text: str, channel: str = "local",
                       identity: str | None = None, inbound: str | None = None) -> str:
        """Handle a message from a person.

        `identity` is their token, and `inbound` the message as the core received it,
        from a channel that signs messages. The core checks either.
        """
        if self.scenario.person(person) is None:
            return "a5s doesn't know who you are, so no agent can help."
        with db.transaction(self.cfg.database_url) as conn:
            inst = conn.execute(
                "select * from instances where definition = %s and %s = any(serves) "
                "and status <> 'retired' order by id limit 1",
                (agent, person),
            ).fetchone()
        if inst is None:
            return self._tell(person, channel, f"There's no {agent} for you yet.", None, inbound)

        key, holder = f"{person}/{agent}/{context.GENERAL}", str(uuid.uuid4())
        if not self._lease(key, holder):
            self._tell(person, channel,
                       "I'm still working on your last message, so I'll get to this next.",
                       inst["id"], inbound)
            deadline = time.monotonic() + self.lease_wait
            while not self._lease(key, holder):
                if time.monotonic() > deadline:
                    return self._tell(person, channel,
                                      "I couldn't get to that in time. Send it again in a few minutes.",
                                      inst["id"], inbound)
                time.sleep(1)
        try:
            return self._run(person, agent, text, channel, inst, identity, inbound)
        finally:
            self._release(key, holder)

    def _run(self, person: str, agent: str, text: str, channel: str, inst: dict,
             identity: str | None, inbound: str | None) -> str:
        with db.transaction(self.cfg.database_url) as conn:
            context.add_turn(conn, person=person, agent=agent, role="person", content=text)
        try:
            opened = self.gw.post("/runs", headers=self.service, json={
                "instance": inst["id"],
                "trigger": {"kind": "message", "channel": channel, "sender": person,
                            "identity": identity, "inbound": inbound},
            })
        except httpx.HTTPError:
            log.exception("the gateway can't be reached")
            opened = None
        if opened is None or opened.status_code >= 500:
            return self._tell(person, channel,
                              "a5s can't run agents right now. Try again in a few minutes.",
                              inst["id"], inbound)
        if opened.status_code == 409:
            detail, owner = opened.json()["detail"], self._owner_name(inst["owner"])
            if detail.get("identity") in ("missing", "refused"):
                text = "a5s couldn't confirm it's you, so no agent can help. Sign in again, then resend."
            elif detail.get("status", "active") != "active":
                text = f"The {agent} is {detail['status']} at the moment, so it can't help. Ask {owner}."
            else:
                text = f"The {agent} can't help you at the moment. Ask {owner}."
            return self._tell(person, channel, text, inst["id"], inbound)
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
                                  inst["id"], inbound)
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
                inst["id"], inbound,
            )
        finally:
            self.gw.post(f"/runs/{run}/close", headers=self.service, json={"outcome": outcome})

    # Messages the core received from channels that sign them, such as Teams.

    def _claim(self) -> dict | None:
        with db.transaction(self.cfg.database_url) as conn:
            return conn.execute(
                """
                update inbound set claimed_at = now()
                where id = (
                  select i.id from inbound i
                  where i.claimed_at is null and not exists (  -- its conversation isn't busy
                    select 1 from leases l
                    where l.key = i.person || '/' || i.agent || '/' || %s and l.expires_at > now())
                  order by i.received_at limit 1 for update skip locked)
                returning id, channel, person, agent, text
                """,
                (context.GENERAL,),
            ).fetchone()

    def _answer(self, row: dict) -> None:
        try:
            self.handle_message(person=row["person"], agent=row["agent"], text=row["text"],
                                channel=row["channel"], inbound=str(row["id"]))
        except Exception:
            log.exception("couldn't answer message %s", row["id"])

    def answer_waiting(self) -> int:
        """Answer, one by one, each message no one has taken yet."""
        answered = 0
        while (row := self._claim()) is not None:
            self._answer(row)
            answered += 1
        return answered

    def listen(self, stop: threading.Event, workers: int = 8) -> None:
        """Answer messages as the core receives them, several at once, until stopped."""
        with ThreadPoolExecutor(workers) as pool:
            while not stop.is_set():
                try:
                    with psycopg.connect(self.cfg.database_url, autocommit=True) as conn:
                        conn.execute("listen a5s_inbound")
                        while not stop.is_set():
                            while (row := self._claim()) is not None:
                                pool.submit(self._answer, row)
                            for _ in conn.notifies(timeout=2, stop_after=1):
                                pass
                except psycopg.OperationalError:
                    log.exception("lost the database, so listening again shortly")
                    stop.wait(5)
