"""The sandbox (docs/studio.md, step 2): a deployment of a5s of its own, where people try the
agents they're making before anyone releases them.

It runs the deployment's scenario on a database of its own, with the scenario's made-up records
and fakes, and a stand-in model by default, or a real one, where the sandbox has its key, when
asked. It isn't the deployment people work in, whatever anyone asks of it: it has none of that
one's records, channels, budgets or keys. When it starts, it makes keys of its own for the
scenario's made-up people, and signs its own settings with them, so each draft tried here gets
an agent and an instance of its own, as a release and signed settings give any.

The studio, in the deployment people work in, sends it a draft's files, who to be among the
made-up people, and what to say. The sandbox runs the draft as a5s runs any agent, through the
core's checks, and says what it answered, each call to a tool with the policy's decision, and
what the model was sent and said, which, all being made up here, it can show whole.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, LiteralString

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from a5s import authoring, build, cases, db, definitions, describing
from a5s.config import Config, load_models
from a5s.core import (
    extractor,
    inbox,
    judging,
    measures,
    models,
    registry,
    retention,
    signing,
    studio,
)
from a5s.core.gateway import Gateway
from a5s.core.gateway import create_app as core_app
from a5s.services.scheduler import Scheduler

log = logging.getLogger(__name__)

STAND_IN = "stand-in"  # the model a draft tries with, unless a real one is asked for
STAND_IN_URL = "https://stand-in.sandbox.a5s/v1"  # never leaves the sandbox: it answers itself
# The most a draft tried here may spend, whatever its own budgets say: those of an agent
# that names none, as the reference assistant has them
BUDGET: Final = definitions.Budget()
SIGNERS = ("instance-approver", "part-owner:")  # whose signatures its own settings carry
KEY = re.compile(r"[a-z0-9]{6,32}")  # a draft's, as the studio names it to the sandbox
QUIET: Final = "1 hour"  # how long it keeps what's said in it, after it's quiet: a try's alone
# What lasts while people work but in the sandbox goes an hour after it's quiet, with what's
# said: a note or a preference one author's try kept would otherwise reach every other's
# tries as that made-up person, and a held change, which nobody there decides, would wait for
# good (round 12, C5)
QUIETED: Final[tuple[tuple[str, LiteralString], ...]] = (
    ("notes", ("delete from profile_notes where greatest(offered_at, confirmed_at, ended_at) "
               "< now() - %(kept)s::interval")),
    ("preferences", "delete from preferences where set_at < now() - %(kept)s::interval"),
    ("reminders", ("delete from reminders where greatest(offered_at, confirmed_at) "
                   "< now() - %(kept)s::interval")),
    ("decisions", ("delete from proposal_decisions where digest in (select digest from "
                   "proposals where proposed_at < now() - %(kept)s::interval)")),
    ("changes", "delete from proposals where proposed_at < now() - %(kept)s::interval"),
)
SWEEP_EVERY = 600  # seconds between its sweeps


class Refused(ValueError):
    """Why the sandbox won't try a draft as asked, in words."""


# Its stand-in model

def _keyed(found: Any) -> list[str]:
    """The records' keys in what a tool answered, at any depth."""
    if isinstance(found, list):
        return [key for item in found for key in _keyed(item)]
    if not isinstance(found, dict):
        return []
    own = [found["key"]] if isinstance(found.get("key"), str) else []
    return own + [key for value in found.values() for key in _keyed(value)]


def _answer(body: dict, message: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "id": f"stand-in-{time.time_ns()}", "object": "chat.completion", "created": int(time.time()),
        "model": body.get("model", "stand-in-1"),
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})


class StandIn:
    """The sandbox's stand-in model, an OpenAI-compatible provider that thinks nothing: asked
    something, it looks it up with the first tool it's offered whose name begins with search,
    then says what it found. Asked to draft an agent from a description, it gives only the tools
    that only read whose words match it (describing.py); asked to judge a test case's step, it
    looks only for the words its criterion quotes and the tools it names (cases.py). A real
    model, where the sandbox has one, says what the agent, or its judge, would."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        first = body["messages"][0]
        if first.get("role") == "system" and str(first.get("content") or "").startswith(describing.DESCRIBING):
            return _answer(body, {"role": "assistant", "content": json.dumps(describing.stand_in(body))})
        if first.get("role") == "system" and first.get("content") == cases.JUDGING:
            asked = str(body["messages"][-1].get("content") or "")
            return _answer(body, {"role": "assistant", "content": json.dumps(cases.stand_in_verdict(asked))})
        last = body["messages"][-1]
        if last.get("role") == "tool":
            content = str(last.get("content") or "")
            try:
                found = json.loads(content) if content[:1] in ("[", "{") else []
            except ValueError:
                found = []
            keys = ", ".join(dict.fromkeys(_keyed(found))) or "nothing it could name"
            return _answer(body, {"role": "assistant",
                                  "content": f"(A stand-in model.) I looked it up and found {keys}."})
        tools = [t["function"] for t in body.get("tools") or [] if t.get("type") == "function"]
        search = next((t for t in tools if t["name"].startswith("search")), None)
        if search is None:
            return _answer(body, {"role": "assistant", "content": (
                "(A stand-in model.) It has no tool to look things up with, so it says only this: "
                "try a real model to see what the agent would say.")})
        said = str(last.get("content") or "").split("] ", 1)[-1]  # after when it was said
        words = re.findall(r"[a-z0-9-]+", said.lower())
        fields = (search.get("parameters") or {}).get("properties") or {}
        text = next((name for name, spec in fields.items() if spec.get("type") == "string"), None)
        return _answer(body, {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call-{time.time_ns()}", "type": "function", "function": {
                "name": search["name"],
                "arguments": json.dumps({text: words[-1] if words else ""} if text else {})}}]})


class Recording:
    """What a try's model calls were sent, and what came back, as they went: heard as each
    answer comes, by whichever way it went, to a real provider, through any proxy the
    environment names, or to the stand-in."""

    def __init__(self) -> None:
        self.calls: list[dict] | None = None  # while a try is under way

    def heard(self, response: httpx.Response) -> None:
        if self.calls is None:
            return
        response.read()
        try:
            sent, came = json.loads(response.request.content), json.loads(response.content)
        except ValueError:
            sent, came = None, None
        if isinstance(sent, dict) and "messages" in sent:
            self.calls.append({"sent": sent, "came": came, "status": response.status_code})


# The sandbox itself

def _serve(app: Any) -> tuple[uvicorn.Server, str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("a part of the sandbox didn't start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}"


def _fresh(folder: Path) -> dict[str, str]:
    """New keys for each of a scenario's made-up people: their public keys where the scenario
    reads them, and their private keys, which only the sandbox holds, to sign its settings."""
    people = (yaml.safe_load((folder / "data.yaml").read_text()) or {}).get("people") or []
    keys = folder / "keys"
    keys.mkdir(exist_ok=True)
    held = {}
    for person in people:
        private, public = signing.keypair()
        (keys / f"{person['id']}.pub").write_text(public + "\n")
        held[person["id"]] = private
    return held


@dataclass
class Sandbox:
    cfg: Config  # its own, on its own copy of the scenario and the agents
    admin: str  # its own database, as its administrator
    gateway: Gateway
    channels_url: str
    keys: dict[str, str]  # its made-up people's private keys, which it made
    standing: dict  # its settings, as it signs them, with an instance for each draft tried
    recording: Recording  # its model calls, to a real provider or to the stand-in
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def scenario(self) -> Any:
        return build.scenario(self.cfg)

    def people(self) -> list[dict]:
        found = (yaml.safe_load((self.cfg.scenario_dir / "data.yaml").read_text()) or {}).get("people") or []
        return [{"id": p["id"], "name": p.get("name") or p["id"]} for p in found]

    def models(self) -> list[str]:
        """The stand-in, and each approved model the sandbox may call: one it has the key for,
        or one on the organisation's own network, which needs none."""
        approved = load_models(self.cfg.models_file)
        return [STAND_IN] + sorted(alias for alias, m in approved.items()
                                   if alias != STAND_IN and (m.key_env is None or m.api_key))

    def _settle(self) -> None:
        """Sign its settings as it stands, as each instance approver and part owner of its own
        made-up directory, and apply them, as a5s applies any."""
        self.standing["serial"] = int(self.standing.get("serial", 0)) + 1
        raw = yaml.safe_dump(self.standing, sort_keys=True).encode()
        folder = self.cfg.scenario_dir
        scenario = self.scenario
        signers = [who for who in self.keys
                   if (p := scenario.person(who)) and any(r.startswith(SIGNERS) for r in p.roles)]
        (folder / "settings.yaml").write_bytes(raw)
        (folder / "settings.sig").write_text(yaml.safe_dump({"signatures": [
            {"signer": who, "value": signing.sign(self.keys[who], raw)} for who in signers]}))
        with db.transaction(self.admin) as conn:
            applied = registry.apply(conn, self.gateway.definitions, scenario.settings(),
                                     scenario.tools(), scenario.person, scenario.name)
        if applied.refused:
            raise Refused("; ".join(applied.refused))

    def _install(self, agent: str, files: dict[str, str], model: str) -> None:
        """A draft as an agent of the sandbox's own: its files, named for the sandbox, on the
        model asked for, with its tools pinned as the scenario has them, and its budgets no
        more than the sandbox's own. A draft it refuses leaves nothing behind, so no later try
        loads it, in its own place or another's."""
        if model not in self.models():
            raise Refused(f"the sandbox can't call {model}: it has {', '.join(self.models())}")
        folder = self.cfg.agents_dir / agent
        # Written and checked apart first: one it refuses leaves what was there as it was, so
        # an earlier try of it, and every other, still runs (round 12, C4)
        scratch = Path(tempfile.mkdtemp(prefix=".installing-", dir=self.cfg.agents_dir.parent))
        try:
            self._written(scratch / agent, agent, files, model)
            shutil.rmtree(folder, ignore_errors=True)
            shutil.move(scratch / agent, folder)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        try:
            found = definitions.load_all(self.cfg.agents_dir)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        for definition in found.values():  # whatever a draft gives itself to spend
            definition.budget = definitions.Budget(
                per_run=min(definition.budget.per_run, BUDGET.per_run),
                per_person_per_day=min(definition.budget.per_person_per_day,
                                       BUDGET.per_person_per_day))
        self.gateway.definitions.clear()  # the same mapping the channels app reads
        self.gateway.definitions.update(found)

    def _written(self, folder: Path, agent: str, files: dict[str, str], model: str) -> None:
        """A draft's files in its folder, named and on its model as the sandbox has them, and
        checked: Refused if they aren't, or if they run as another agent, or on another model,
        than the sandbox set."""
        for path, text in files.items():
            if path == "tools.lock":
                continue
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        spec = folder / "agent.yaml"
        text = spec.read_text() if spec.exists() else ""
        for name, value in (("id", agent), ("model", model)):  # its value on the line, or the next
            text, found = re.subn(rf"(?m)^{name}:[ \t]*(?:\n[ \t]+)?[^\s#]+", f"{name}: {value}",
                                  text, count=1)
            if not found:
                raise Refused(f"its agent.yaml names no {name}")
        spec.write_text(text)
        tools = self.scenario.tools()
        try:
            definitions.pin(folder, {n: t.schema_hash for n, t in tools.items()})
        except (ValueError, TypeError, OSError, yaml.YAMLError):
            pass  # its checks say why
        if problems := authoring.check(folder, tools, load_models(self.cfg.models_file)):
            raise Refused("; ".join(problems))
        loaded = definitions.load(folder)
        if (loaded.id, loaded.model) != (agent, model):  # whatever else its YAML says
            raise Refused("its agent.yaml names its id and its model each once, on a line of "
                          "its own, as id: and model:")

    def _serving(self, instance: str, agent: str, person: str) -> None:
        """An instance of a draft's agent, which serves `person` too, in its settings."""
        instances = self.standing.setdefault("instances", {})
        serving = set((instances.get(instance) or {}).get("serves") or [])
        instances[instance] = {"definition": agent, "serves": sorted(serving | {person}),
                               "parts": self.parts, "level": 1, "owner": person}

    def _said(self, instance: str, person: str, text: str) -> tuple[str, dict | None, list[dict]]:
        """Say something to an instance, as a person: what it answered, the run that answered
        it, if one opened for it, and each call to the model."""
        with db.transaction(self.admin) as conn:  # by the database's clock, as runs open
            since = (conn.execute("select now() as at").fetchone() or {}).get("at")
        self.recording.calls = []
        try:
            sent = httpx.post(f"{self.channels_url}/channels/local/messages", timeout=60,
                              json={"person": person, "agent": instance, "text": text})
            if sent.status_code != 202:
                raise Refused(str(sent.json().get("detail")))
            Scheduler(self.cfg, self.gateway.scenario).answer_waiting()
            said = httpx.get(f"{self.channels_url}/channels/local/messages/{sent.json()['message']}",
                             params={"person": person}, timeout=60).json()["replies"]
        finally:
            calls, self.recording.calls = self.recording.calls or [], None
        with db.transaction(self.admin) as conn:
            last = conn.execute("select id::text as id, outcome from runs where instance_id = %s "
                                "and opened_at >= %s order by opened_at desc limit 1",
                                (instance, since)).fetchone()
            run = None
            if last is not None:
                run = studio.run(conn, self.scenario, last["id"])
                if run is not None:  # how it ended: in its own answer, or not
                    run["outcome"] = last["outcome"]
        return "\n".join(said), run, calls

    def turn(self, key: str, files: dict[str, str], person: str, text: str, model: str) -> dict:
        """Try a draft: say `text` to it as `person`, one of the made-up people, and what came
        of it: what it answered, the run, with each call to a tool and the policy's decision,
        and each call to the model, what it was sent and what it said."""
        if not KEY.fullmatch(key):
            raise Refused("a draft is tried by its key, of lower case letters and digits")
        if person not in {p["id"] for p in self.people()}:
            raise Refused(f"the sandbox has nobody called {person}")
        agent = f"try-{key}"
        with self.lock:
            self._install(agent, files, model)
            self._serving(agent, agent, person)
            self._settle()
            reply, run, calls = self._said(agent, person, text)
        return {"agent": agent, "reply": reply, "run": run, "model_calls": calls}

    def describe(self, words: str, model: str) -> dict:
        """What a model proposes for a new agent described in `words`, of what the sandbox's
        scenario offers, each with why, and each call to the model, what it was sent and said:
        a proposal, never a draft, which the studio makes from it (describing.py)."""
        if model not in self.models():
            raise Refused(f"the sandbox can't call {model}: it has {', '.join(self.models())}")
        if not words.strip():
            raise Refused("say what it's for, in your own words")
        scenario = self.scenario
        found = load_models(self.cfg.models_file)[model]
        offered = describing.offer(scenario.tools(), sorted({o.source for o in scenario.obligations()}))
        body = describing.asked(found.api, found.alias, words, offered)
        with self.lock:
            self.recording.calls = []
            try:
                status, data = models.forward(found, models.screen(found.api, body)[0], self.gateway.http)
            except models.ModelUnavailable as e:
                raise Refused(f"the sandbox couldn't ask {model}: {e}") from None
            finally:
                calls, self.recording.calls = self.recording.calls or [], None
        if status >= 400:
            raise Refused(f"{model} said {status}: try again, or another model")
        proposed = describing.proposal(extractor.reply_text(found.api, data))
        if proposed is None:
            raise Refused(f"what {model} answered doesn't read as a proposal: try again, or another model")
        return {"proposal": proposed, "model": model, "model_calls": calls}

    def case(self, key: str, files: dict[str, str], model: str, number: int) -> dict:
        """Run one of a draft's test cases, by its place among them, as the agent's suite runs
        it, in a conversation of its own: what it answered at each step, the tools it used, and
        whether that's as the case says, and if not, why. A case that needs what the suite
        alone does, such as a time to be at, it doesn't run, and says so."""
        if not KEY.fullmatch(key):
            raise Refused("a draft is tried by its key, of lower case letters and digits")
        try:
            found = cases.found(files)
        except cases.Unreadable as e:
            raise Refused(str(e)) from None
        if not 0 <= number < len(found):
            raise Refused(f"the draft has {len(found)} test cases, not a case {number + 1}")
        case = found[number]
        shown = {"name": case["name"], "file": case["file"]}
        if alone := cases.suite_alone(case):
            return {**shown, "ran": False, "why": f"it needs {', '.join(alone)}, which the "
                                                  "agent's suite alone runs"}
        person = case.get("as", "ana")  # as the suite says it, unless the case says
        if person not in {p["id"] for p in self.people()}:
            return {**shown, "ran": False, "why": f"it's said as {person}, and the sandbox has "
                                                  "nobody called that"}
        # The draft as an agent of its own, for this case alone: a conversation is a person's
        # with an agent, so each case starts one afresh, as the suite's do
        agent = f"case-{secrets.token_hex(5)}"
        steps, problems = [], []
        started, spent = time.monotonic(), {"in": 0, "out": 0, "cached": 0}  # what it took
        with self.lock:
            instances = self.standing.setdefault("instances", {})
            for done in [name for name in instances if name.startswith("case-")]:
                del instances[done]  # an earlier case's, which its settings retire
                shutil.rmtree(self.cfg.agents_dir / done, ignore_errors=True)
            self._install(agent, files, model)
            self._serving(agent, agent, person)
            self._settle()
            for n, step in enumerate(case["steps"], 1):
                said = cases.dated(str(step["say"]))
                reply, run, _ = self._said(agent, person, said)
                for kind in spent:  # its own runs' tokens: a judge's are the same on any model
                    spent[kind] += int((run or {}).get(f"tokens_{kind}") or 0)
                called = used(run)
                wrong = cases.check(step, reply, called, case.get("own_values") == "allowed")
                if why := cases.unanswered(run["outcome"] if run else None):
                    wrong.insert(0, why)  # a5s's own words pass no case's checks
                done = {"say": step["say"], "reply": reply, "called": called}
                if criterion := step.get("judged"):  # where it can be right in more than one way
                    done["judged"] = verdict = self._judged(agent, model, str(criterion), said,
                                                            reply, called)
                    if verdict["grade"] is None:
                        wrong.append(f"nobody judged it: {verdict['why']}")
                    elif verdict["grade"] != "right":
                        wrong.append(f"its judge found it {verdict['grade']}: {verdict['why']}")
                problems += [f"step {n}: {w}" for w in wrong]
                steps.append({**done, "wrong": wrong})
        priced = measures.priced(load_models(self.cfg.models_file).get(model), spent["in"],
                                 spent["out"], spent["cached"])
        return {**shown, "ran": True, "passed": not problems, "problems": problems, "steps": steps,
                "model": model, "seconds": round(time.monotonic() - started, 2),
                "tokens": spent["in"] + spent["out"], "cost": priced}

    def _judged(self, agent: str, model: str, criterion: str, said: str, reply: str,
                called: list[str]) -> dict:
        """What a judge says of a step a case says what a right answer is for: its grade, right,
        wrong or critical, and why, and which model judged it, or why none could. A draft tried
        on the stand-in is judged by it too, by words alone; on a real model, by the judge its
        definition names, where the sandbox can call it."""
        judge: str | None = STAND_IN
        if model != STAND_IN:
            definition = self.gateway.definitions.get(agent)
            judge = definition.evaluation.judge if definition and definition.evaluation else None
            if judge is None:
                return {"grade": None, "why": "the draft names no judge", "judge": None}
            if judge not in self.models():
                return {"grade": None, "why": f"the sandbox can't call its judge, {judge}",
                        "judge": judge}
        found = load_models(self.cfg.models_file)[judge]
        body = extractor.asked(found.api, found.alias, cases.JUDGING,
                               cases.judging(criterion, said, reply, called))
        try:
            status, data = models.forward(found, models.screen(found.api, body)[0], self.gateway.http)
        except models.ModelUnavailable as e:
            return {"grade": None, "why": f"the sandbox couldn't ask {judge}: {e}", "judge": judge}
        verdict = judging.verdict(extractor.reply_text(found.api, data)) if status < 400 else None
        if verdict is None:
            return {"grade": None, "why": f"what {judge} answered doesn't read as a grade",
                    "judge": judge}
        return {"grade": verdict[0], "why": verdict[1], "judge": judge}

    def forget(self) -> dict[str, int]:
        """Sweep what's past its time, as a5s's retention sweep does, but with what's said
        here gone an hour after it's quiet, not a year: long enough to try a draft over a
        few turns, and no longer, since someone may have said there what they shouldn't."""
        with db.transaction(self.admin) as conn:
            gone = retention.sweep(conn, self.gateway.clock(), self.scenario.name, kept=QUIET)
            for kind, sql in QUIETED:  # and what lasts where people work, here an hour after
                if count := conn.execute(sql, {"kept": QUIET}).rowcount:
                    gone[kind] = gone.get(kind, 0) + count
            return gone

    @property
    def parts(self) -> list[str]:
        """Every part its scenario's instances work in: a draft tried here may see them all."""
        return sorted({p for inst in (self.standing.get("instances") or {}).values()
                       for p in (inst.get("parts") or [])} - {""})


def used(run: dict | None) -> list[str]:
    """The tools a run used and a5s let it, or held for someone to decide, as an agent's suite
    counts them."""
    calls = (run or {}).get("calls") or []
    return list(dict.fromkeys(c["tool"] for c in calls if c["decision"] == "hold"
                              or (c["decision"] == "allow" and c["outcome"] == "ok")))


def _own(admin: str) -> None:
    """Make sure a database is the sandbox's own: new, or one a sandbox marked as its own. One
    whose ledger holds what a deployment did is someone else's, and the sandbox won't touch it."""
    with db.transaction(admin) as conn:
        found = conn.execute("select to_regclass('public.ledger') is not null as ledger, "
                             "to_regclass('public.a5s_sandbox') is not null as marked").fetchone()
        if found["ledger"] and not found["marked"]:
            used = conn.execute("select exists (select 1 from ledger) as used").fetchone()["used"]
            if used:
                raise Refused("that database holds a deployment's ledger: the sandbox needs a "
                              "database of its own")
        conn.execute("create table if not exists a5s_sandbox (made_at timestamptz not null "
                     "default now())")
        conn.execute("insert into a5s_sandbox default values")


@contextmanager
def opened(deployment: Config, admin: str, work: Path,
           transport: httpx.BaseTransport | None = None) -> Iterator[Sandbox]:
    """A sandbox for a deployment's scenario and agents, on its own database, whose
    administrator's address is `admin`, with its working copies in `work`: its calls to real
    models' providers go by `transport`, the internet's unless a test gives its own."""
    root = work / "root"
    shutil.rmtree(root, ignore_errors=True)
    scenario_dir = root / "scenarios" / deployment.scenario_dir.name
    shutil.copytree(deployment.scenario_dir, scenario_dir,
                    ignore=shutil.ignore_patterns("*.key", "settings.sig", "__pycache__", "*.pyc"))
    standing = yaml.safe_load((scenario_dir / "settings.yaml").read_text()) or {}
    if standing.get("data_class") != "synthetic":  # before it touches anything
        raise Refused("the sandbox runs only a scenario whose records are all made up "
                      "(data_class: synthetic): give it the scenario's fakes")
    _own(admin)
    shutil.copytree(deployment.agents_dir, root / "agents",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    models = yaml.safe_load(deployment.models_file.read_text()) or {}
    models.setdefault("models", {})[STAND_IN] = {
        "provider": "sandbox", "api": "openai", "base_url": STAND_IN_URL, "model": "stand-in-1",
        "reported_model": "stand-in-1", "region": "the sandbox itself", "data_classes": ["synthetic"]}
    (root / "config").mkdir(parents=True)
    (root / "config" / "models.yaml").write_text(yaml.safe_dump(models, sort_keys=False))
    keys = _fresh(scenario_dir)
    # Each of its parts connects as its database's administrator, by its own password: the
    # roles a5s gives each part belong to a whole database server, and a deployment's may share it
    cfg = Config(database_url=admin, gateway_url="http://127.0.0.1:1",
                 service_token=secrets.token_urlsafe(32), root=root, development=True,
                 seal_keys=(secrets.token_urlsafe(32),), scenario=deployment.scenario,
                 scenario_folder=scenario_dir, agents_folder=root / "agents", sandboxed=True)
    db.migrate(admin)
    with db.transaction(admin) as conn:
        build.scenario(cfg).setup(conn, db.ROLES["gateway"])
        last = conn.execute("select max(serial) as serial from settings_versions where scenario = %s",
                            (build.scenario(cfg).name,)).fetchone()["serial"]
    standing["serial"] = max(int(standing.get("serial") or 0), int(last or 0))  # on from its last
    recording = Recording()
    mounts: dict[str, httpx.BaseTransport] = {
        STAND_IN_URL.rsplit("/", 1)[0]: httpx.MockTransport(StandIn().handler)}
    if transport is not None:  # a test's own, for every provider, whatever the environment says
        mounts |= dict.fromkeys(("all://", "http://", "https://"), transport)
    http = httpx.Client(mounts=mounts, event_hooks={"response": [recording.heard]})
    gw = build.gateway(cfg, http=http)
    gw.identity = None  # it signs nobody in: its people are made up, and say who they are
    core, core_url = _serve(core_app(gw))
    cfg = replace(cfg, gateway_url=core_url)
    gw.cfg = cfg
    channels, channels_url = _serve(inbox.create_app(replace(gw, cfg=cfg)))
    sandbox = Sandbox(cfg, admin, gw, channels_url, keys, standing, recording)
    stop = threading.Event()

    def sweeping() -> None:
        while not stop.wait(SWEEP_EVERY):
            try:
                sandbox.forget()
            except Exception:  # the next sweep tries again
                log.exception("the sandbox's sweep failed")

    try:
        sandbox._settle()
        sandbox.forget()  # what it kept before it stopped, if it's been an hour
        threading.Thread(target=sweeping, daemon=True).start()
        yield sandbox
    finally:
        stop.set()
        core.should_exit = channels.should_exit = True


# Its API, for the studio of the deployment people work in, by the token they share

class Case(BaseModel):
    key: str  # the draft's, as the studio names it
    files: dict[str, str]  # its agent's folder, each file's text by its path in it
    number: int  # which of its test cases, by its place among them, from 0
    model: str = STAND_IN


class Describe(BaseModel):
    words: str  # what a new agent is for, in its author's words
    model: str = STAND_IN


class Try(BaseModel):
    key: str  # the draft's, as the studio names it
    files: dict[str, str]  # its agent's folder, each file's text by its path in it
    person: str  # who to be, of the sandbox's made-up people
    text: str  # what to say
    model: str = STAND_IN


def create_app(sandbox: Sandbox, token: str) -> FastAPI:
    app = FastAPI(title="a5s sandbox")

    def allowed(authorization: str | None) -> None:
        if not token or not secrets.compare_digest(authorization or "", f"Bearer {token}"):
            raise HTTPException(401, "the sandbox answers only the studio it's set up for")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/sandbox")
    def about(authorization: str | None = Header(default=None)) -> dict:
        """Whom a draft may be tried as, of the made-up people, and on which models."""
        allowed(authorization)
        return {"people": sandbox.people(), "models": sandbox.models()}

    @app.post("/sandbox/tries")
    def attempt(body: Try, authorization: str | None = Header(default=None)) -> dict:
        allowed(authorization)
        try:
            return sandbox.turn(body.key, body.files, body.person, body.text[:4000], body.model)
        except Refused as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/sandbox/descriptions")
    def described(body: Describe, authorization: str | None = Header(default=None)) -> dict:
        allowed(authorization)
        try:
            return sandbox.describe(body.words[:describing.WORDS], body.model)
        except Refused as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/sandbox/cases")
    def run_case(body: Case, authorization: str | None = Header(default=None)) -> dict:
        allowed(authorization)
        try:
            return sandbox.case(body.key, body.files, body.model, body.number)
        except Refused as e:
            raise HTTPException(400, str(e)) from None

    return app
