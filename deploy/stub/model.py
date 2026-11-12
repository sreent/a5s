"""A stand-in model provider, OpenAI-compatible, for trying a5s's containers offline.

It looks up what the person asked about, then says what it found, so a run
makes a model call, a tool call through the gateway, and another model call.
Asked to ask the watcher, and offered the tool to, it asks it, and says what
it answered. Asked for something "as a task:", it offers it as a task, starts it
when told "yes, start it", and works on each slice: it keeps its work, says it's
done, and tells its owner so.
"""

import json
import re
import time

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="stand-in model")


TASKED = "as a task:"  # how the soak's people ask for one


def calling(body: dict, name: str, args: dict) -> dict:
    return reply(body, {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call-{time.time_ns()}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)}}]})


def saying(body: dict, text: str) -> dict:
    return reply(body, {"role": "assistant", "content": text})


def reply(body: dict, message: dict) -> dict:
    return {"id": f"stub-{time.time_ns()}", "object": "chat.completion", "created": int(time.time()),
            "model": body["model"],
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,  # a few, as the measures
                      "total_tokens": 15}}  # count, but too few for any budget to stop


def keyed(found) -> list[str]:
    """The records' keys in what a tool answered, at any depth: a list of records, as the
    sample's tools answer, or an object that holds them, as other scenarios' tools do."""
    if isinstance(found, list):
        return [key for item in found for key in keyed(item)]
    if not isinstance(found, dict):
        return []
    own = [found["key"]] if isinstance(found.get("key"), str) else []
    return own + [key for value in found.values() for key in keyed(value)]


@app.post("/v1/chat/completions")
def complete(body: dict) -> dict:
    messages = body["messages"]
    last = messages[-1]
    offered = {t["function"]["name"] for t in body.get("tools") or []}
    if last["role"] == "tool" and last["content"].startswith("{"):  # a task's tools
        told = json.loads(last["content"])
        if "kept" in told and "finish_task" in offered:  # its slice kept its work
            return calling(body, "finish_task", {"status": "done", "result": "gone through"})
        if told.get("noted") == "done":
            return saying(body, "Your task is done: I went through it.")
        if "offered" in told and "task" in told:
            return saying(body, f"I can take that on as {told['task']}: shall I start it?")
        if told.get("started"):
            return saying(body, f"Started {told['task']}.")
    if last["role"] == "tool":
        if last["content"].startswith("{") and '"answer"' in last["content"]:  # another agent's
            told = json.loads(last["content"])
            return reply(body, {"role": "assistant",
                                "content": f"The {told['agent']} says: {told['answer']}"})
        found = json.loads(last["content"]) if last["content"][:1] in ("[", "{") else []
        keys = ", ".join(dict.fromkeys(keyed(found))) or "nothing"
        return reply(body, {"role": "assistant", "content": f"I looked it up and found {keys}."})
    said = str(last.get("content", "")).split("] ", 1)[-1]  # after when it was said
    if said.startswith("Work on ") and "checkpoint_task" in offered:  # a slice of a task
        return calling(body, "checkpoint_task", {"step": 1, "progress": 0.5,
                                                 "partial": ["half way"]})
    if TASKED in said.lower() and "offer_task" in offered:
        return calling(body, "offer_task", {"task": said.lower().split(TASKED, 1)[1].strip()
                                            or "go through my open questions"})
    if "yes, start it" in said.lower() and "confirm_task" in offered:
        return calling(body, "confirm_task", {})
    if "ask the watcher" in said.lower() and "ask_agent" in offered:
        return reply(body, {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call-{time.time_ns()}", "type": "function", "function": {
                "name": "ask_agent", "arguments": json.dumps({"agent": "watcher",
                                                              "question": said})}}]})
    if "asks you this" in said:  # another agent's question, apart from a5s's words around it
        said = said.split(": ", 1)[-1].split("\n\n")[0]
    words = re.findall(r"[a-z0-9-]+", said.lower())
    query = words[-1] if words else ""  # the last word, such as "invoice"
    return reply(body, {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call-{time.time_ns()}", "type": "function",
        "function": {"name": "search_records", "arguments": json.dumps({"query": query})}}]})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
