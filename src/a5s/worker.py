"""A worker runs one piece of work as a Deep Agents run.

It holds no credentials, only the run's token. Its model is the gateway's model
endpoint, and its tools are calls to the gateway, which decides each one. The
run's LangGraph thread ends with the run: nothing is checkpointed.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


def denial(verdict: dict[str, Any]) -> str:
    why = verdict.get("explanations") or verdict.get("reasons") or ["not permitted"]
    return f"Not allowed: {'; '.join(why)}."


class GatewayTool(StructuredTool):
    """A tool that runs at the gateway, which decides each call and records it."""

    gateway: Any = None  # the run's httpx client, holding only the run token


# Registered for each model a5s uses, because deepagents applies a model's
# profile to the agent's subagents too, and an agent's own settings it doesn't.
_PROFILE = HarnessProfile(excluded_tools=frozenset({"execute"}))  # no shell
_profiles: set[str] = set()


def chat_model(gateway_url: str, token: str, model: dict[str, str]) -> BaseChatModel:
    alias, api = model["alias"], model["api"]
    if api == "openai":
        chat: BaseChatModel = ChatOpenAI(
            model=alias, base_url=f"{gateway_url}/v1", api_key=token,
            use_responses_api=False, disable_streaming=True, max_retries=0, timeout=180,
        )
    else:
        chat = ChatAnthropic(
            model=alias, base_url=gateway_url, api_key=token,
            disable_streaming=True, max_retries=0, max_tokens=4096,
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
        return json.dumps(response.json()["result"], ensure_ascii=False)

    return GatewayTool(name=name, description=definition["description"],
                       args_schema=definition["schema"], func=call, gateway=gw)


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


def run_agent(gateway_url: str, token: str, history: list[dict]) -> str:
    """Run the agent on the conversation so far, and return its reply."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=gateway_url, headers=headers, timeout=180) as gw:
        info = gw.get("/run")
        info.raise_for_status()
        info = info.json()
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
        agent = create_deep_agent(
            model=chat_model(gateway_url, token, info["model"]),
            tools=[gateway_tool(gw, d) for d in info["tools"]],
            system_prompt=instructed(info["instructions"], info.get("context") or []),
        )
        try:
            result = agent.invoke({"messages": [as_message(t) for t in history]},
                                  config={"recursion_limit": 40})
            if not text_of(result["messages"][-1]).strip():  # it ended with nothing to say
                result = agent.invoke({"messages": [*result["messages"], EMPTY]},
                                      config={"recursion_limit": 40})
        except Exception as exc:
            if why := stopped(exc):  # from the model gateway
                raise why from exc
            raise
    return text_of(result["messages"][-1])


class Work(BaseModel):
    token: str
    history: list[dict[str, str]]


def create_app(gateway_url: str) -> Any:
    """The worker as a service. It holds no secrets: each request brings one run's token."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="a5s worker")

    @app.post("/work")
    def work(body: Work) -> Any:
        try:
            return {"reply": run_agent(gateway_url, body.token, body.history)}
        except ModelDown as exc:
            return JSONResponse(status_code=503, content={"error": "model_unavailable",
                                                          "detail": str(exc)[:200]})
        except BudgetSpent as exc:
            return JSONResponse(status_code=429, content={"error": "budget_spent",
                                                          "detail": str(exc)[:200]})

    return app
