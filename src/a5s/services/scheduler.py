"""The scheduler: answers the messages the core received, one at a time per conversation.

Phase 1's only trigger is a message. Every message arrives at the core first
(core/inbox.py), which checks who sent it and records it. The scheduler takes
the oldest message whose conversation is free, leasing the conversation in the
same step, and keeps the lease alive while it works. It opens a run through the
core, gives the worker the conversation, sends the reply through the gateway,
and closes the run. If the scheduler stops, the lease runs out and the message
is taken again. If the core can't be reached, the message waits and is tried
again later. It has no port of its own, so nothing can send it work but the core.
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
from a5s.services import context
from a5s.worker import run_agent

log = logging.getLogger(__name__)
Worker = Callable[[str, str, list[dict]], str]
LEASE = 120  # seconds a conversation stays leased without being renewed


class Retry(Exception):
    """The core couldn't be reached, so the message waits and is tried again."""


def remote_worker(url: str) -> Worker:
    """Hand each run to a worker service, which holds nothing but the run's token."""

    def work(_gateway_url: str, token: str, history: list[dict]) -> str:
        response = httpx.post(f"{url}/work", json={"token": token, "history": history}, timeout=600)
        response.raise_for_status()
        return response.json()["reply"]

    return work


class Scheduler:
    def __init__(self, cfg: Config, scenario: Scenario, worker: Worker = run_agent,
                 http: httpx.Client | None = None):
        self.cfg = cfg
        self.scenario = scenario
        self.worker = worker
        self.gw = http or httpx.Client(base_url=cfg.gateway_url, timeout=600)
        self.service = {"Authorization": f"Bearer {cfg.service_token}"}

    def _tell(self, inbound: str, text: str, instance: str | None = None) -> None:
        """a5s's own words, in answer to a message. They go through the core, like any message."""
        try:
            sent = self.gw.post("/notices", headers=self.service,
                                json={"inbound": inbound, "text": text, "instance": instance})
            if sent.status_code >= 400:
                log.warning("a notice for message %s wasn't sent: %s", inbound, sent.text[:200])
        except httpx.HTTPError:
            log.exception("the gateway can't be reached, so message %s goes unanswered", inbound)

    def _owner_name(self, owner: str | None) -> str:
        person = self.scenario.person(owner) if owner else None
        return person.name if person else "the platform owner"

    # Taking messages, and holding their conversation while answering

    def _claim(self) -> dict | None:
        """The oldest waiting message whose conversation is free, with that conversation leased."""
        holder = str(uuid.uuid4())
        with db.transaction(self.cfg.database_url) as conn:
            row = conn.execute(
                """
                select i.id::text as id, i.channel, i.person, i.agent, i.text, i.attempts,
                       i.person || '/' || i.agent || '/' || %(topic)s as conversation
                from inbound i
                where i.answered_at is null and (i.retry_at is null or i.retry_at <= now())
                  and not exists (
                    select 1 from leases l
                    where l.key = i.person || '/' || i.agent || '/' || %(topic)s
                      and l.expires_at > now())
                order by i.received_at limit 1
                for update of i skip locked
                """,
                {"topic": context.GENERAL},
            ).fetchone()
            if row is None:
                return None
            leased = conn.execute(
                """
                insert into leases (key, holder, expires_at)
                values (%s, %s, now() + make_interval(secs => %s))
                on conflict (key) do update set holder = excluded.holder,
                  expires_at = excluded.expires_at
                where leases.expires_at <= now()
                returning key
                """,
                (row["conversation"], holder, LEASE),
            ).fetchone()
            if leased is None:  # another scheduler took the conversation a moment ago
                return None
            conn.execute("update inbound set claimed_at = now() where id = %s", (row["id"],))
        return {**row, "holder": holder}

    def _renew(self, claim: dict, stop: threading.Event) -> None:
        while not stop.wait(LEASE / 4):
            try:
                with db.transaction(self.cfg.database_url) as conn:
                    conn.execute(
                        "update leases set expires_at = now() + make_interval(secs => %s) "
                        "where key = %s and holder = %s",
                        (LEASE, claim["conversation"], claim["holder"]))
            except psycopg.Error:
                log.exception("couldn't renew the lease on %s", claim["conversation"])

    def _release(self, claim: dict) -> None:
        with db.transaction(self.cfg.database_url) as conn:
            conn.execute("delete from leases where key = %s and holder = %s",
                         (claim["conversation"], claim["holder"]))

    def _later(self, claim: dict, *, never: bool = False) -> None:
        """Try a message again after a while, longer each time, or never."""
        with db.transaction(self.cfg.database_url) as conn:
            conn.execute(
                "update inbound set attempts = attempts + 1, retry_at = case when %s "
                "then 'infinity'::timestamptz "
                "else now() + make_interval(secs => least(300, 15 * power(2, attempts))) end "
                "where id = %s", (never, claim["id"]))

    def _answer(self, claim: dict) -> None:
        stop = threading.Event()
        beat = threading.Thread(target=self._renew, args=(claim, stop), daemon=True)
        beat.start()
        try:
            self.handle(claim)
        except Retry:
            log.warning("the core can't be reached, so message %s waits", claim["id"])
            self._later(claim)
        except Exception:
            log.exception("couldn't answer message %s", claim["id"])
            self._tell(claim["id"], "Something went wrong on my side, so I couldn't answer that. "
                                    "Try again in a few minutes.")
            self._later(claim, never=True)
        finally:
            stop.set()
            beat.join()
            self._release(claim)

    # Answering one message

    def handle(self, claim: dict) -> None:
        person, agent, inbound = claim["person"], claim["agent"], claim["id"]
        with db.transaction(self.cfg.database_url) as conn:
            inst = conn.execute(
                "select * from instances where definition = %s and %s = any(serves) "
                "and status <> 'retired' order by (status = 'active') desc, id limit 1",
                (agent, person),
            ).fetchone()
        if inst is None:
            self._tell(inbound, f"There's no {agent} for you yet.")
            self._later(claim, never=True)
            return
        try:
            opened = self.gw.post("/runs", headers=self.service, json={
                "instance": inst["id"], "trigger": {"kind": "message", "inbound": inbound}})
        except httpx.HTTPError as exc:
            raise Retry from exc
        if opened.status_code >= 500:
            raise Retry
        if opened.status_code == 409:
            detail = opened.json()["detail"]
            if not detail.get("answered"):  # answered already, by someone else: nothing to do
                self._tell(inbound, self._why_not(agent, inst, detail), inst["id"])
            return
        if opened.status_code >= 400:
            log.error("the gateway refused to open a run: %s", opened.text[:200])
            self._tell(inbound, "a5s couldn't start on that. Try again, or ask "
                                f"{self._owner_name(inst['owner'])}.", inst["id"])
            self._later(claim, never=True)
            return
        self._run(claim, inst, opened.json()["run"], opened.json()["token"])

    def _why_not(self, agent: str, inst: dict, detail: dict) -> str:
        owner = self._owner_name(inst["owner"])
        if detail.get("status", "active") != "active":
            return f"The {agent} is {detail['status']} at the moment, so it can't help. Ask {owner}."
        return f"The {agent} can't help you at the moment. Ask {owner}."

    def _run(self, claim: dict, inst: dict, run: str, token: str) -> None:
        person, agent, inbound = claim["person"], claim["agent"], claim["id"]
        outcome = "failed"
        try:
            with db.transaction(self.cfg.database_url) as conn:
                context.add_turn(conn, person=person, agent=agent, role="person",
                                 content=claim["text"], run=run)
                history = context.recent(conn, person=person, agent=agent)
            reply = self.worker(self.cfg.gateway_url, token, history)
            sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                                json={"to": person, "text": reply})
            if sent.status_code == 403:
                outcome = "reply denied"
                self._tell(inbound, "I couldn't send you my reply, sorry.", inst["id"])
                return
            sent.raise_for_status()
            with db.transaction(self.cfg.database_url) as conn:
                context.add_turn(conn, person=person, agent=agent, role="agent",
                                 content=sent.json()["text"], run=run)
            outcome = "done"
        except Exception:
            log.exception("run %s failed", run)
            self._tell(inbound, "I couldn't finish that. Try again, or ask "
                                f"{self._owner_name(inst['owner'])}.", inst["id"])
        finally:
            try:
                self.gw.post(f"/runs/{run}/close", headers=self.service, json={"outcome": outcome})
            except httpx.HTTPError:
                log.exception("couldn't close run %s; it expires on its own", run)

    # Working through the queue

    def answer_waiting(self) -> int:
        """Answer, one by one, each message that's waiting and can be answered now."""
        answered = 0
        while (claim := self._claim()) is not None:
            self._answer(claim)
            answered += 1
        return answered

    def sweep(self) -> None:
        """Close runs that outlived their time, and tell their people."""
        try:
            stale = self.gw.post("/runs/sweep", headers=self.service)
            stale.raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't sweep runs")
            return
        for run in stale.json():
            if run.get("inbound"):
                self._tell(run["inbound"], "I couldn't finish your last message, so I stopped. "
                                           "Send it again if you still need it.", run["instance"])

    def listen(self, stop: threading.Event, workers: int = 8, sweep_every: float = 60) -> None:
        """Answer messages as the core receives them, several at once, until stopped.

        A message is taken only when a worker is free to answer it.
        """
        free = threading.Semaphore(workers)

        def answer(claim: dict) -> None:
            try:
                self._answer(claim)
            finally:
                free.release()

        swept = 0.0
        with ThreadPoolExecutor(workers) as pool:
            while not stop.is_set():
                try:
                    with psycopg.connect(self.cfg.database_url, autocommit=True) as conn:
                        conn.execute("listen a5s_inbound")
                        while not stop.is_set():
                            if time.monotonic() - swept > sweep_every:
                                self.sweep()
                                swept = time.monotonic()
                            while free.acquire(blocking=False):
                                claim = self._claim()
                                if claim is None:
                                    free.release()
                                    break
                                pool.submit(answer, claim)
                            for _ in conn.notifies(timeout=2, stop_after=1):
                                pass
                except psycopg.OperationalError:
                    log.exception("lost the database, so listening again shortly")
                    stop.wait(5)
