"""A worker runs one piece of work as a Deep Agents run.

It holds no credentials, only the run's token. Its model is the gateway's model
endpoint, and its tools are calls to the gateway, which decides each one. The
run's LangGraph thread ends with the run: nothing is checkpointed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

_NO_SHELL = frozenset({"execute"})
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
    if key not in _profiles:  # a5s workers have no shell to offer the model
        register_harness_profile(key, HarnessProfile(excluded_tools=_NO_SHELL))
        _profiles.add(key)
    return chat


def gateway_tool(gw: httpx.Client, definition: dict[str, Any]) -> StructuredTool:
    name = definition["name"]

    def call(**args: Any) -> str:
        response = gw.post(f"/run/tools/{name}", json={"args": args})
        if response.status_code == 403:
            body = response.json()
            why = ", ".join(body.get("reasons") or body.get("errors") or ["not permitted"])
            return f"Denied by policy ({why})."
        if response.status_code >= 400:
            return f"The tool failed: {response.text[:300]}"
        return json.dumps(response.json()["result"], ensure_ascii=False)

    return StructuredTool(
        name=name, description=definition["description"],
        args_schema=definition["schema"], func=call,
    )


def text_of(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


def run_agent(gateway_url: str, token: str, history: list[dict]) -> str:
    """Run the agent on the conversation so far, and return its reply."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=gateway_url, headers=headers, timeout=180) as gw:
        info = gw.get("/run")
        info.raise_for_status()
        info = info.json()
        if info["model"] is None:
            raise RuntimeError("the instance's model isn't on the approved list")
        agent = create_deep_agent(
            model=chat_model(gateway_url, token, info["model"]),
            tools=[gateway_tool(gw, d) for d in info["tools"]],
            system_prompt=info["instructions"],
        )
        messages = [
            {"role": "user" if t["role"] == "person" else "assistant", "content": t["content"]}
            for t in history
        ]
        result = agent.invoke({"messages": messages}, config={"recursion_limit": 40})
    return text_of(result["messages"][-1])
