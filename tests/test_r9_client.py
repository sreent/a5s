"""Round 9 of the critique: the client (a5s/client.py) and the command line on it, when the core
is down, slow, or answers with something other than its JSON: what it answered, or Refused, and
from the command line a sentence and an exit status (docs/critique.md, round 9)."""

from __future__ import annotations

import socket

import httpx
import pytest

from a5s import cli
from a5s.client import Client, Refused


def test_an_answer_that_isnt_json_is_refused_not_a_parse_error():
    page = httpx.MockTransport(lambda request: httpx.Response(
        200, text="<html>Sign in to continue</html>", headers={"content-type": "text/html"}))
    with Client("http://core.test", "t", transport=page) as core, pytest.raises(Refused) as why:
        core.agents()
    assert why.value.status == 200 and "Sign in" in why.value.text


def test_a_core_that_cant_be_reached_is_refused_with_no_status():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with Client("http://core.test", "t", transport=httpx.MockTransport(down)) as core, \
            pytest.raises(Refused) as why:
        core.status()
    assert why.value.status == 0 and "can't be reached" in str(why.value.detail)


def test_the_command_line_says_the_core_cant_be_reached_rather_than_a_traceback(monkeypatch):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()  # nothing listens there now
    monkeypatch.setenv("A5S_GATEWAY_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("A5S_SERVICE_TOKEN", "t")
    with pytest.raises(SystemExit) as stopped:
        cli.main(["agents"])
    assert "can't be reached" in str(stopped.value.code)
