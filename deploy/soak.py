"""The soak test's people, run by deploy/soak.sh on the stack the smoke test leaves running.

Each of the sample's people talks to each agent that serves them through a5s's own channel,
as the web chat does: one message at a time, waiting for the answer before saying the next
thing, for as many minutes as it's told. Ana also asks the assistant for long tasks, and says
yes to each, and half way through, the core, the scheduler and the assistant's workers restart. Every
30 seconds it notes how much memory each of a5s's containers holds, and how many connections
Postgres has open. Then it checks that each message had one answer, in time; that every task
she started ended done, and told her once, with none lost and no lease left over; and that
neither memory nor connections kept growing once the stack had warmed up, and says how it
went. Standard library only.

  A5S_PASSWORD=... python3 deploy/soak.py <minutes> <where to write what it found>
"""

import json
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHANNEL = "http://127.0.0.1:8703/channels/local/messages"
SIGN_IN = "http://127.0.0.1:8180/realms/a5s/protocol/openid-connect/token"
PROJECT = "a5s-smoke"
PARTS = ("gateway", "channels", "scheduler", "worker", "worker-assistant", "worker-watcher",
         "anchor", "postgres")
RESTARTED = ("gateway", "scheduler", "worker-assistant")  # half way, as an upgrade would
TASKS_EVERY = 60  # seconds between the tasks Ana asks for
# Who talks to which agent: the agents that serve each of them once the smoke test is done
TALKS = [("ana", "assistant"), ("ana", "watcher"), ("ben", "assistant"), ("ben", "watcher"),
         ("chen", "assistant")]
ASKED = ["Which questions mention an invoice?", "Is there anything about a refund?",
         "Which of my questions are overdue?", "Did anyone ask about a credit note?",
         "What's open for Northwind?", "Which questions mention a payment?"]
OBJECTIVE = 120  # seconds: nine in ten answers within this, a5s's own objective
WARMED = 0.2  # the share of the run it takes to warm up, after which nothing should grow


def call(method: str, url: str, token: str | None = None, body: dict | None = None,
         form: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = None
    if body is not None:
        headers["Content-Type"], data = "application/json", json.dumps(body).encode()
    elif form is not None:
        headers["Content-Type"], data = ("application/x-www-form-urlencoded",
                                         urlencode(form).encode())
    with urlopen(Request(url, data, headers, method=method), timeout=150) as answer:
        return json.load(answer)


def sign_in(person: str) -> str:
    return call("POST", SIGN_IN, form={"grant_type": "password", "client_id": "a5s-local",
                                       "scope": "openid", "username": person,
                                       "password": os.environ["A5S_PASSWORD"]})["access_token"]


def talk(person: str, agent: str, until: float, said: list, lock: threading.Lock) -> None:
    """One person's conversation with one agent, until the time's up."""
    token, signed_in = "", 0.0
    while time.monotonic() < until:
        if time.monotonic() - signed_in > 240:  # the stand-in's tokens last five minutes
            token, signed_in = sign_in(person), time.monotonic()
        started = time.monotonic()
        try:
            sent = call("POST", CHANNEL, token, {"agent": agent, "text": random.choice(ASKED)})
            answer = call("GET", f"{CHANNEL}/{sent['message']}?wait={OBJECTIVE}", token)
            replies = answer.get("replies") or []
            outcome = "answered" if len(replies) == 1 else f"{len(replies)} answers"
        except HTTPError as exc:
            outcome = f"refused: {exc.code} {exc.read()[:200]!r}"
        # whatever went wrong is what the test reports
        except Exception as exc:  # noqa: BLE001
            outcome = f"failed: {type(exc).__name__}: {exc}"
        with lock:
            said.append({"person": person, "agent": agent, "outcome": outcome,
                         "seconds": round(time.monotonic() - started, 2)})
        time.sleep(random.uniform(0.5, 3))


def asking(token_for, until: float, started: list, lock: threading.Lock) -> None:
    """Ana asks the assistant for a long task, and says yes to it, now and again."""
    while time.monotonic() < until:
        token = token_for()
        try:
            for text in ("Please do this as a task: go through my open questions",
                         "Yes, start it"):
                sent = call("POST", CHANNEL, token, {"agent": "assistant", "text": text})
                answer = call("GET", f"{CHANNEL}/{sent['message']}?wait={OBJECTIVE}", token)
            if any(r.startswith("Started ") for r in answer.get("replies") or []):
                with lock:
                    started.append(answer["replies"][0])
        except Exception as exc:  # noqa: BLE001 - the end checks find what it left undone
            print(f"Asking for a task failed: {type(exc).__name__}: {exc}")
        time.sleep(TASKS_EVERY)


def restart(at: float) -> None:
    """Restart the core, the scheduler and the assistant's workers, one after another, once,
    at `at`."""
    time.sleep(max(0.0, at - time.monotonic()))
    subprocess.run(["docker", "restart", *(f"{PROJECT}-{part}-1" for part in RESTARTED)],
                   capture_output=True, check=False)
    print(f"Restarted {' and '.join(RESTARTED)} half way.")


def psql(query: str) -> list[str]:
    return subprocess.run(
        ["docker", "exec", f"{PROJECT}-postgres-1", "psql", "-U", "a5s", "-d", "postgres",
         "-tAc", query], capture_output=True, text=True, check=False).stdout.split()


def settled() -> dict:
    """How the tasks stand once nothing more is due, waiting a few minutes for that: how
    many ended each way; how many times their owners were told one had, by its run or by
    a5s, whether at once or in a batch past the day's urgent messages; and how many leases,
    the scheduler's and the tasks', are left."""
    for _ in range(90):
        stood = dict(line.split("|") for line in psql(
            "select status, count(*) from tasks group by status"))
        if not set(stood) & {"queued", "running", "waiting"}:  # all ended, or never begun
            break
        time.sleep(2)
    for _ in range(30):  # any run still finishing ends its lease: one left over stays
        leases = psql("select (select count(*) from leases) + (select count(*) from tasks "
                      "where lease_id is not null)")
        if leases == ["0"]:
            break
        time.sleep(2)
    told = psql("select (select count(*) from turns t join runs r on r.id = t.run_id where "
                "t.role = 'agent' and r.trigger->>'kind' = 'task') + (select count(*) from "
                "turns where role = 'notice' and content like 'T-%, the task you asked the %')")
    return {"tasks": {k: int(v) for k, v in stood.items()},
            "told": int(told[0]) if told else None,
            "leases_left": int(leases[0]) if leases else None}


def mebibytes(usage: str) -> float:
    number, unit = re.fullmatch(r"([\d.]+)\s*([KMG]i?B|B)", usage.strip()).groups()
    return float(number) * {"B": 1 / 2**20, "KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1,
                            "GiB": 1024, "GB": 1024}[unit]


def sample(until: float, samples: list) -> None:
    """The memory of each part, and Postgres's connections, every 30 seconds."""
    while time.monotonic() < until:
        at = time.monotonic()
        stats = subprocess.run(["docker", "stats", "--no-stream", "--format",
                                "{{.Name}}\t{{.MemUsage}}"], capture_output=True, text=True,
                               check=False).stdout
        memory = {}
        for line in stats.splitlines():
            name, usage = line.split("\t")
            part = re.sub(r"-\d+$", "", name.removeprefix(f"{PROJECT}-"))
            if part in PARTS:
                memory[part] = round(mebibytes(usage.split("/")[0]), 1)
        counted = subprocess.run(
            ["docker", "exec", f"{PROJECT}-postgres-1", "psql", "-U", "a5s", "-d", "postgres",
             "-tAc", "select count(*) from pg_stat_activity where backend_type = 'client backend'"],
            capture_output=True, text=True, check=False).stdout.strip()
        samples.append({"memory": memory, "connections": int(counted) if counted else None})
        time.sleep(max(0.0, 30 - (time.monotonic() - at)))


def grew(samples: list, measure) -> tuple[float, float]:
    """A measure's mean just after warming up, and over the last fifth of the run."""
    n = len(samples)
    warm = [measure(s) for s in samples[int(n * WARMED):int(n * 2 * WARMED)]]
    last = [measure(s) for s in samples[-max(1, int(n * WARMED)):]]
    warm, last = [v for v in warm if v is not None], [v for v in last if v is not None]
    return (statistics.mean(warm) if warm else 0.0), (statistics.mean(last) if last else 0.0)


def main() -> None:
    minutes, found_at = float(sys.argv[1]), sys.argv[2]
    until, said, samples, lock = time.monotonic() + minutes * 60, [], [], threading.Lock()
    threads = [threading.Thread(target=talk, args=(person, agent, until, said, lock))
               for person, agent in TALKS]
    threads.append(threading.Thread(target=sample, args=(until, samples)))
    signed: dict[str, float | str] = {}

    def ana() -> str:  # her sign-in, for asking for tasks, renewed as the stand-in's expire
        if time.monotonic() - float(signed.get("at", 0.0)) > 240:
            signed.update(token=sign_in("ana"), at=time.monotonic())
        return str(signed["token"])

    started: list = []
    threads.append(threading.Thread(target=asking, args=(ana, until, started, lock)))
    threads.append(threading.Thread(target=restart, args=(time.monotonic() + minutes * 30,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    problems = []
    failed = [s for s in said if s["outcome"] != "answered"]
    if failed:
        problems.append(f"{len(failed)} of {len(said)} messages weren't answered once: "
                        + "; ".join(sorted({s["outcome"] for s in failed}))[:1000])
    seconds = sorted(s["seconds"] for s in said if s["outcome"] == "answered")
    p50 = statistics.median(seconds) if seconds else None
    p90 = seconds[int(len(seconds) * 0.9) - 1] if len(seconds) >= 10 else None
    if p90 is not None and p90 > OBJECTIVE:
        problems.append(f"nine in ten answers took up to {p90:.0f}s, past the {OBJECTIVE}s objective")
    memory = {}
    for part in PARTS:
        warm, last = grew(samples, lambda s, part=part: s["memory"].get(part))
        memory[part] = {"warm_mib": round(warm, 1), "last_mib": round(last, 1)}
        allowed = max(48.0, warm * 0.25)  # what caches and the allocator may take, but no leak
        if part != "postgres" and last - warm > allowed:
            problems.append(f"the {part}'s memory grew from {warm:.0f} MiB to {last:.0f} MiB")
    warm, last = grew(samples, lambda s: s["connections"])
    if last > warm + 3:
        problems.append(f"Postgres's connections grew from {warm:.1f} to {last:.1f}")
    tasks = settled()
    done = tasks["tasks"].get("done", 0)
    if done < len(started):
        problems.append(f"of the {len(started)} tasks Ana started, {done} ended done: "
                        f"{tasks['tasks']}")
    if tasks["told"] != done:  # each, once
        problems.append(f"{done} tasks ended done, but their owner was told one had "
                        f"{tasks['told']} times")
    if tasks["leases_left"]:
        problems.append(f"{tasks['leases_left']} leases were left once nothing was due")

    found = {"minutes": minutes, "messages": len(said), "answered": len(seconds),
             "p50_seconds": p50, "p90_seconds": p90, "memory": memory,
             "connections": {"warm": round(warm, 1), "last": round(last, 1)},
             "tasks": {"started": len(started), **tasks},
             "samples": samples, "problems": problems}
    with open(found_at, "w") as out:
        json.dump(found, out, indent=1)
    print(f"{len(said)} messages from {len(TALKS)} conversations over {minutes:g} minutes: "
          f"{len(seconds)} answered once, half within {p50 or 0:.1f}s"
          + (f", nine in ten within {p90:.1f}s." if p90 is not None else "."))
    print("Memory, just after warming up and at the end: " + "; ".join(
        f"{part} {m['warm_mib']:.0f} to {m['last_mib']:.0f} MiB" for part, m in memory.items()))
    print(f"Postgres's connections: {warm:.1f} to {last:.1f}.")
    print(f"Tasks Ana started: {len(started)}; how they ended: {tasks['tasks']}; times she "
          f"was told one had: {tasks['told']}; leases left: {tasks['leases_left']}.")
    if problems:
        raise SystemExit("The soak test found:\n- " + "\n- ".join(problems))


if __name__ == "__main__":
    main()
