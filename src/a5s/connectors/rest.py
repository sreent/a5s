"""A fixed-origin, read-only JSON REST transport for scenario connectors."""

from __future__ import annotations

import ipaddress
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from a5s import reach

MAX_BYTES = 1_000_000
NEXT = re.compile(r"<([^>]+)>\s*;\s*rel=[\"']?next[\"']?", re.IGNORECASE)


class ConnectorError(RuntimeError):
    """A connector's safe, record-free account of a failed call, with its HTTP status if any."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Page:
    items: list[Any]
    truncated: bool
    total: int | None = None


class RestClient:
    """GET only, on one origin, with bounded responses and no cross-host redirects."""

    def __init__(self, base_url: str, *, token_env: str | None = None,
                 http: httpx.Client | None = None, timeout: float = 20, pages: int = 3):
        parsed = urlsplit(base_url)
        host = parsed.hostname or ""
        if (parsed.scheme not in ("http", "https") or not host or parsed.username
                or parsed.fragment or parsed.query):
            raise ValueError("a connector needs an HTTP(S) origin, with no userinfo or fragment")
        if parsed.scheme == "http" and not self._local(host):
            raise ValueError("a remote connector needs HTTPS")
        self.base_url = base_url.rstrip("/")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.base_path = parsed.path.rstrip("/")
        self.token_env = token_env
        self.http = http or reach.client(timeout=timeout)
        self.owns_http = http is None
        self.timeout = timeout
        self.pages = pages

    @staticmethod
    def _local(host: str) -> bool:
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def close(self) -> None:
        if self.owns_http:
            self.http.close()

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {"Accept": accept}
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token:
                raise ConnectorError(f"the connector's {self.token_env} credential isn't set")
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _url(self, path: str, query: dict[str, Any] | None) -> str:
        if path.startswith(("http://", "https://")):
            if not self._same_origin(path):
                raise ConnectorError("a connector's next page must stay on its configured origin")
            return path
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("a connector path is relative to its configured origin")
        return self.base_url + path + (f"?{urlencode(query or {})}" if query else "")

    def _same_origin(self, url: str) -> bool:
        found = urlsplit(url)
        return (found.scheme + "://" + found.netloc == self.origin
                and found.path.startswith(self.base_path + "/")
                and not found.username and not found.fragment)

    def _request(self, path: str, query: dict[str, Any] | None, accept: str,
                 max_bytes: int) -> tuple[Any, httpx.Headers]:
        url = self._url(path, query)

        def get() -> httpx.Response:
            return self.http.get(url, headers=self._headers(accept), follow_redirects=False)

        try:
            answer = get()
            if answer.status_code in (429, 502, 503, 504):  # busy, or restarting: once more
                delay = answer.headers.get("Retry-After", "")
                time.sleep(min(float(delay) if delay.isdigit() else 0.25, 1.0))
                answer = get()
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"the records system couldn't be reached: {type(exc).__name__}") from None
        if answer.status_code >= 400:
            raise ConnectorError(f"the records system answered HTTP {answer.status_code}",
                                 status=answer.status_code)
        body = answer.content
        if len(body) > max_bytes:
            raise ConnectorError(f"the records system answered more than {max_bytes:,} bytes")
        return body, answer.headers

    @staticmethod
    def _json(body: bytes) -> Any:
        import json
        try:
            return json.loads(body)
        except (UnicodeDecodeError, ValueError):
            raise ConnectorError("the records system answered invalid JSON") from None

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        body, _ = self._request(path, query, "application/json", MAX_BYTES)
        return self._json(body)

    def list(self, path: str, query: dict[str, Any] | None = None,
             limit: int = 100) -> Page:
        found: list[Any] = []
        total = None
        next_url = None
        for _ in range(self.pages):
            body, headers = self._request(next_url or path, None if next_url else query,
                                          "application/json", MAX_BYTES)
            data = self._json(body)
            items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
            if not isinstance(items, list):
                raise ConnectorError("the records system's list isn't a list")
            if isinstance(data, dict) and isinstance(data.get("total_count"), int):
                total = data["total_count"]
            found.extend(items)
            if len(found) >= limit:
                return Page(found[:limit], True, total)
            links = [m.group(1) for m in NEXT.finditer(headers.get("Link", ""))]
            if not links:
                return Page(found, False, total)
            next_url = links[0]
            if not self._same_origin(next_url):
                raise ConnectorError("the records system tried to paginate to another origin")
        return Page(found[:limit], True, total)

    def text(self, path: str, query: dict[str, Any] | None = None,
             accept: str = "text/plain", max_bytes: int = 200_000) -> str:
        body, _ = self._request(path, query, accept, max_bytes)
        try:
            return body.decode()
        except UnicodeDecodeError:
            raise ConnectorError("the repository's content isn't text") from None
