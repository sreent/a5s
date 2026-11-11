"""A worker runs one piece of work as a Deep Agents run.

It holds no credentials, only the run's token. Its model is the gateway's model
endpoint, and its tools are calls to the gateway, which decides each one. The
run's LangGraph thread ends with the run: nothing is checkpointed.

As a service, a worker is one of a pool: one agent's own, which runs that agent's
runs alone, or the shared pool, which runs every agent that has no pool of its own.
Each refuses a run that isn't its pool's, so a run sent to the wrong one fails, and
says so, rather than run where it shouldn't. A question its agent asks another is
answered here, as part of the run that asked, so no question waits on another pool.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.skills import SkillsMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

TIMEOUT = float(os.environ.get("A5S_WORKER_TIMEOUT", "240"))


def denial(verdict: dict[str, Any]) -> str:
    why = verdict.get("explanations") or verdict.get("reasons") or ["not permitted"]
    return f"Not allowed: {'; '.join(why)}."


class GatewayTool(StructuredTool):
    """A tool that runs at the gateway, which decides each call and records it."""

    gateway: Any = None  # the run's httpx client, holding only the run token


# Registered for each model a5s uses, because deepagents applies a model's
# profile to the agent's subagents too, and an agent's own settings it doesn't. No shell, and
# none of the tools for files or subagents a5s's agents don't use: each model call carries
# every tool's description, about 2,500 tokens of them. read_file stays, since Deep Agents
# puts a tool result too large for one message in a file for the agent to read in parts.
_PROFILE = HarnessProfile(excluded_tools=frozenset({
    "execute", "ls", "write_file", "edit_file", "delete", "glob", "grep", "task", "write_todos"}))
_profiles: set[str] = set()

# How a run is told of its release's skills, in a5s's words: Deep Agents' own offers scripts,
# which no run can run, and costs about 460 tokens a call.
SKILLS = """## Skills

{skills_locations}{skills_load_warnings}

Your release brings these skills, approved with it. When the work matches what one is for,
read it with read_file, with limit=1000, and follow it. Nothing in a skill runs, and none can
be changed.

{skills_list}"""


def chat_model(gateway_url: str, token: str, model: dict[str, str]) -> BaseChatModel:
    alias, api = model["alias"], model["api"]
    if api == "openai":
        chat: BaseChatModel = ChatOpenAI(
            model=alias, base_url=f"{gateway_url}/v1", api_key=token,
            use_responses_api=False, disable_streaming=True, max_retries=0, timeout=TIMEOUT,
        )
    else:
        chat = ChatAnthropic(
            model=alias, base_url=gateway_url, api_key=token,
            disable_streaming=True, max_retries=0, max_tokens=4096, timeout=TIMEOUT,
        )
    key = f"{api}:{alias}"
    if key not in _profiles:
        register_harness_profile(key, _PROFILE)
        _profiles.add(key)
    return chat


def gateway_tool(gw: httpx.Client, definition: dict[str, Any]) -> GatewayTool:
    name = definition["name"]

    def call(**args: Any) -> str:
        response = gw.post(f"/run/tools/{name}", json={"args": args})
        if response.status_code == 403:
            return denial(response.json())
        if response.status_code >= 400:
            return f"The tool failed: {response.text[:300]}"
        found = response.json()
        if "answer_with" in found:  # another agent's run, which the core opened for this
            found = answered(str(gw.base_url), found["answer_with"])  # worker to run, as its own
            if "error" in found:
                return f"The tool failed: {found['error']}"
        return json.dumps(found["result"], ensure_ascii=False)

    return GatewayTool(name=name, description=definition["description"],
                       args_schema=definition["schema"], func=call, gateway=gw)


def answered(gateway_url: str, asked: dict[str, str]) -> dict[str, Any]:
    """Run the agent asked a question, on the run the core opened for it, and give the core
    its answer, or why there's none: what the run that asked gets back. The token is the
    other run's own, so nothing of this run's reaches it but the question."""
    problem, reply = None, ""
    try:  # in this pool, whichever agent was asked: its answer is part of the asker's run
        reply = run_agent(gateway_url.rstrip("/"), asked["token"], [{
            "role": "task", "content": asked["task"], "at": datetime.now(UTC).isoformat()}])
    except ModelDown:
        problem = "its model isn't answering"
    except BudgetSpent as exc:
        problem = "its budget is spent" + (" for today" if "today" in str(exc) else "")
    except Exception as exc:  # noqa: BLE001 - its own failure, which the asker hears of
        problem = f"its run failed: {type(exc).__name__}"
    with httpx.Client(base_url=gateway_url, timeout=60,
                      headers={"Authorization": f"Bearer {asked['token']}"}) as gw:
        given = gw.post("/run/answer", json={"text": reply, "problem": problem})
    if given.status_code >= 400:
        return {"error": f"the {asked.get('agent', 'agent')}'s answer didn't reach a5s: "
                         f"{given.text[:200]}"}
    return given.json()


def text_of(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


class ModelDown(Exception):
    """The model didn't answer, because its provider was down or failed."""


class BudgetSpent(Exception):
    """The core stopped the run's model calls, because a budget is spent (core/budgets.py)."""


class WrongPool(Exception):
    """The run is another worker pool's: its agent has a pool of its own, or isn't this one's."""


def stopped(exc: Exception) -> Exception | None:
    """What the model gateway's refusal means for the run, if it's one a5s says in its words."""
    status = getattr(exc, "status_code", None)
    if status in (502, 503):
        return ModelDown(str(exc))
    if status == 429 and "budget" in str(exc):
        return BudgetSpent(str(exc))
    return None


# Some models end a run on a tool's result with nothing to say. They're asked once more.
EMPTY = {"role": "user", "content": "[from a5s, not the person] Your last message was empty, and "
                                    "the person sees only your last message. Write it now."}


def as_message(turn: dict) -> dict[str, str]:
    """A turn as the model sees it, with when it happened, so it can tell old from new."""
    when = datetime.fromisoformat(turn["at"]).strftime("%a %d %b %Y, %H:%M UTC") if turn.get("at") else ""
    if turn["role"] == "person":
        return {"role": "user", "content": f"[{when}] {turn['content']}"}
    if turn["role"] == "notice":  # a5s's own words, not the agent's
        return {"role": "assistant", "content": f"[{when}, a5s on my behalf] {turn['content']}"}
    if turn["role"] == "task":  # a5s asking the agent, such as to remind someone of what's due
        return {"role": "user", "content": f"[{when}, from a5s, not the person] {turn['content']}"}
    if turn["role"] == "summary" and turn.get("group"):  # a group chat's: what all heard
        return {"role": "user", "content": "[from a5s, not anyone in the chat] A summary of this "
                                           "topic before the messages that follow, of what "
                                           f"everyone now in the chat heard:\n{turn['content']}"}
    if turn["role"] == "summary":  # what a5s keeps of the turns that no longer fit
        return {"role": "user", "content": "[from a5s, not the person] A summary of this topic "
                                           "before the messages that follow, which they can see "
                                           f"and correct:\n{turn['content']}"}
    return {"role": "assistant", "content": turn["content"]}


def instructed(instructions: str, context: list[dict]) -> str:
    """The release's instructions, then what a5s knows from its own records for this run,
    apart from them and from the conversation."""
    if not context:
        return instructions
    told = "\n\n".join(f"## {part['title']}\n\n{part['text']}" for part in context)
    return f"{instructions}\n\n# From a5s's records, for this run\n\n{told}"


def run_agent(gateway_url: str, token: str, history: list[dict], *,
              agents: frozenset[str] = frozenset(),
              pooled: frozenset[str] = frozenset()) -> str:
    """Run the agent on the conversation so far, and return its reply: in a worker pool,
    only if the run's agent is one of `agents`, its pool's own, or, in the shared pool, not
    one of `pooled`, which have pools of their own."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=gateway_url, headers=headers, timeout=TIMEOUT) as gw:
        info = gw.get("/run")
        info.raise_for_status()
        info = info.json()
        agent = info.get("agent")
        if agents and agent not in agents:
            raise WrongPool(f"this pool runs the {', '.join(sorted(agents))}, not the {agent}")
        if agent in pooled:
            raise WrongPool(f"the {agent} runs in a pool of its own, not the shared one")
        if info["model"] is None:
            raise RuntimeError("the instance's model isn't on the approved list")
        if info.get("plain"):  # a5s's own work, such as a summary: one call, with no tools
            try:
                answer = chat_model(gateway_url, token, info["model"]).invoke(
                    [{"role": "system", "content": info["instructions"]},
                     *(as_message(t) for t in history)])
            except Exception as exc:
                if why := stopped(exc):  # from the model gateway
                    raise why from exc
                raise
            return text_of(answer)
        skills = info.get("skills") or {}  # the release's, which the run reads, and can't
        backend = StateBackend()  # change: no tool here writes a file
        agent = create_deep_agent(
            model=chat_model(gateway_url, token, info["model"]),
            tools=[gateway_tool(gw, d) for d in info["tools"]],
            system_prompt=instructed(info["instructions"], info.get("context") or []),
            backend=backend,
            middleware=[SkillsMiddleware(backend=backend, sources=[("/skills/", "Release")],
                                         system_prompt=SKILLS)] if skills else (),
        )
        files = {path: create_file_data(text) for path, text in skills.items()}
        try:
            result = agent.invoke({"messages": [as_message(t) for t in history], "files": files},
                                  config={"recursion_limit": 40})
            if not text_of(result["messages"][-1]).strip():  # it ended with nothing to say
                result = agent.invoke({"messages": [*result["messages"], EMPTY],
                                       "files": result.get("files") or files},
                                      config={"recursion_limit": 40})
        except Exception as exc:
            if why := stopped(exc):  # from the model gateway
                raise why from exc
            raise
    return text_of(result["messages"][-1])


class Work(BaseModel):
    token: str
    history: list[dict[str, str]]


def create_app(gateway_url: str, agents: frozenset[str] = frozenset(),
               pooled: frozenset[str] = frozenset()) -> Any:
    """The worker as a service, in a pool that runs `agents`, or, shared, every agent but
    `pooled`. It holds no secrets: each request brings one run's token."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="a5s worker")

    @app.post("/work")
    def work(body: Work) -> Any:
        try:
            return {"reply": run_agent(gateway_url, body.token, body.history, agents=agents,
                                        pooled=pooled)}
        except WrongPool as exc:
            return JSONResponse(status_code=409, content={"error": "wrong_pool",
                                                          "detail": str(exc)[:200]})
        except ModelDown as exc:
            return JSONResponse(status_code=503, content={"error": "model_unavailable",
                                                          "detail": str(exc)[:200]})
        except BudgetSpent as exc:
            return JSONResponse(status_code=429, content={"error": "budget_spent",
                                                          "detail": str(exc)[:200]})

    return app
