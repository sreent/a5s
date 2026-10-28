"""Calls to model providers, in the OpenAI-compatible or Anthropic-compatible style.

Only the gateway calls providers, with the provider's key. Workers never see it.
"""

from __future__ import annotations

from typing import Any

import httpx

from a5s.config import ModelConfig


class ModelUnavailable(Exception):
    pass


def forward(model: ModelConfig, body: dict[str, Any], http: httpx.Client) -> tuple[int, dict]:
    key = model.api_key
    if not key:
        raise ModelUnavailable(f"{model.key_env} isn't set")
    payload = {**body, "model": model.model}
    if model.api == "openai":
        url = f"{model.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
    else:
        url = f"{model.base_url}/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        response = http.post(url, json=payload, headers=headers, timeout=180)
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
