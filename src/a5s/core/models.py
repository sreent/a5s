"""Calls to model providers, in the OpenAI-compatible or Anthropic-compatible style.

Only the gateway calls providers, with the provider's key. Workers never see it.
A model the organisation hosts itself, such as with vLLM, Ollama or llama.cpp on
its own network, speaks the same API, and may need no key at all.
"""

from __future__ import annotations

from typing import Any

import httpx

from a5s import config
from a5s.config import ModelConfig


class ModelUnavailable(Exception):
    pass


# What a5s forwards to a provider. Anything else, such as a provider's own web search,
# is never sent, so no provider reads outside content on a run's behalf.
_FIELDS = {
    "openai": {"model", "messages", "tools", "tool_choice", "temperature", "top_p", "max_tokens",
               "max_completion_tokens", "stop", "seed", "response_format", "parallel_tool_calls",
               "presence_penalty", "frequency_penalty", "stream"},
    "anthropic": {"model", "messages", "system", "tools", "tool_choice", "temperature", "top_p",
                  "top_k", "max_tokens", "stop_sequences", "stream", "thinking",
                  "cache_control"},  # where the provider may cache the prompt so far
}


def screen(api: str, body: dict[str, Any]) -> tuple[dict[str, Any], list[str], str | None]:
    """The request as a5s would forward it, the fields it leaves out, and why it refuses it."""
    kept = _for_minutes({k: v for k, v in body.items() if k in _FIELDS[api]})
    dropped = sorted(set(body) - set(kept))
    for tool in body.get("tools") or []:
        kind = tool.get("type") if isinstance(tool, dict) else None
        if (api == "openai" and kind != "function") or (api == "anthropic" and kind not in (None, "custom")):
            return kept, dropped, f"agents use only their own tools, not the provider's {kind}"
    return kept, dropped, None


def _for_minutes(block: Any) -> Any:
    """A request, or a block of it, with each place the provider may cache what came before
    marked for the shortest time it keeps it, a few minutes: the core, not the worker, says
    how long a provider holds what a run sent (docs/data-protection.md). Only where Anthropic's
    API reads it: the request, its system blocks, tools and messages, and their content."""
    if not isinstance(block, dict):
        return block
    out = dict(block)
    if out.get("cache_control") is not None:
        out["cache_control"] = {"type": "ephemeral"}
    for key in ("system", "tools", "messages", "content"):
        if isinstance(out.get(key), list):
            out[key] = [_for_minutes(b) for b in out[key]]
    return out


def forward(model: ModelConfig, body: dict[str, Any], http: httpx.Client) -> tuple[int, dict]:
    key = model.api_key
    if model.key_env and not key:
        raise ModelUnavailable(f"{model.key_env} isn't set")
    payload = {**body, "model": model.model}
    if model.api == "openai":
        url = f"{model.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    else:
        url = f"{model.base_url}/v1/messages"
        headers = {"anthropic-version": "2023-06-01", **({"x-api-key": key} if key else {})}
    try:
        response = http.post(url, json=payload, headers=headers,
                             timeout=config.PROVIDER_TIMEOUT.read())
    except httpx.HTTPError as exc:
        raise ModelUnavailable(f"{model.provider} couldn't be reached: {exc}") from exc
    try:
        data = response.json()
    except ValueError:
        data = {"error": {"message": response.text[:500]}}
    return response.status_code, data


def error_body(api: str, message: str, kind: str = "permission_denied") -> dict:
    """An error in the style the worker's client expects."""
    if api == "anthropic":
        return {"type": "error", "error": {"type": "permission_error", "message": message}}
    return {"error": {"message": message, "type": kind, "code": kind}}
