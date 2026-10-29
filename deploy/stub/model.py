"""A stand-in model provider, OpenAI-compatible, for trying a5s's containers offline.

It looks up what the person asked about, then says what it found, so a run
makes a model call, a tool call through the gateway, and another model call.
"""

import json
import re
import time

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="stand-in model")


def reply(body: dict, message: dict) -> dict:
    return {"id": f"stub-{time.time_ns()}", "object": "chat.completion", "created": int(time.time()),
            "model": body["model"],
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


@app.post("/v1/chat/completions")
def complete(body: dict) -> dict:
    messages = body["messages"]
    last = messages[-1]
    if last["role"] == "tool":
        found = json.loads(last["content"]) if last["content"].startswith("[") else []
        keys = ", ".join(r["key"] for r in found) or "nothing"
        return reply(body, {"role": "assistant", "content": f"I looked it up and found {keys}."})
    words = re.findall(r"[a-z0-9-]+", str(last.get("content", "")).lower())
    query = words[-1] if words else ""  # the last word, such as "invoice"
    return reply(body, {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call-{time.time_ns()}", "type": "function",
        "function": {"name": "search_records", "arguments": json.dumps({"query": query})}}]})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
