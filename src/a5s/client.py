"""A client for the core's API, for code and CI: the calls the command line makes, so a team's
own jobs can read how a5s is doing, its agents and their runs, as `a5s` does (docs/studio.md).

It reaches the core with the service token, as the team that runs a5s does, so it belongs
where that token already is, such as the team's own jobs. People use the studio's pages,
signed in as themselves, which show them only what they may watch.

    from a5s.client import Client

    with Client.from_env() as core:
        for agent in core.agents():
            for inst in agent["instances"]:
                figures = core.measures(days=7, instance=inst["id"])
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Self
from urllib.parse import quote

import httpx

from a5s.config import DEFAULT_GATEWAY_URL

RUNS = 50  # runs to a page, as the core gives them


class Refused(Exception):
    """The core turned a call down: its status, what it said why, and the body as it came. A
    status of 0 says the core couldn't be reached at all."""

    def __init__(self, status: int, detail: Any, text: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail, self.text = status, detail, text


def _part(name: str) -> str:
    return quote(name, safe="")


class Client:
    """The core's API, by its service token."""

    def __init__(self, url: str, token: str, *, timeout: float = 30,
                 transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"},
                                  timeout=timeout, transport=transport)

    @classmethod
    def from_env(cls, **kwargs: Any) -> Client:
        """The core at A5S_GATEWAY_URL, by the token in A5S_SERVICE_TOKEN, as `a5s` finds it."""
        return cls(os.environ.get("A5S_GATEWAY_URL", DEFAULT_GATEWAY_URL),
                   os.environ.get("A5S_SERVICE_TOKEN", ""), **kwargs)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def call(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        """Any of the core's calls, by its path: what it answered, or Refused."""
        given = {k: v.isoformat() if isinstance(v, datetime) else v
                 for k, v in params.items() if v is not None}
        try:
            response = self._http.request(method, path, json=body, params=given or None)
        except httpx.HTTPError as exc:  # down, unreachable or too slow: refused, with no status
            raise Refused(0, f"the core at {self._http.base_url} can't be reached now "
                             f"({type(exc).__name__})", "") from exc
        if response.status_code >= 400:
            try:
                found = response.json()
                detail = found.get("detail", found) if isinstance(found, dict) else found
            except ValueError:
                detail = response.text
            raise Refused(response.status_code, detail, response.text)
        try:
            return response.json()
        except ValueError as exc:  # a page, such as a proxy's sign-in or maintenance page
            raise Refused(response.status_code, "the core didn't answer with its JSON, so "
                          "something stands in front of it", response.text[:500]) from exc

    def get(self, path: str, **params: Any) -> Any:
        return self.call("GET", path, **params)

    def post(self, path: str, body: Any = None) -> Any:
        return self.call("POST", path, {} if body is None else body)

    # How a5s is doing

    def status(self) -> dict:
        """The last day's status, as `a5s status` reads it."""
        return self.get("/status")

    def measures(self, days: int = 30, *, agent: str | None = None,
                 instance: str | None = None) -> dict:
        """The measures over the last `days` days: of the whole deployment, or of one agent's
        instances, or of one instance, as `a5s measures` reads them."""
        if agent and instance:
            raise ValueError("name an agent or an instance, not both")
        path = (f"/studio/agents/{_part(agent)}/measures" if agent
                else f"/studio/instances/{_part(instance)}/measures" if instance
                else "/measures")
        return self.get(path, days=days)

    # The studio

    def agents(self) -> list[dict]:
        """Each agent of the release, and where it runs."""
        return self.get("/studio/agents")["agents"]

    def agent(self, agent: str) -> dict:
        """One agent as its release defines it, its instructions included, and where it runs."""
        return self.get(f"/studio/agents/{_part(agent)}")

    def runs(self, instance: str, *, before: str | None = None, limit: int = RUNS) -> dict:
        """A page of an instance's runs, newest first: after where the page before ended, its
        `before`, if given."""
        return self.get(f"/studio/instances/{_part(instance)}/runs", before=before, limit=limit)

    def each_run(self, instance: str, *, page: int = RUNS) -> Iterator[dict]:
        """Every run of an instance, newest first, a page at a time, until the core says
        there are no more."""
        before = None
        while True:
            found = self.runs(instance, before=before, limit=page)
            yield from found["runs"]
            before = found["before"]
            if not before:
                return

    def run(self, run: str) -> dict:
        """What one run did, with its entries in the ledger."""
        return self.get(f"/studio/runs/{_part(run)}")

    # The audit trail, for an auditor or assurance (docs/administration.md)

    def audit_entries(self, by: str, *, since: datetime | None = None,
                      until: datetime | None = None, after: int = 0,
                      **filters: str | None) -> dict:
        """A page of a period's ledger entries, as `by`, an auditor or assurance, asks: of a
        kind, action, decision, instance or person, after an entry, for the next page."""
        return self.get("/audit/entries", by=by, since=since, until=until, after=after,
                        **filters)

    def audit_export(self, by: str, *, since: datetime | None = None,
                     until: datetime | None = None) -> Iterator[dict]:
        """Each of a period's entries exactly as the ledger holds them, a page at a time, as
        `by` exports them."""
        after = 0
        while True:
            page = self.get("/audit/export", by=by, since=since, until=until, after=after)
            yield from page["entries"]
            if not page["next"]:
                return
            after = page["next"]

    def audit_report(self, by: str, *, since: datetime | None = None,
                     until: datetime | None = None) -> dict:
        """Who holds each role, and each administrative act of a period, as `by` asks."""
        return self.get("/audit/report", by=by, since=since, until=until)
