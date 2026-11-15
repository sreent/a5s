"""A made-up identity provider's self-service API, behind its MCP server, for the service desk
scenario (docs/connectors.md#mcp-servers): an account for each person in the desk's synthetic
data, ACC- and their id, with how many authenticators it has registered; its own password reset,
which the account's holder finishes at the provider, verifying themselves there, so whoever starts
it never sees a secret; and removing an account's authenticators, so its holder registers new ones
when they next sign in.

Like the desk's ITSM, it reads the data afresh for each call, keeps what's done through it in its
memory until it stops, makes each change once for a5s's key, and runs beside the gateway, sharing
its network:

    python deploy/systems/idp.py scenarios/service-desk/data.yaml      # on 127.0.0.1:9202
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))  # beside the other made-up systems
from standin import KEY, Tools, once, serving

PORT = 9202
LINK = "https://idp.desk.test/accounts/"


@dataclass
class Done:
    """What's been done through the provider since it started: the password resets it started,
    and the authenticators it removed, by account, and what each request a5s keyed made."""

    resets: dict[str, list[dict]] = field(default_factory=dict)
    removed: dict[str, list[dict]] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)

    def reset(self) -> None:
        self.resets.clear()
        self.removed.clear()
        self.made.clear()


def accounts(data: dict) -> dict[str, dict]:
    """Each person's account, by its key, with what data.yaml's accounts say of it."""
    said = {a["key"]: a for a in data.get("accounts") or []}
    return {f"ACC-{p['id']}": {"key": f"ACC-{p['id']}", "holder": p["id"],
                               "state": said.get(f"ACC-{p['id']}", {}).get("state", "active"),
                               "authenticators": said.get(f"ACC-{p['id']}", {}).get("authenticators", 1)}
            for p in data.get("people") or []}


def make(data: Path) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`: what's done through it is in
    `app.state.done`."""
    done = Done()

    def account(args: dict) -> dict | None:
        found = accounts(yaml.safe_load(data.read_text()) or {}).get(str(args.get("key")))
        if found is None:
            return None
        removed = sum(r["removed"] for r in done.removed.get(found["key"], []))
        return {**found, "authenticators": max(found["authenticators"] - removed, 0),
                "link": LINK + found["key"]}

    def get(args: dict, _: dict) -> dict | None:
        return account(args)

    def start_reset(args: dict, meta: dict) -> dict | None:
        """The provider's own reset, for the account's holder to finish there: it tells them, and
        they verify themselves with it before they choose a password. Nothing secret comes back."""
        found = account(args)
        if found is None:
            return None

        def start() -> dict:
            started = {"key": found["key"], "flow": "started: its holder finishes it with the "
                       "identity provider, verifying themselves there", "link": found["link"],
                       "at": datetime.now(UTC).isoformat(timespec="seconds")}
            done.resets.setdefault(found["key"], []).append({**started, "a5s_key": meta.get("a5s/key")})
            return started

        return once(done.made, meta, f"reset {found['key']}", start)

    def remove(args: dict, meta: dict) -> dict | None:
        found = account(args)
        if found is None:
            return None

        def take() -> dict:
            gone = {"key": found["key"], "removed": found["authenticators"], "link": found["link"]}
            done.removed.setdefault(found["key"], []).append({**gone, "a5s_key": meta.get("a5s/key")})
            return gone

        return once(done.made, meta, f"remove {found['key']}", take)

    changes = {"readOnlyHint": False, "idempotentHint": True, "openWorldHint": False}
    tools: Tools = {
        "get_account": ("Get an account by its key: its holder, its state, and how many authenticators it has.",
                        KEY, {"readOnlyHint": True}, get),
        "start_password_reset": ("Start the provider's own password reset for an account, for its holder to finish.",
                                 KEY, {**changes, "destructiveHint": False}, start_reset),
        "reset_authenticators": ("Remove an account's authenticators, so its holder registers new ones.",
                                 KEY, {**changes, "destructiveHint": True}, remove),
    }
    app = serving("desk-idp", tools, "No such account.")
    app.state.done = done
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=PORT, log_level="warning")
