"""While a5s's database is away, as in a managed database's failover, the channels app, the
part of a5s people and their chats reach, refuses for a moment: it says so, and when to try
again, as the core does for its own callers, rather than failing with an error of its own and
a trace in its log for each request (core/inbox.py). The soak test takes Postgres away for
half a minute, and every message sent again once it's back is answered (deploy/soak.py)."""

from __future__ import annotations

import logging
from dataclasses import replace

import httpx

from a5s.core import inbox
from conftest import free_port, serve


def test_the_channels_app_asks_people_to_try_again_while_the_database_is_away(stack, caplog):
    away = f"postgresql://a5s_channels@127.0.0.1:{free_port()}/postgres?connect_timeout=1"
    gone = replace(stack.gateway, cfg=replace(stack.cfg, database_url=away))
    caplog.set_level(logging.WARNING, logger="a5s.core.inbox")
    with serve(inbox.create_app(gone), free_port()) as url:
        sent = httpx.post(f"{url}/channels/local/messages", timeout=30,
                          json={"person": "ana", "agent": "assistant", "text": "Hello"})
    assert sent.status_code == 503
    assert sent.headers["retry-after"] == str(inbox.AWAY_RETRY)
    assert sent.json() == {"detail": inbox.AWAY}  # the words the web chat shows its person
    said = [r for r in caplog.records if r.name == "a5s.core.inbox"]
    assert [r.levelno for r in said] == [logging.WARNING]  # one line, not a trace
    assert "the database can't be reached" in said[0].getMessage()
    back = httpx.post(f"{stack.channels_url}/channels/local/messages", timeout=30,
                      json={"person": "ana", "agent": "assistant", "text": "Hello"})
    assert back.status_code == 202  # and once it's back, the same message goes through
