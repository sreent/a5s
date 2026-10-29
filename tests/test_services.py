"""a5s's parts as separate services: the channel and scheduler, and a worker with no secrets."""

import httpx

from a5s import worker
from a5s.services import channels
from a5s.services.scheduler import Scheduler, remote_worker
from conftest import SERVICE_TOKEN, free_port, serve


def test_a_message_through_the_channel_the_scheduler_and_a_worker_service(stack):
    stack.model.reply("Hello from a worker that holds no secrets.")
    seen = []

    def record(request: httpx.Request) -> None:
        seen.append(request.headers.get("authorization", ""))

    with serve(worker.create_app(stack.url), free_port()) as worker_url:
        scheduler = Scheduler(stack.cfg, stack.gateway.scenario, worker=remote_worker(worker_url))
        channel = channels.create_app(scheduler, stack.cfg.database_url)
        with serve(channel, free_port()) as channel_url, httpx.Client(
                event_hooks={"request": [record]}, timeout=60) as person:
            reply = person.post(f"{channel_url}/channels/local/messages",
                                json={"person": "ana", "agent": "assistant", "text": "Hi"})
            outbox = person.get(f"{channel_url}/channels/local/outbox/ana").json()

    assert reply.json()["reply"] == "Hello from a worker that holds no secrets."
    assert [m["text"] for m in outbox] == ["Hello from a worker that holds no secrets."]
    assert all(SERVICE_TOKEN not in h for h in seen)  # people never handle a5s's secrets
    assert stack.verify().ok
