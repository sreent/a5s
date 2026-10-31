"""Round 5, reviewer b: one slow chat stalls answers in every chat.

The scheduler's loop asks the core for each sweep in turn, and waits for it, before it takes
the next message (Scheduler.listen). The core delivers each digest, escalation, batch and
reminder to Teams or Matrix inside that sweep's request, one after another, each waiting up
to its client's timeout (30 seconds for Teams, 15 for Matrix). So at the start of the working
day, when everyone's digest falls due at once, a chat that's slow or hanging stops a5s
answering anyone, in any chat, until it has tried every delivery.
"""

import threading
import time
import uuid
from dataclasses import replace

import httpx
import pytest

from a5s.core import inbox
from a5s.core.matrix import Matrix, MatrixConfig
from conftest import free_port, serve
from test_matrix import AS_TOKEN, DM, HS_TOKEN, Homeserver, invite, said


class Hanging(Homeserver):
    """A homeserver that hangs on the first message into Ana's room, until it's let go."""

    def __init__(self) -> None:
        super().__init__()
        self.hanging, self.go = threading.Event(), threading.Event()
        self.armed = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.armed and "/send/" in request.url.path and DM.split(":")[0][1:] in request.url.path:
            self.armed = False
            self.hanging.set()
            self.go.wait(12)  # as a homeserver that doesn't answer, until the client gives up
        return super().handler(request)


@pytest.fixture
def hanging(stack):
    fake = Hanging()
    cfg = MatrixConfig("https://matrix.test", "a5s.test", AS_TOKEN, HS_TOKEN)
    stack.gateway.matrix = Matrix(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/matrix/_matrix/app/v1"
        yield fake
    fake.go.set()


def test_a_hanging_chat_at_digest_time_doesnt_stop_answers_in_other_chats(stack, hanging):
    def deliver(*events):
        httpx.put(f"{hanging.url}/transactions/{uuid.uuid4().hex}", json={"events": list(events)},
                  headers={"Authorization": f"Bearer {HS_TOKEN}"}).raise_for_status()

    deliver(invite())
    stack.model.reply("Hello, Ana.")
    deliver(said("Hello"))
    stack.scheduler().answer_waiting()  # Ana talks to the assistant in Matrix

    stack.at("2026-11-02T09:30:00+00:00")  # Monday: the chases go in each one's digest
    stack.model.reply("Your Q-1001 is due on Wednesday.")
    stack.model.reply("Your Q-1002 is due on Friday.")
    hanging.armed = True  # Ana's digest is the first message into her room
    stop = threading.Event()
    loop = threading.Thread(target=stack.scheduler().listen,
                            kwargs={"stop": stop, "workers": 4, "sweep_every": 0.2}, daemon=True)
    loop.start()
    try:
        assert hanging.hanging.wait(20), "Ana's digest never went to Matrix"
        stack.model.reply("Hello, Ben.")
        asked = stack.send("Hello", person="ben")  # through the web chat, while Matrix hangs
        started = time.monotonic()
        answered = httpx.get(f"{stack.channels_url}/channels/local/messages/{asked}",
                             params={"person": "ben", "wait": 5}, timeout=30).json()["replies"]
        waited = time.monotonic() - started
    finally:
        hanging.go.set()
        stop.set()
        loop.join(30)
    assert answered == ["Hello, Ben."], (
        f"Ben's message in the web chat waited {waited:.1f}s, unanswered, while the core was "
        "delivering Ana's digest to a Matrix homeserver that didn't answer")
