"""The scheduler: works through what the core says is waiting, one thing at a time
in each conversation.

Every message arrives at the core first (core/inbox.py), which checks who sent
it and records it. The scheduler takes the oldest message whose conversation is
free, leasing the conversation in the same step, and keeps the lease alive while
it works. It opens a run through the core, gives the worker the conversation,
sends the reply through the gateway, and closes the run. If the scheduler stops,
the lease runs out and the message is taken again. If the core can't be reached,
the message waits and is tried again later.

Every minute, it also asks the core what falls due: obligations whose agents
should remind their people, and reports with something to tell someone, each
taking the person's conversation in the same way, and schedules to fire, each
taking a lease of its own. The core decides each run, and escalates overdue
obligations itself. What can't run now is due
again at the next sweep. The scheduler has no port of its own, so nothing can
send it work but the core.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import psycopg

from a5s import db
from a5s.config import Config
from a5s.contract import INSTANCE_APPROVER, Scenario
from a5s.services import context
from a5s.worker import ModelDown, run_agent

log = logging.getLogger(__name__)
Worker = Callable[[str, str, list[dict]], str]
LEASE = 120  # seconds a conversation stays leased without being renewed


class Retry(Exception):
    """The core couldn't be reached, so the work waits and is tried again."""


def what(claim: dict) -> str:
    if claim["kind"] == "schedule":
        return f"schedule {claim['schedule']} of {claim['instance']}"
    return f"{claim['kind']} {claim.get(claim['kind']) or claim.get('id')}"


def remote_worker(url: str) -> Worker:
    """Hand each run to a worker service, which holds nothing but the run's token."""

    def work(_gateway_url: str, token: str, history: list[dict]) -> str:
        response = httpx.post(f"{url}/work", json={"token": token, "history": history}, timeout=600)
        if response.status_code == 503 and response.json().get("error") == "model_unavailable":
            raise ModelDown(response.json().get("detail", ""))
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

    def _ask(self, inst: dict, asker: str) -> str:
        """Who to ask about an instance: its owner, or its deputy when the owner is asking."""
        for candidate in (inst["owner"], inst["deputy"]):
            person = self.scenario.person(candidate) if candidate and candidate != asker else None
            if person:
                return person.name
        return "whoever runs a5s"

    def _nobody_serves(self, agent: str, asker: str) -> str:
        approvers = [p.name for p in self.scenario.holders(INSTANCE_APPROVER) if p.id != asker]
        if approvers:
            return f"There's no {agent} for you yet. Ask {' or '.join(approvers)} to add you."
        if self.scenario.holders(INSTANCE_APPROVER):  # only the person asking approves instances
            return f"There's no {agent} for you yet. As an instance approver, you can add one."
        return f"There's no {agent} for you yet. Ask whoever runs a5s to add you."

    def _turn(self, claim: dict, text: str, run: str) -> None:
        """Note in the conversation what a5s told someone, so a later run knows."""
        with db.transaction(self.cfg.database_url) as conn:
            context.add_turn(conn, person=claim["person"], agent=claim["agent"], role="notice",
                             content=text, run=run)

    # Taking work, and holding its conversation, or its schedule, while working on it

    @staticmethod
    def _lease(conn: psycopg.Connection, key: str, holder: str) -> bool:
        return conn.execute(
            """
            insert into leases (key, holder, expires_at)
            values (%s, %s, now() + make_interval(secs => %s))
            on conflict (key) do update set holder = excluded.holder,
              expires_at = excluded.expires_at
            where leases.expires_at <= now()
            returning key
            """,
            (key, holder, LEASE),
        ).fetchone() is not None

    def _claim(self) -> dict | None:
        """The oldest waiting message whose conversation is free, with that conversation leased."""
        holder = str(uuid.uuid4())
        with db.transaction(self.cfg.database_url) as conn:
            row = conn.execute(
                """
                select i.id::text as id, i.channel, i.person, i.agent, i.text, i.attempts,
                       i.person || '/' || i.agent || '/' || %(topic)s as lease
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
            if not self._lease(conn, row["lease"], holder):  # another scheduler took it a moment ago
                return None
            conn.execute("update inbound set claimed_at = now() where id = %s", (row["id"],))
        return {**row, "kind": "message", "holder": holder}

    def _take(self, item: dict) -> dict | None:
        """What's due, with what it needs leased: the person's conversation, for a reminder or
        a report, or the schedule itself."""
        if item["kind"] in ("obligation", "report", "reminder"):
            key = f"{item['person']}/{item['agent']}/{context.GENERAL}"
        else:
            key = f"schedule/{item['instance']}/{item['schedule']}"
        holder = str(uuid.uuid4())
        with db.transaction(self.cfg.database_url) as conn:
            if not self._lease(conn, key, holder):
                return None
        return {**item, "lease": key, "holder": holder}

    def _renew(self, claim: dict, stop: threading.Event) -> None:
        while not stop.wait(LEASE / 4):
            try:
                with db.transaction(self.cfg.database_url) as conn:
                    conn.execute(
                        "update leases set expires_at = now() + make_interval(secs => %s) "
                        "where key = %s and holder = %s",
                        (LEASE, claim["lease"], claim["holder"]))
            except psycopg.Error:
                log.exception("couldn't renew the lease on %s", claim["lease"])

    def _release(self, claim: dict) -> None:
        with db.transaction(self.cfg.database_url) as conn:
            conn.execute("delete from leases where key = %s and holder = %s",
                         (claim["lease"], claim["holder"]))

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
        message = claim["kind"] == "message"
        try:
            if message:
                self.handle(claim)
            else:
                self._work(claim)
        except Retry:
            log.warning("the core can't be reached, so %s waits", what(claim))
            if message:  # else it's due again at the next sweep
                self._later(claim)
        except Exception:
            log.exception("couldn't work on %s", what(claim))
            if message:
                self._tell(claim["id"], "Something went wrong on my side, so I couldn't answer "
                                        "that. Try again in a few minutes.")
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
            self._tell(inbound, self._nobody_serves(agent, person))
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
                self._tell(inbound, self._why_not(agent, inst, detail, person), inst["id"])
            return
        if opened.status_code >= 400:
            log.error("the gateway refused to open a run: %s", opened.text[:200])
            self._tell(inbound, "a5s couldn't start on that. Try again, or ask "
                                f"{self._ask(inst, person)}.", inst["id"])
            self._later(claim, never=True)
            return
        self._run(claim, inst, opened.json()["run"], opened.json()["token"])

    def _why_not(self, agent: str, inst: dict, detail: dict, asker: str) -> str:
        status, by = detail.get("status", "active"), detail.get("suspended_by")
        if status == "suspended" and by == asker:
            return f"The {agent} is suspended, because you suspended it. Resume it to carry on."
        if status == "suspended" and (suspender := self.scenario.person(by) if by else None):
            return (f"The {agent} is suspended at the moment, so it can't help. "
                    f"{suspender.name} suspended it and can resume it.")
        if status != "active":
            return f"The {agent} is {status}, so it can't help. Ask {self._ask(inst, asker)}."
        return f"The {agent} can't help you at the moment. Ask {self._ask(inst, asker)}."

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
                self._tell(inbound, told := "I couldn't send you my reply, sorry.", inst["id"])
                self._turn(claim, told, run)
                return
            sent.raise_for_status()
            with db.transaction(self.cfg.database_url) as conn:
                context.add_turn(conn, person=person, agent=agent, role="agent",
                                 content=sent.json()["text"], run=run)
            outcome = "done"
        except ModelDown:
            log.warning("the model for run %s isn't answering", run)
            outcome = "model unavailable"
            self._tell(inbound, told := "The model I use isn't answering right now, so I couldn't "
                                        "finish that. Try again in a few minutes.", inst["id"])
            self._turn(claim, told, run)
        except Exception:
            log.exception("run %s failed", run)
            self._tell(inbound, told := "I couldn't finish that. Try again, or ask "
                                        f"{self._ask(inst, person)}.", inst["id"])
            self._turn(claim, told, run)
        finally:
            self._close(run, outcome)

    def _close(self, run: str, outcome: str) -> None:
        try:
            self.gw.post(f"/runs/{run}/close", headers=self.service, json={"outcome": outcome})
        except httpx.HTTPError:
            log.exception("couldn't close run %s; it expires on its own", run)

    # Reminding people of obligations, telling them about their records, and schedules

    def _work(self, claim: dict) -> None:
        """Remind someone of an obligation, tell them what changed in their records, or work on
        a schedule, if the core opens the run."""
        kind = claim["kind"]
        try:
            opened = self.gw.post("/runs", headers=self.service, json={
                "instance": claim["instance"], "trigger": {"kind": kind, kind: claim[kind]}})
        except httpx.HTTPError as exc:
            raise Retry from exc
        if opened.status_code >= 500:
            raise Retry
        if opened.status_code >= 400:
            log.info("the core didn't open a run for %s: %s", what(claim), opened.text[:200])
            return
        run, token, task = (opened.json()[k] for k in ("run", "token", "task"))
        person, agent = claim.get("person"), claim["agent"]  # a schedule acts for nobody
        outcome = "failed"
        try:
            history = []
            if person:
                with db.transaction(self.cfg.database_url) as conn:
                    history = context.recent(conn, person=person, agent=agent)
            asked = {"role": "task", "content": task, "at": datetime.now(UTC).isoformat()}
            reply = self.worker(self.cfg.gateway_url, token, [*history, asked])
            if person:  # the agent writes to the person it reminds, and to nobody else
                sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                                    json={"to": person, "text": reply})
                if sent.status_code == 403:
                    outcome = "reply denied"
                    return
                sent.raise_for_status()
                with db.transaction(self.cfg.database_url) as conn:
                    context.add_turn(conn, person=person, agent=agent, role="task", content=task,
                                     run=run)
                    context.add_turn(conn, person=person, agent=agent, role="agent",
                                     content=sent.json()["text"], run=run)
            outcome = "done"
        except ModelDown:
            log.warning("the model for run %s isn't answering", run)
            outcome = "model unavailable"
        except Exception:
            log.exception("run %s failed", run)
        finally:
            self._close(run, outcome)

    # Working through the queue, and what falls due

    def answer_waiting(self) -> int:
        """Answer, one by one, each message that's waiting and can be answered now."""
        answered = 0
        while (claim := self._claim()) is not None:
            self._answer(claim)
            answered += 1
        return answered

    def due(self) -> list[dict]:
        """What the core says falls due now: obligations whose agents should remind their
        people, schedules to fire, and reports with something to tell. The core escalates
        overdue obligations as it works this out."""
        found: list[dict] = []
        for path in ("/obligations/sweep", "/schedules/sweep", "/reports/sweep", "/reminders/sweep"):
            try:
                response = self.gw.post(path, headers=self.service)
                response.raise_for_status()
                found += response.json()
            except httpx.HTTPError:
                log.exception("couldn't ask the core what's due (%s)", path)
        return found

    def work_due(self) -> int:
        """Work, one by one, on each obligation, schedule, report and reminder that's due and
        free now, and then send the digests whose work is done."""
        worked = 0
        for item in self.due():
            if (claim := self._take(item)) is not None:
                self._answer(claim)
                worked += 1
        self.digest()
        return worked

    def digest(self) -> None:
        """Ask the core to send each person's digest whose time has come and whose work is done."""
        try:
            self.gw.post("/digests/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to send the digests")

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
        """Answer messages as the core receives them, and work on what falls due, several at
        once, until stopped.

        Work is taken only when a worker is free for it.
        """
        free = threading.Semaphore(workers)

        def answer(claim: dict) -> None:
            try:
                self._answer(claim)
            finally:
                free.release()

        swept = float("-inf")  # so the first sweep is straight away
        with ThreadPoolExecutor(workers) as pool:
            while not stop.is_set():
                try:
                    with psycopg.connect(self.cfg.database_url, autocommit=True) as conn:
                        conn.execute("listen a5s_inbound")
                        while not stop.is_set():
                            if time.monotonic() - swept > sweep_every:
                                self.sweep()
                                for item in self.due():
                                    if not free.acquire(blocking=False):
                                        break  # the rest is due again at the next sweep
                                    if (claim := self._take(item)) is None:
                                        free.release()
                                        continue
                                    pool.submit(answer, claim)
                                self.digest()  # those whose work is done: the rest next time
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
