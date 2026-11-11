"""Round 9, reviewer B: the client (a5s/client.py) and the command line on it, when the core
is down, slow, or answers with something other than its JSON. Client.call says it gives
'what it answered, or Refused'; the command line exits with the reason a call was refused."""

from __future__ import annotations

import socket

import httpx
import pytest

from a5s import cli
from a5s.client import Client, Refused


def test_an_answer_that_isnt_json_is_refused_not_a_parse_error():
    """A proxy or ingress in front of the core that answers 200 with a page, as a sign-in
    page or a maintenance page does, comes out of the client as a JSONDecodeError."""
    page = httpx.MockTransport(lambda request: httpx.Response(
        200, text="<html>Sign in to continue</html>", headers={"content-type": "text/html"}))
    with Client("http://core.test", "t", transport=page) as core, pytest.raises(Refused):
        core.agents()


def test_the_command_line_says_the_core_cant_be_reached_rather_than_a_traceback(monkeypatch):
    """`a5s status`, `a5s agents` or `a5s runs` with the gateway down: _core catches only
    Refused, so on-call gets httpx's ConnectError and a traceback, not a sentence."""
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()  # nothing listens there now
    monkeypatch.setenv("A5S_GATEWAY_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("A5S_SERVICE_TOKEN", "t")
    with pytest.raises(SystemExit):  # what a refusal gives: a sentence, and an exit status
        cli.main(["agents"])


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
