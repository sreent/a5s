"""The soak test's people, run by deploy/soak.sh on the stack the smoke test leaves running.

Each of the sample's people talks to each agent that serves them through a5s's own channel,
as the web chat does: one message at a time, waiting for the answer before saying the next
thing, for as many minutes as it's told. Ana also asks the assistant for long tasks, each to
be done in two runs, so two slices, and says yes to each. While a slice is at work, a quarter
of the way through, the assistant's worker is killed, and at three eighths the core, as a
crash or the out-of-memory killer would; half way, the core, the scheduler and the assistant's
workers restart, as an upgrade would; and at three quarters the scheduler is killed. Every 30
seconds it notes how much memory each of a5s's containers holds, and how many connections
Postgres has open. Then it checks that each message had one answer, in time, and that only
those at work when something was killed were told it couldn't finish; that every task she
started ended done, in two slices at least, and told her once, each by its number, with none
lost and no lease left over; that neither memory nor connections kept growing once the stack
had warmed up; and that no part logged an error but in the minutes after a kill. Standard
library only.

  A5S_PASSWORD=... python3 deploy/soak.py <minutes> <where to write what it found>
"""

import calendar
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
KILLED = (("worker-assistant", 0.25), ("gateway", 0.375), ("scheduler", 0.75))  # mid-slice
AFTER_KILL = 300  # seconds after a kill whose errors it explains: a run it cut off, and those
# whose scheduler it was, closed once its lease has lapsed two minutes, at the next sweep
CUT_OFF = ("I couldn't finish", "Something went wrong on my side")  # a5s's words for one
TASKS_EVERY = 60  # seconds between the tasks Ana asks for
TASK = "Please do this as a task: go through my open questions, in two runs"
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


def answers(token: str, message: str, within: float) -> list:
    """The answers to a message, waiting up to `within` seconds for one."""
    until, replies = time.monotonic() + within, []
    while not replies and time.monotonic() < until:
        wait = max(1, min(OBJECTIVE, int(until - time.monotonic())))
        replies = call("GET", f"{CHANNEL}/{message}?wait={wait}", token).get("replies") or []
    return replies


def talk(person: str, agent: str, until: float, said: list, lock: threading.Lock) -> None:
    """One person's conversation with one agent, until the time's up. A message at work as
    something is killed may wait for the core's sweep to say so, minutes on."""
    token, signed_in = "", 0.0
    while time.monotonic() < until:
        if time.monotonic() - signed_in > 240:  # the stand-in's tokens last five minutes
            token, signed_in = sign_in(person), time.monotonic()
        started, sent_at, cut = time.monotonic(), time.time(), False
        try:
            sent = call("POST", CHANNEL, token, {"agent": agent, "text": random.choice(ASKED)})
            replies = answers(token, sent["message"], AFTER_KILL + OBJECTIVE)
            outcome = "answered" if len(replies) == 1 else f"{len(replies)} answers"
            cut = any(str(r).startswith(CUT_OFF) for r in replies)
        except HTTPError as exc:
            outcome = f"refused: {exc.code} {exc.read()[:200]!r}"
        # whatever went wrong is what the test reports
        except Exception as exc:  # noqa: BLE001
            outcome = f"failed: {type(exc).__name__}: {exc}"
        with lock:
            said.append({"person": person, "agent": agent, "outcome": outcome, "cut_off": cut,
                         "sent_at": sent_at, "seconds": round(time.monotonic() - started, 2)})
        time.sleep(random.uniform(0.5, 3))


def asking(token_for, until: float, started: list, lock: threading.Lock) -> None:
    """Ana asks the assistant for a long task, and says yes to it, now and again."""
    while time.monotonic() < until:
        token = token_for()
        try:
            for text in (TASK, "Yes, start it"):
                sent = call("POST", CHANNEL, token, {"agent": "assistant", "text": text})
                replies = answers(token, sent["message"], AFTER_KILL + OBJECTIVE)
            if found := next((r for r in replies if r.startswith("Started T-")), None):
                with lock:  # by its number, as its owner knows it
                    started.append(int(re.match(r"Started T-(\d+)", found).group(1)))
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


def kill(part: str, at: float, killed: list, lock: threading.Lock) -> None:
    """Kill `part` at once, as a crash or the out-of-memory killer would, once a task's slice
    is at work after `at`, and start it again: which task's slice, and when."""
    time.sleep(max(0.0, at - time.monotonic()))
    task, until = None, time.monotonic() + 180
    while task is None and time.monotonic() < until:  # a slice at work, part way
        found = psql("select t.number from runs r join tasks t on t.id::text = "
                     "r.trigger->>'task' where r.closed_at is null and r.trigger->>'kind' = "
                     "'task' and r.opened_at < now() - interval '1 second' limit 1")
        task = int(found[0]) if found else None
        if task is None:
            time.sleep(0.5)
    container = f"{PROJECT}-{part}-1"
    subprocess.run(["docker", "kill", "--signal", "KILL", container], capture_output=True,
                   check=False)
    when = time.time()
    time.sleep(2)
    subprocess.run(["docker", "start", container], capture_output=True, check=False)
    with lock:
        killed.append({"part": part, "task": task, "at": when})
    print(f"Killed the {part}" + (f" as T-{task}'s slice was at work." if task else
                                  ", though no task's slice was at work."))


def psql(query: str) -> list[str]:
    return subprocess.run(
        ["docker", "exec", f"{PROJECT}-postgres-1", "psql", "-U", "a5s", "-d", "postgres",
         "-tAc", query], capture_output=True, text=True, check=False).stdout.split()


def settled() -> dict:
    """How the tasks stand once nothing more is due, waiting several minutes for that, as a
    slice a kill cut off ends once its scheduler's lease has lapsed two minutes, then waits
    a while to go on: how many ended each way; each, by its number, with how it ended, the
    step its work came to, its slices, those cut off, and how many times its owner was told
    it had, by its run or by
    a5s, whether at once or in a batch past the day's urgent messages; and how many leases,
    the scheduler's live ones and the tasks', are left."""
    for _ in range(240):
        stood = dict(line.split("|") for line in psql(
            "select status, count(*) from tasks group by status"))
        if not set(stood) & {"queued", "running", "waiting"}:  # all ended, or never begun
            break
        time.sleep(2)
    for _ in range(30):  # any run still finishing ends its lease: one left over stays
        leases = psql("select (select count(*) from leases where expires_at > now()) + "
                      "(select count(*) from tasks where lease_id is not null)")
        if leases == ["0"]:
            break
        time.sleep(2)
    each = {}
    for line in psql(
            "select t.number, t.status, t.step, count(r.id), count(r.id) filter (where r.outcome is "
            "distinct from 'done'), (select count(*) from turns u join runs s on s.id = u.run_id "
            "where u.role = 'agent' and s.trigger->>'task' = t.id::text) + (select count(*) "
            "from turns u where u.role = 'notice' and u.content like 'T-' || t.number || "
            "', the task you asked the %') from tasks t left join runs r on r.trigger->>'kind' "
            "= 'task' and r.trigger->>'task' = t.id::text where t.parent is null "
            "group by t.id order by t.number"):
        number, status, step, slices, cut, told = line.split("|")
        each[int(number)] = {"status": status, "step": int(step or 0), "slices": int(slices),
                             "cut_off": int(cut), "told": int(told)}
    return {"tasks": {k: int(v) for k, v in stood.items()}, "each": each,
            "told": sum(t["told"] for t in each.values()),
            "leases_left": int(leases[0]) if leases else None}


def errors(since: float, killed: list) -> tuple[list[str], int]:
    """What a5s's parts logged as errors since `since`: those no kill explains, and how many
    the minutes after one do, such as a run it cut off."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since))
    found, explained = [], 0
    for part in PARTS[:-1]:  # not Postgres's own
        logged = subprocess.run(["docker", "logs", "--timestamps", "--since", stamp,
                                 f"{PROJECT}-{part}-1"], capture_output=True, text=True,
                                check=False)
        for line in (logged.stdout + logged.stderr).splitlines():
            if not re.search(r"Traceback|ERROR|CRITICAL", line):
                continue
            at = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", line)
            when = calendar.timegm(time.strptime(at.group(1), "%Y-%m-%dT%H:%M:%S")) if at else 0
            if any(k["at"] - 2 <= when <= k["at"] + AFTER_KILL for k in killed):
                explained += 1
            else:
                found.append(f"{part}: {line[:300]}")
    return found, explained


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
    began, killed = time.time(), []
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
    threads += [threading.Thread(target=kill, args=(part, time.monotonic() + minutes * 60 * share,
                                                    killed, lock)) for part, share in KILLED]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    problems = []
    failed = [s for s in said if s["outcome"] != "answered"]
    if failed:
        problems.append(f"{len(failed)} of {len(said)} messages weren't answered once: "
                        + "; ".join(sorted({s["outcome"] for s in failed}))[:1000])
    cut = [s for s in said if s["cut_off"]]  # told it couldn't finish: only as a kill would
    unexplained = [s for s in cut if not any(
        s["sent_at"] - 5 <= k["at"] <= s["sent_at"] + s["seconds"] + 5 for k in killed)]
    if unexplained:
        problems.append(f"{len(unexplained)} messages were told it couldn't finish, though "
                        "nothing was killed as they were at work")
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
    each = tasks["each"]
    for number in started:  # each task Ana started, by its number
        task = each.get(number)
        if task is None:
            problems.append(f"T-{number}, which Ana started, isn't among the tasks")
        elif task["status"] != "done" or task["told"] != 1:
            problems.append(f"T-{number} ended {task['status']}, and Ana was told it had "
                            f"{task['told']} times, not once")
        elif task["slices"] < 2 or task["step"] != 2:  # each half kept by a slice of its own
            problems.append(f"T-{number} ended at step {task['step']} of 2, in "
                            f"{task['slices']} slices")
    if tasks["leases_left"]:
        problems.append(f"{tasks['leases_left']} leases were left once nothing was due")
    if len(killed) < len(KILLED) or not all(k["task"] for k in killed):
        problems.append("not every kill came as a task's slice was at work: "
                        + "; ".join(f"the {k['part']}" for k in killed if not k["task"]))
    logged, explained = errors(began, killed)
    if logged:
        problems.append(f"a5s's parts logged {len(logged)} errors no kill explains, such as: "
                        + " | ".join(logged[:5]))

    found = {"minutes": minutes, "messages": len(said), "answered": len(seconds),
             "p50_seconds": p50, "p90_seconds": p90, "memory": memory,
             "connections": {"warm": round(warm, 1), "last": round(last, 1)},
             "tasks": {"started": len(started), **tasks}, "killed": killed,
             "cut_off": len(cut), "errors_after_kills": explained,
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
    for k in killed:
        hit = each.get(k["task"], {})
        print(f"The {k['part']}, killed as T-{k['task']}'s slice was at work: T-{k['task']} "
              f"ended {hit.get('status')} in {hit.get('slices')} slices, "
              f"{hit.get('cut_off')} cut off, and Ana was told once." if hit.get("told") == 1
              else f"The {k['part']}, killed as T-{k['task']}'s slice was at work: {hit}.")
    print(f"Messages at work as something was killed, told it couldn't finish: {len(cut)}. "
          f"Errors logged in the minutes after a kill: {explained}; at any other time: "
          f"{len(logged)}.")
    if problems:
        raise SystemExit("The soak test found:\n- " + "\n- ".join(problems))


if __name__ == "__main__":
    main()
