"""How a5s's own parts reach one another over HTTP: the scheduler its worker pools and the
core, and a worker the core, for its run's tools and model calls.

A connection that won't open, as while the part at the other end restarts for an upgrade
or after a crash, is tried again for up to a minute before it fails: a part takes about two
seconds to start. Only a connection that never opened is tried again, so nothing is sent
twice: a request the part got and didn't answer fails at once, as it always did.
"""

from __future__ import annotations

import logging
import time
from functools import cache
from types import ModuleType
from typing import Any

import httpx

log = logging.getLogger(__name__)
WITHIN = 60.0  # seconds a connection that won't open is tried again


@cache
def reaching(http: ModuleType = httpx) -> type:
    """The transport that waits for a part that can't be reached: of httpx, or of `http`,
    such as httpx2, which the model providers' SDKs take in its place."""

    class Reaching(http.HTTPTransport):  # type: ignore[name-defined, misc]
        def __init__(self, within: float = WITHIN, **kwargs: Any):
            super().__init__(**kwargs)
            self.within = within

        def handle_request(self, request: Any) -> Any:
            until, wait = time.monotonic() + self.within, 0.25
            while True:
                try:
                    return super().handle_request(request)
                except (http.ConnectError, http.ConnectTimeout):  # it never got the request
                    if time.monotonic() + wait > until:
                        raise
                    if wait == 0.25:
                        log.warning("%s can't be reached, so what's sent there waits for it, "
                                    "for up to %.0f seconds", where(request.url), self.within)
                    time.sleep(wait)
                    wait = min(wait * 2, 5)

    return Reaching


def where(url: Any) -> str:
    return f"{url.scheme}://{url.host}" + (f":{url.port}" if url.port else "")


def client(within: float = WITHIN, *, http: ModuleType = httpx, **kwargs: Any) -> Any:
    """A client for another of a5s's parts, which waits for it as `reaching` says."""
    return http.Client(transport=reaching(http)(within), **kwargs)
