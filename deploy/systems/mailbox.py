"""A made-up Exchange Online, for a scenario's shared mailboxes on a5s's containers: each mailbox
its mailboxes.yaml names, as Microsoft Graph answers the deployment's own app, holding the made-up
messages the mailbox's `sandbox:` folder keeps, and the drafts a5s leaves there. It sends nothing,
as a5s asks it to send nothing: a reply waits among the drafts for a person to send.

    A5S_MAIL_CLIENT_SECRET=... python deploy/systems/mailbox.py scenarios/procure-to-pay
                                                                       # on 127.0.0.1:9207

It signs in the app A5S_MAIL_TENANT, A5S_MAIL_CLIENT_ID and A5S_MAIL_CLIENT_SECRET name, as the
core's are set, and no other. It shares the gateway's network, as the core reaches Graph over
plain HTTP on its own loopback alone, where a stand-in is: a deployment's own mailboxes are the
tenant's, over HTTPS. Mail already in a mailbox when a5s first asks starts nothing, as in Exchange:
the scenario's made-up messages are there for its tools to search and read.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PORT = 9207
TENANT, CLIENT = "harbour", "a5s-mail"  # the made-up tenant, and the deployment's app, unless set


def inbox(folder: Path, mailbox: dict) -> list[dict[str, Any]]:
    """A mailbox's messages, as Graph gives them: the made-up ones its sandbox folder keeps."""
    where = str(mailbox.get("sandbox") or "")
    found: list[dict[str, Any]] = []
    for n, path in enumerate(sorted((folder / where).glob("*.yaml")) if where else [], 1):
        message = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sender = str(message.get("from") or "")
        found.append({"id": f"AAMkAGI2-{n:04d}/made-up==", "subject": str(message.get("subject") or ""),
                      "receivedDateTime": str(message.get("received") or ""),
                      "from": {"emailAddress": {"name": sender, "address": sender}},
                      "body": {"contentType": "text", "content": str(message.get("text") or "")},
                      "hasAttachments": False, "isDraft": False})
    return found


def make(folder: Path) -> FastAPI:
    boxes = (yaml.safe_load((folder / "mailboxes.yaml").read_text(encoding="utf-8")) or {}).get(
        "mailboxes") or {}
    held = {str(box["address"]): inbox(folder, box) for box in boxes.values()}
    drafts: list[dict[str, Any]] = []
    tenant = os.environ.get("A5S_MAIL_TENANT") or TENANT
    client = os.environ.get("A5S_MAIL_CLIENT_ID") or CLIENT
    secret, token = os.environ.get("A5S_MAIL_CLIENT_SECRET") or "", secrets.token_urlsafe(24)
    app = FastAPI(title="Exchange Online, made up")  # what it holds is in app.state

    def refused(request: Request, address: str) -> JSONResponse | None:
        if request.headers.get("authorization") != f"Bearer {token}":
            return JSONResponse({"error": {"code": "InvalidAuthenticationToken"}}, status_code=401)
        if address not in held:  # only the mailboxes the application access policy gives
            return JSONResponse({"error": {"code": "ErrorAccessDenied"}}, status_code=403)
        return None

    @app.post(f"/{tenant}/oauth2/v2.0/token")
    async def sign_in(request: Request) -> Any:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        if not secret or form.get("client_id") != client or form.get("client_secret") != secret:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        return {"access_token": token, "expires_in": 3600, "token_type": "Bearer"}

    @app.get("/v1.0/users/{address}/mailFolders/inbox/messages/delta")
    def delta(address: str, request: Request) -> Any:
        if problem := refused(request, address):
            return problem
        messages = held[address]
        seen = int(request.query_params.get("$deltatoken", "-1"))
        since = (request.query_params.get("$filter") or "").split()  # receivedDateTime ge <time>
        new = messages[seen:] if seen >= 0 else [
            m for m in messages if since and m["receivedDateTime"] >= since[-1]]
        here = f"{str(request.base_url).rstrip('/')}/v1.0/users/{address}/mailFolders/inbox/messages/delta"
        return {"value": [{"id": m["id"], "receivedDateTime": m["receivedDateTime"], "isDraft": False}
                          for m in new],
                "@odata.deltaLink": f"{here}?$deltatoken={len(messages)}"}

    @app.get("/v1.0/users/{address}/messages")
    def search(address: str, request: Request) -> Any:
        if problem := refused(request, address):
            return problem
        asked = request.query_params.get("$search", "").strip('"').lower()
        return {"value": [{k: m[k] for k in ("id", "subject", "from", "receivedDateTime")}
                          for m in held[address] if all(
                              w in f"{m['subject']} {m['body']['content']}".lower()
                              for w in asked.split())]}

    @app.get("/v1.0/users/{address}/messages/{message:path}")
    def read(address: str, message: str, request: Request) -> Any:
        if problem := refused(request, address):
            return problem
        found = next((m for m in held[address] if m["id"] == message), None)
        return found or JSONResponse({"error": {"code": "ErrorItemNotFound"}}, status_code=404)

    @app.post("/v1.0/users/{address}/messages/{message:path}")
    async def act(address: str, message: str, request: Request) -> Any:
        if problem := refused(request, address):
            return problem
        message, _, verb = message.rpartition("/")
        if verb != "createReply":  # a5s leaves replies among the drafts, and sends nothing
            return JSONResponse({"error": {"code": "ErrorAccessDenied"}}, status_code=403)
        drafts.append({"mailbox": address, "reply_to": message, **(await request.json())})
        return {"id": f"draft-{len(drafts)}", "isDraft": True}

    app.state.held, app.state.drafts = held, drafts
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario")), host="127.0.0.1",
                port=int(os.environ.get("A5S_SYSTEM_PORT") or PORT), log_level="warning")
