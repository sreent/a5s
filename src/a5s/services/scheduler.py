"""The scheduler: works through what the core says is waiting, one thing at a time
in each conversation.

Every message arrives at the core first (core/inbox.py), which checks who sent
it and records it. The scheduler takes the oldest message whose conversation is
free, leasing the conversation in the same step, and keeps the lease alive while
it works. It opens a run through the core, gives the worker the conversation,
sends the reply through the gateway, and closes the run. Each agent's runs go to
its own pool of workers, if it has one, and every other agent's to the shared
pool. If the scheduler stops, the lease runs out and the message is taken again.
If the core can't be reached, the message waits and is tried again later.

Every minute, it also asks the core what falls due: obligations whose agents
should remind their people, and reports with something to tell someone, each
taking the person's conversation in the same way, and schedules to fire, and
the next slices of people's tasks, each taking a lease of its own, so a task at
work never holds up its owner's own chat. The core decides each run, and
escalates overdue obligations itself. What can't run now is due again at the
next sweep, but for a task, which the core puts off a while. The scheduler has
no port of its own, so nothing can send it work but the core.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import psycopg

from a5s import config, db, reach
from a5s.config import Config
from a5s.contract import INSTANCE_APPROVER, PART_OWNER, Scenario
from a5s.core import groups, registry, tasking
from a5s.services import context, summaries
from a5s.worker import BudgetSpent, ModelDown, TaskStopped, run_agent

log = logging.getLogger(__name__)
Worker = Callable[[str, str, list[dict]], str]
LEASE = 120  # seconds a conversation stays leased without being renewed




class Slots:
    """How many runs the scheduler works on at once in each worker pool: in each agent's
    own, and in the shared pool, for every other agent. Each pool's are its own, so no
    agent's runs, however slow, take the slots another's need."""

    def __init__(self, shared: int, pools: dict[str, int] | None = None):
        self._lock = threading.Lock()
        self.pooled = frozenset(pools or {})
        self._free: dict[str | None, int] = {None: shared, **(pools or {})}
        self._size = dict(self._free)
        self.total = sum(self._free.values())

    def pool(self, agent: str) -> str | None:
        """The agent's own pool, or None for the shared one."""
        return agent if agent in self.pooled else None

    def pools(self) -> list[str | None]:
        return [*sorted(self.pooled), None]

    def take(self, pool: str | None, keep: int = 0) -> bool:
        """A slot of the pool's, leaving `keep` free, or False if it has none to spare."""
        with self._lock:
            if self._free[pool] <= keep:
                return False
            self._free[pool] -= 1
            return True

    def spare(self, pool: str | None) -> int:
        """The slots a pool keeps for people's messages, which work that falls due, such as
        a task's slice, never takes: one, where it has more than one."""
        return 1 if self._size[pool] > 1 else 0

    def give(self, pool: str | None) -> None:
        with self._lock:
            self._free[pool] += 1

    def busy(self) -> int:
        """How many runs are in flight, in every pool."""
        with self._lock:
            return self.total - sum(self._free.values())


class Retry(Exception):
    """The core couldn't be reached, so the work waits and is tried again."""


def what(claim: dict) -> str:
    if claim["kind"] == "schedule":
        return f"schedule {claim['schedule']} of {claim['instance']}"
    return f"{claim['kind']} {claim.get(claim['kind']) or claim.get('id')}"


def remote_worker(url: str, within: float = reach.WITHIN) -> Worker:
    """Hand each run to a worker service, which holds nothing but the run's token. A pool
    that can't be reached, such as one restarting, never got the run, so it's tried again for
    up to `within` seconds before the run fails: a restart holds its runs up, and loses none."""
    # longer than the run may take on the worker, so the worker says why it stopped first
    pool = reach.client(within, base_url=url,
                        timeout=httpx.Timeout(config.WORKER_WAIT.read(), connect=10))

    def work(_gateway_url: str, token: str, history: list[dict]) -> str:
        response = pool.post("/work", json={"token": token, "history": history})
        if response.status_code == 503 and response.json().get("error") == "model_unavailable":
            raise ModelDown(response.json().get("detail", ""))
        if response.status_code == 429 and response.json().get("error") == "budget_spent":
            raise BudgetSpent(response.json().get("detail", ""))
        if response.status_code == 409 and response.json().get("error") == "task_stopped":
            raise TaskStopped(response.json().get("detail", ""))
        if response.status_code == 409 and response.json().get("error") == "wrong_pool":
            raise RuntimeError(f"the worker pool at {url} refused the run: "
                               f"{response.json().get('detail', '')}")
        response.raise_for_status()
        return response.json()["reply"]

    return work


class Scheduler:
    def __init__(self, cfg: Config, scenario: Scenario, worker: Worker = run_agent,
                 http: httpx.Client | None = None, pools: dict[str, Worker] | None = None):
        self.cfg = cfg
        self.scenario = scenario
        self.worker = worker  # the shared pool, for every agent without a pool of its own
        self.pools = dict(pools or {})  # each agent's own, by its name
        self.gw = http or reach.client(base_url=cfg.gateway_url,  # waiting for it, a moment,
                                       timeout=httpx.Timeout(600, connect=10))  # as it restarts
        self.service = {"Authorization": f"Bearer {cfg.service_token}"}

    def _worker(self, agent: str) -> Worker:
        """Where an agent's runs go: its own worker pool, or the shared one."""
        return self.pools.get(agent, self.worker)

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

    def _serving(self, instances: list[dict], people: list[str], text: str) -> dict | None:
        """The instance of an agent that answers someone: one that serves them, and everyone
        else in their group chat, and, if their message names a record, one that works in the
        record's part."""
        theirs = [i for i in instances
                  if all(registry.serving(self.scenario, i["serves"], p) for p in people)]
        pattern = getattr(self.scenario, "record_pattern", None)
        for found in (re.finditer(pattern, text) if pattern else ()):
            part = self.scenario.part_of(found.group(0))
            if part and (fit := [i for i in theirs if part in (i["parts"] or {})]):
                return fit[0]
        return theirs[0] if theirs else None

    def _nobody_serves(self, agent: str, asker: str, others: list[str] | None = None) -> str:
        """Who can add someone to an agent: the owners of the parts its instances work in, or
        the instance approvers, for one in no part. With `others`, the people in a group chat
        with the asker whom it doesn't serve."""
        with db.transaction(self.cfg.database_url) as conn:
            scopes = [i["parts"] or {} for i in conn.execute(
                "select parts from instances where definition = %s and status <> 'retired'",
                (agent,))]
        roles = [f"{PART_OWNER}:{p}" for scope in scopes for p in scope] or [INSTANCE_APPROVER]
        holders = {p.id: p for role in dict.fromkeys(roles) for p in self.scenario.holders(role)}
        approvers = [p.name for p in holders.values() if p.id != asker]
        them = "them" if others else "you"
        if approvers:
            add = f"Ask {' or '.join(approvers)} to add {them}."
        elif holders:  # only the person asking approves it
            add = ("As an instance approver, you can add " if roles == [INSTANCE_APPROVER]
                   else "As the owner of the parts it works in, you can add ") + (
                "them." if others else "one.")
        else:
            add = f"Ask whoever runs a5s to add {them}."
        if others:
            return groups.UNSERVED.format(who=groups.names(self.scenario, others), add=add)
        return f"There's no {agent} for you yet. {add}"

    def _turn(self, claim: dict, text: str, run: str, topic: str) -> None:
        """Note in the conversation what a5s told someone, so a later run knows."""
        with db.transaction(self.cfg.database_url) as conn:
            context.add_turn(conn, person=claim.get("conversation") or claim["person"],
                             agent=claim["agent"], role="notice", content=text, run=run,
                             topic=topic, heard_by=claim.get("members"))

    # Taking work, and holding its conversation, or its schedule, while working on it

    @staticmethod
    def _lease(conn: db.Connection, key: str, holder: str) -> bool:
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

    def _claim(self, agent: str | None = None,
               besides: frozenset[str] = frozenset()) -> dict | None:
        """The oldest waiting message whose conversation is free, with that conversation
        leased: for `agent` alone, if it says, and for none of `besides`, so each worker
        pool takes only its own agents' messages."""
        holder = str(uuid.uuid4())
        with db.transaction(self.cfg.database_url) as conn:
            row = conn.execute(
                """
                select i.id::text as id, i.channel, i.person, i.agent, i.text, i.attempts,
                       coalesce(i.conversation, i.person) as conversation, i.members,
                       coalesce(i.conversation, i.person) || '/' || i.agent || '/' || %(topic)s
                         as lease
                from inbound i
                where i.answered_at is null and (i.retry_at is null or i.retry_at <= now())
                  and (%(agent)s::text is null or i.agent = %(agent)s)
                  and not i.agent = any(%(besides)s::text[])
                  and not exists (
                    select 1 from leases l
                    where l.key = coalesce(i.conversation, i.person) || '/' || i.agent || '/'
                                  || %(topic)s
                      and l.expires_at > now())
                order by i.received_at limit 1
                for update of i skip locked
                """,
                {"topic": context.GENERAL, "agent": agent, "besides": sorted(besides)},
            ).fetchone()
            if row is None:
                return None
            if not self._lease(conn, row["lease"], holder):  # another scheduler took it a moment ago
                return None
            conn.execute("update inbound set claimed_at = now() where id = %s", (row["id"],))
        return {**row, "kind": "message", "holder": holder}

    def _take(self, item: dict) -> dict | None:
        """What's due, with what it needs leased: the person's conversation, for a reminder or
        a report, or the schedule, or the task, itself."""
        if item["kind"] in ("obligation", "report", "reminder"):
            key = f"{item['person']}/{item['agent']}/{context.GENERAL}"
        elif item["kind"] == tasking.KIND:
            key = f"task/{item['task']}"
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
        group = groups.of(claim.get("conversation"))
        with db.transaction(self.cfg.database_url) as conn:
            instances = conn.execute(
                "select * from instances where definition = %s and status <> 'retired' "
                "order by (status = 'active') desc, id", (agent,)).fetchall()
        members = list(claim["members"]) if group else [person]
        if group and (unwritten := [m for m in members if (p := self.scenario.person(m))
                                    and not p.in_audience]):  # before a run, not after it
            self._tell(inbound, groups.UNWRITTEN.format(who=groups.names(self.scenario, unwritten)))
            self._later(claim, never=True)
            return
        inst = self._serving(instances, members, claim["text"])
        if inst is None:
            unserved = [m for m in members if not any(
                registry.serving(self.scenario, i["serves"], m) for i in instances)]
            self._tell(inbound, self._nobody_serves(agent, person) if not group else
                       self._nobody_serves(agent, person, unserved) if unserved else groups.APART)
            self._later(claim, never=True)
            return
        try:
            opened = self.gw.post("/runs", headers=self.service, json={
                "instance": inst["id"], "trigger": {"kind": "message", "inbound": inbound,
                                                    "holder": claim.get("holder")}})
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
        self._run(claim, inst, opened.json())

    def _why_not(self, agent: str, inst: dict, detail: dict, asker: str) -> str:
        status, by = detail.get("status", "active"), detail.get("suspended_by")
        if detail.get("out_of_budget"):
            return self._spent(agent, inst, asker)
        if status == "suspended" and by == asker:
            return f"The {agent} is suspended, because you suspended it. Resume it to carry on."
        if status == "suspended" and (suspender := self.scenario.person(by) if by else None):
            return (f"The {agent} is suspended at the moment, so it can't help. "
                    f"{suspender.name} suspended it and can resume it.")
        if status != "active":
            return f"The {agent} is {status}, so it can't help. Ask {self._ask(inst, asker)}."
        return f"The {agent} can't help you at the moment. Ask {self._ask(inst, asker)}."

    def _spent(self, agent: str, inst: dict, asker: str) -> str:
        return (f"The {agent} has used its budget for you today, so it can't help with that until "
                f"tomorrow. Ask {self._ask(inst, asker)} if it can't wait.")

    def _run(self, claim: dict, inst: dict, opened: dict) -> None:
        person, agent, inbound = claim["person"], claim["agent"], claim["id"]
        run, token = opened["run"], opened["token"]
        topic = opened.get("topic") or context.GENERAL  # the core decides it
        conversation = claim.get("conversation") or person  # theirs, or their group chat's
        members = list(claim["members"]) if groups.of(conversation) else None
        heard = {"speaker": person, "heard_by": members} if members else {}
        outcome = "failed"
        try:
            with db.transaction(self.cfg.database_url) as conn:
                context.add_turn(conn, person=conversation, agent=agent, role="person",
                                 content=claim["text"], run=run, topic=topic, **heard)
                history = context.history(
                    conn, person=conversation, agent=agent, topic=topic,
                    chars=opened.get("history_chars") or context.CHARS, members=members,
                    names=self._names([*members, *context.speakers(conn, conversation, agent)])
                    if members else None)
            reply = self._worker(agent)(self.cfg.gateway_url, token, history)
            if not reply.strip():
                raise RuntimeError("the agent's reply was empty")
            sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                                json={"to": conversation, "text": reply})
            if sent.status_code == 403:
                outcome = "reply denied"
                self._tell(inbound, told := "I couldn't send you my reply, sorry.", inst["id"])
                self._turn(claim, told, run, topic)
                return
            sent.raise_for_status()
            heard = [person] if sent.json().get("kept_back") else members  # whoever asked
            with db.transaction(self.cfg.database_url) as conn:  # alone, if someone joined
                context.add_turn(conn, person=conversation, agent=agent, role="agent",
                                 content=sent.json()["text"], run=run, topic=topic,
                                 heard_by=heard)
                if note := sent.json().get("note"):  # a5s's own words on the agent's values
                    context.add_turn(conn, person=conversation, agent=agent, role="notice",
                                     content=note, run=run, topic=topic, heard_by=heard)
            outcome = "done"
        except ModelDown:
            log.warning("the model for run %s isn't answering", run)
            outcome = "model unavailable"
            self._tell(inbound, told := "The model I use isn't answering right now, so I couldn't "
                                        "finish that. Try again in a few minutes.", inst["id"])
            self._turn(claim, told, run, topic)
        except BudgetSpent as exc:
            outcome = "budget spent"
            told = self._spent(agent, inst, person) if "today" in str(exc) else (
                "That took more work than one run may do, so I stopped. Try asking for less at "
                f"once, or ask {self._ask(inst, person)}.")
            self._tell(inbound, told, inst["id"])
            self._turn(claim, told, run, topic)
        except Exception:
            log.exception("run %s failed", run)
            self._tell(inbound, told := "I couldn't finish that. Try again, or ask "
                                        f"{self._ask(inst, person)}.", inst["id"])
            self._turn(claim, told, run, topic)
        finally:
            self._close(run, outcome)
        if outcome == "done":  # once they have their answer
            self._fold(inst["id"], conversation, agent, topic, opened.get("history_chars"),
                       members, inbound)

    def _fold(self, instance: str, person: str, agent: str, topic: str,
              chars: int | None, members: list[str] | None = None,
              inbound: str | None = None) -> None:
        """Fold the topic's turns that no run is given any more into its summary, with a run
        of a5s's own, once there are any. Code checks the summary before it's kept. In a group
        chat, the turns everyone in it heard, for them, as the message's run was."""
        chars = chars or context.CHARS
        with db.transaction(self.cfg.database_url) as conn:
            previous, turns = context.dropped(conn, person=person, agent=agent, topic=topic,
                                              chars=chars, members=members)
        names = None if members is None else self._names(
            [*members, *(t["speaker"] for t in turns if t["speaker"])])
        if sum(len(t["content"]) for t in turns) < chars * context.FOLD:
            return  # not yet: they're folded in a batch, not one model call a run
        taken, size = [], 0  # at most a run's worth at once: the rest, next time
        for turn in turns:
            if taken and size + len(turn["content"]) > chars:
                break
            taken.append(turn)
            size += len(turn["content"])
        turns = taken
        trigger = {"kind": "summary", "person": person, "topic": topic,
                   **({"message": inbound} if members is not None else {})}
        try:
            opened = self.gw.post("/runs", headers=self.service,
                                  json={"instance": instance, "trigger": trigger})
        except httpx.HTTPError:
            log.warning("the core can't be reached, so %s's summary waits", topic)
            return
        if opened.status_code >= 400:
            log.info("the core didn't open a summary run: %s", opened.text[:200])
            return
        run, token = opened.json()["run"], opened.json()["token"]
        name = who.name if (who := self.scenario.person(person)) else person
        asked = {"role": "task", "content": summaries.task(name, topic, previous, turns, names),
                 "at": datetime.now(UTC).isoformat()}
        outcome = "failed"
        try:
            reply = self._worker(agent)(self.cfg.gateway_url, token, [asked])
            body, problems = summaries.checked(reply, previous, turns, name, self.scenario,
                                               names)
            with db.transaction(self.cfg.database_url) as conn:  # folded, either way, once
                summaries.keep(conn, person, agent, topic, body, turns[-1]["id"], run,
                               summaries.heard_by(previous, turns))
            if problems:  # how many, never what: they're what someone said
                log.warning("kept %s's summary for %s without %d things code couldn't trace",
                            topic, person, len(problems))
            outcome = "done" if not problems else "done, leaving some out"
        except ModelDown:
            outcome = "model unavailable"
        except BudgetSpent:  # the turns wait to be folded in, with the next day's budget
            outcome = "budget spent"
        except Exception:
            log.exception("summary run %s failed", run)
        finally:
            self._close(run, outcome[:200])

    def _names(self, people: list[str]) -> dict[str, str]:
        """What the directory calls each of them, in a group chat's conversation: whoever's in
        it, and whoever said what its runs are given, even if they've left it since."""
        return {p: who.name for p in dict.fromkeys(people) if (who := self.scenario.person(p))}

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
                "instance": claim["instance"], "trigger": {"kind": kind, kind: claim[kind],
                                                           "holder": claim.get("holder")}})
        except httpx.HTTPError as exc:
            raise Retry from exc
        if opened.status_code >= 500:
            raise Retry
        if opened.status_code >= 400:
            log.info("the core didn't open a run for %s: %s", what(claim), opened.text[:200])
            return
        run, token, task = (opened.json()[k] for k in ("run", "token", "task"))
        topic = opened.json().get("topic") or context.GENERAL  # the core decides it
        person, agent = claim.get("person"), claim["agent"]  # a schedule acts for nobody
        outcome = "failed"
        try:
            history = []
            if person:
                with db.transaction(self.cfg.database_url) as conn:
                    history = context.history(
                        conn, person=person, agent=agent, topic=topic,
                        chars=opened.json().get("history_chars") or context.CHARS)
            asked = {"role": "task", "content": task, "at": datetime.now(UTC).isoformat()}
            reply = self._worker(agent)(self.cfg.gateway_url, token, [*history, asked])
            if person and not reply.strip():
                raise RuntimeError("the agent's reply was empty")
            if (kind == tasking.KIND and reply.strip()  # to its owner, once it's done or needs
                    and not self._finished(claim, run, token, reply, topic)):  # them
                outcome = "reply denied"
                return
            if person:  # the agent writes to the person it reminds, and to nobody else
                sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                                    json={"to": person, "text": reply})
                if sent.status_code == 403:
                    outcome = "reply denied"
                    return
                sent.raise_for_status()
                with db.transaction(self.cfg.database_url) as conn:
                    context.add_turn(conn, person=person, agent=agent, role="task", content=task,
                                     run=run, topic=topic)
                    context.add_turn(conn, person=person, agent=agent, role="agent",
                                     content=sent.json()["text"], run=run, topic=topic)
                    if note := sent.json().get("note"):
                        context.add_turn(conn, person=person, agent=agent, role="notice",
                                         content=note, run=run, topic=topic)
            outcome = "done"
        except ModelDown:
            log.warning("the model for run %s isn't answering", run)
            outcome = "model unavailable"
        except BudgetSpent:  # it waits, for the next day's budget
            outcome = "budget spent"
        except TaskStopped:  # its task was cancelled, or taken over, as it worked
            outcome = "stopped"
        except Exception:
            log.exception("run %s failed", run)
        finally:
            self._close(run, outcome)
        if person and outcome == "done":  # once the person has been told
            self._fold(claim["instance"], person, agent, topic, opened.json().get("history_chars"))

    def _finished(self, claim: dict, run: str, token: str, reply: str,
                  topic: str = context.GENERAL) -> bool:
        """Give a task's owner what its run wrote them, if the core lets it, now that the task
        is done or needs them: kept in their conversation, as the agent's, in the task's own
        topic. Whether nothing was denied: a task still at work writes to nobody, which isn't
        a denial."""
        owner, agent = claim["owner"], claim["agent"]
        sent = self.gw.post("/run/messages", headers={"Authorization": f"Bearer {token}"},
                            json={"to": owner, "text": reply})
        if sent.status_code == 403:
            return tasking.HELD in (sent.json().get("reasons") or [])
        sent.raise_for_status()
        topic = sent.json().get("topic") or topic  # the core says where: its own, if marked
        with db.transaction(self.cfg.database_url) as conn:
            context.add_turn(conn, person=owner, agent=agent, role="agent",
                             content=sent.json()["text"], run=run, topic=topic)
            if note := sent.json().get("note"):
                context.add_turn(conn, person=owner, agent=agent, role="notice", content=note,
                                 run=run, topic=topic)
        return True

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
        for path in ("/obligations/sweep", "/schedules/sweep", "/reports/sweep",
                     "/reminders/sweep", "/tasks/sweep"):
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
        self.decided()
        self.deliveries()
        return worked

    def digest(self) -> None:
        """Ask the core to send each person's digest whose time has come and whose work is done."""
        try:
            self.gw.post("/digests/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to send the digests")

    def apply_approved(self) -> None:
        """Ask the core to apply a version of the settings its instance approvers approved
        where they work, if one is waiting."""
        try:
            self.gw.post("/settings/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to apply approved settings")

    def decided(self) -> None:
        """Ask the core to make the held changes their deciders approved, and to remind,
        escalate or let go of those still waiting; and to weigh the grades of agents' work."""
        for path, what in (("/proposals/sweep", "the held changes"),
                           ("/samples/sweep", "the graded samples")):
            try:
                self.gw.post(path, headers=self.service).raise_for_status()
            except httpx.HTTPError:
                log.exception("couldn't ask the core about %s", what)

    def deliveries(self) -> None:
        """Ask the core to deliver again what a chat it writes to didn't take before."""
        try:
            self.gw.post("/deliveries/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to deliver again")

    def retain(self) -> None:
        """Ask the core to delete what's past its time to keep."""
        try:
            self.gw.post("/retention/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to delete what's past its time")

    def check_notes(self) -> None:
        """Ask the core to check the notebook's notes against their records: on a thread of
        its own, since the records system may be slow to answer."""
        try:
            self.gw.post("/notebook/sweep", headers=self.service).raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't ask the core to check the notebook")

    def sweep(self) -> None:
        """Close runs that outlived their time, or whose scheduler stopped without closing them,
        and tell their people, unless they had an answer."""
        try:
            stale = self.gw.post("/runs/sweep", headers=self.service)
            stale.raise_for_status()
        except httpx.HTTPError:
            log.exception("couldn't sweep runs")
            return
        for run in stale.json():
            if run.get("inbound") and not run.get("answered"):
                self._tell(run["inbound"], "I couldn't finish your last message, so I stopped. "
                                           "Send it again if you still need it.", run["instance"])

    def listen(self, stop: threading.Event, workers: int = 8, sweep_every: float = 60,
               retain_every: float = 3600) -> None:
        """Answer messages as the core receives them, and work on what falls due, several at
        once, until stopped. Every hour, ask the core to delete what's past its time to keep,
        and, on a thread of its own, to check the notebook against its records.

        Once stopped, it takes no more work, and returns when the runs it has in flight are
        done, so none loses its answer.

        Work is taken only when its agent's worker pool has a slot free for it: `workers` in
        the shared pool, and each agent's own pool its own (Slots). The sweeps run on their
        own thread, so a chat that's slow to take what the core delivers in them never holds
        up answers.
        """
        slots = Slots(workers, {agent: self.cfg.worker_slots.get(agent, config.POOL_SLOTS)
                                for agent in self.pools})

        def answer(claim: dict) -> None:
            try:
                self._answer(claim)
            finally:
                slots.give(slots.pool(claim["agent"]))

        def handed(each: str | None, take: Callable[[], dict | None]) -> bool:
            """Take work for the slot the caller holds, and hand it to a worker: or give the
            slot back, where there's no work, or taking it fails, as a database error makes
            it, so no error costs a slot."""
            try:
                if (claim := take()) is not None:
                    pool.submit(answer, claim)
                    return True
            except BaseException:
                slots.give(each)
                raise
            slots.give(each)
            return False

        def sweeping() -> None:
            kept = float("-inf")  # so the first sweeps are straight away
            while not stop.is_set():
                started = time.monotonic()
                try:
                    self.sweep()
                    self.apply_approved()
                    for item in self.due():
                        if stop.is_set():  # asked to stop: it takes nothing more
                            break
                        each = slots.pool(item["agent"])
                        if not slots.take(each, keep=slots.spare(each)):
                            continue  # its pool is full: it's due again at the next sweep
                        handed(each, lambda item=item: self._take(item))
                    for then in (self.digest, self.decided, self.deliveries):
                        if not stop.is_set():  # those whose work is done: the rest next time
                            then()
                    if not stop.is_set() and time.monotonic() - kept > retain_every:
                        self.retain()
                        kept = time.monotonic()
                    log.debug("%s runs in flight", slots.busy())
                except Exception:  # each sweep logs its own; this keeps the thread going
                    log.exception("a sweep failed")
                stop.wait(max(0.0, sweep_every - (time.monotonic() - started)))

        def checking() -> None:  # the notebook against its records, every hour, apart
            while not stop.is_set():
                self.check_notes()
                stop.wait(retain_every)

        with ThreadPoolExecutor(slots.total) as pool:
            sweeper = threading.Thread(target=sweeping, name="a5s-sweeps", daemon=True)
            sweeper.start()
            checker = threading.Thread(target=checking, name="a5s-notebook", daemon=True)
            checker.start()
            while not stop.is_set():
                try:
                    with psycopg.connect(self.cfg.database_url, autocommit=True) as conn:
                        conn.execute("listen a5s_inbound")
                        while not stop.is_set():
                            for each in slots.pools():  # each agent's own, then the shared
                                while not stop.is_set() and slots.take(each) and handed(
                                        each, lambda each=each: self._claim(
                                            each, frozenset() if each else slots.pooled)):
                                    pass
                            for _ in conn.notifies(timeout=2, stop_after=1):
                                pass
                except psycopg.OperationalError:
                    log.exception("lost the database, so listening again shortly")
                    stop.wait(5)
            if busy := slots.busy():  # so whoever watches an upgrade sees why it waits
                log.info("Asked to stop: finishing %s in flight first, and taking no more",
                         "1 run" if busy == 1 else f"{busy} runs")
            sweeper.join()
            checker.join()
        log.info("Stopped, with every run it took finished")
