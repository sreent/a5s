"""a5s's own parts reach one another through a restart (src/a5s/reach.py): what goes to a
part that can't be reached for a moment, as while it restarts, waits for it, and is sent once
it's back. Only a connection that never opened is tried again, so nothing a part got is sent
twice. A run's calls to the core, for its tools and its model, wait for it so, and the
scheduler's to the core and its worker pools."""

import logging
import socket
import threading
import time

import httpx
import httpx2
import pytest
import uvicorn
from fastapi import FastAPI

from a5s import reach
from a5s.core.gateway import create_app
from a5s.worker import chat_model, run_agent
from conftest import free_port, serve


def counting() -> tuple[FastAPI, list[int]]:
    app, got = FastAPI(), []

    @app.post("/")
    def take() -> dict:
        got.append(1)
        return {"got": len(got)}

    return app, got


def later(app: FastAPI, port: int, after: float, done: threading.Event) -> threading.Event:
    """Serve `app` on `port` once `after` seconds have passed, until `done`."""
    up = threading.Event()

    def serving() -> None:
        time.sleep(after)
        with serve(app, port):
            up.set()
            done.wait(30)

    threading.Thread(target=serving, daemon=True).start()
    return up


def test_what_goes_to_a_part_that_cant_be_reached_for_a_moment_waits_for_it():
    app, got = counting()
    port, done = free_port(), threading.Event()
    up = later(app, port, 1, done)
    try:
        with reach.client(20) as c:
            answer = c.post(f"http://127.0.0.1:{port}/")
    finally:
        done.set()
    assert up.is_set() and answer.json() == {"got": 1} and got == [1]  # sent once


def test_a_connection_that_never_opened_logs_once_before_it_is_tried_again(monkeypatch, caplog):
    calls = 0

    def unreachable_once(self, request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("no listener", request=request)
        return httpx.Response(200, json={"got": 1}, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", unreachable_once)
    with caplog.at_level(logging.WARNING, logger="a5s.reach"), reach.client(20) as client:
        answer = client.post("http://a5s-part.test/")
    assert calls == 2 and answer.json() == {"got": 1}
    assert caplog.text.count("http://a5s-part.test can't be reached") == 1


def test_what_goes_to_a_part_that_stays_down_fails_once_its_time_is_up():
    began = time.monotonic()
    with reach.client(1) as c, pytest.raises(httpx.ConnectError):
        c.post(f"http://127.0.0.1:{free_port()}/")  # nothing listens there
    assert 0.5 < time.monotonic() - began < 10


def whole(conn: socket.socket) -> bytes:
    """All of a request: its head, and as much of a body as it says it has."""
    got = b""
    while b"\r\n\r\n" not in got and (chunk := conn.recv(65536)):
        got += chunk
    head, _, body = got.partition(b"\r\n\r\n")
    length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                   if line.lower().startswith(b"content-length:")), 0)
    while len(body) < length and (chunk := conn.recv(65536)):
        body += chunk
    return head + b"\r\n\r\n" + body


def test_what_a_part_got_is_never_sent_again():
    """A part that took the request and stopped before answering, as one killed part way
    would, may have done it: it fails at once, rather than be done twice, however the drop
    reaches the sender, as a close or a reset."""
    taken = []
    with socket.socket() as listening:
        listening.bind(("127.0.0.1", 0))
        listening.listen()

        def dropping() -> None:  # takes each request, and closes without answering it
            while True:
                try:
                    conn, _ = listening.accept()
                except OSError:
                    return
                with conn:
                    taken.append(whole(conn))

        threading.Thread(target=dropping, daemon=True).start()
        port = listening.getsockname()[1]
        with reach.client(20) as c, pytest.raises((httpx.RemoteProtocolError, httpx.ReadError)):
            c.post(f"http://127.0.0.1:{port}/", json={"change": 1})
        time.sleep(0.5)
    assert len(taken) == 1 and taken[0].endswith(b'{"change":1}')


class Restartable:
    """The core, served on a port of its own, where it can stop and start again."""

    def __init__(self, app: FastAPI):
        self.app, self.port, self.server = app, free_port(), None

    def start(self) -> None:
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port,
                                                    log_level="warning"))
        threading.Thread(target=self.server.run, daemon=True).start()
        while not self.server.started:
            time.sleep(0.02)

    def restart(self, after: float) -> None:
        """Stop taking anything new now, as a part asked to stop does, finishing what it has
        in hand; and start again `after` seconds later."""
        self.server.should_exit = True
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:  # until it no longer takes connections
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
            except OSError:
                break
            time.sleep(0.02)
        threading.Timer(after, self.start).start()

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True


def test_a_run_goes_on_once_its_core_is_back_from_a_restart(stack):
    """The core restarts part way through a run, as for an upgrade: just as its model has
    asked for a tool. The run's call to the tool waits for the core, and the run ends as it
    would have, with its answer."""
    core = Restartable(create_app(stack.gateway))
    core.start()
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("I found two questions about an invoice.")
    stack.model.on_request = lambda n: core.restart(after=1) if n == 1 else None
    worker = f"http://127.0.0.1:{core.port}"  # the run reaches the core here; the scheduler,
    try:  # at the stack's own
        said = stack.say("Which questions mention an invoice?", scheduler=stack.scheduler(
            worker=lambda _url, token, history: run_agent(worker, token, history)))
    finally:
        core.stop()
    assert said == "I found two questions about an invoice."
    assert len(stack.model.requests) == 2  # each of its model's calls, once
    closed = [e["outcome"] for e in stack.ledger() if e["kind"] == "run" and e["action"] == "close"]
    assert closed == ["done"]


def test_a_runs_model_waits_for_its_core_a_moment(stack):
    """A model call to a core that isn't back yet, such as one restarting, goes once it is."""
    _, token = stack.open_run()
    model = httpx.get(f"{stack.url}/run", headers={"Authorization": f"Bearer {token}"},
                      timeout=10).json()["model"]
    stack.model.reply("Hello, once the core was back.")
    port, done = free_port(), threading.Event()
    up = later(create_app(stack.gateway), port, 1, done)
    try:
        answer = chat_model(f"http://127.0.0.1:{port}", token, model).invoke("Hello")
    finally:
        done.set()
    assert up.is_set() and answer.content == "Hello, once the core was back."
    assert len(stack.model.requests) == 1


def test_each_providers_models_reach_the_core_as_the_rest_of_a_run_does():
    """The providers' SDKs take httpx2 in httpx's place: their clients wait for the core too."""
    for api in ("openai", "anthropic"):
        chat = chat_model("http://127.0.0.1:9", "token", {"alias": "a-model", "api": api})
        client = chat.root_client if api == "openai" else chat._client
        assert isinstance(client._client._transport, reach.reaching(httpx2)), api
