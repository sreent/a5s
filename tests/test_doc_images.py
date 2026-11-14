"""The docs' pictures of the studio (docs/user-journey.md), made from a5s running: two weeks and
more of an instance's runs, a few of them ended otherwise than done, and the studio's pages as
the person who runs it sees them. Only when A5S_DOC_IMAGES names the folder to write them to:

    A5S_DOC_IMAGES=docs/images uv run pytest tests/test_doc_images.py
"""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime

import pytest

from a5s import db
from conftest import QUIET

FOLDER = os.environ.get("A5S_DOC_IMAGES")
pytestmark = pytest.mark.skipif(not FOLDER, reason="makes the docs' pictures only when asked")

# How many runs on each day, back from the core's: a working pattern, quieter at weekends
DAYS = [3, 4, 0, 0, 5, 3, 4, 2, 5, 1, 0, 4, 6, 3, 2, 4]
OTHERWISE = ["failed", "budget spent", "done, leaving some out"]  # how a few ended instead


def test_the_docs_pictures_of_the_studio(stack, approving, provider, browser):
    stack.with_watcher()
    back = []  # how many days back each run goes, in the order they ran
    for days, runs in enumerate(DAYS):
        for i in range(runs):
            stack.model.reply(None, ("search_records", {"query": "invoice"}))
            if i % 2 == 0:
                stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
            stack.model.reply("Q-1001 is open: the invoice went to the wrong address.")
            stack.say("What's open?", person="ben" if i % 3 == 2 else "ana")
            back.append(days)
    # Onto the core's days, which the tests keep at QUIET, by whole days, so each run's calls
    # keep the time of day they had
    shift = math.ceil((datetime.now(UTC) - QUIET).total_seconds() / 86400)
    with db.transaction(stack.admin) as conn:
        runs = [r["id"] for r in conn.execute("select id from runs order by opened_at")]
        assert len(runs) == len(back)
        for run, days in zip(runs, back, strict=True):
            conn.execute("update runs set opened_at = opened_at - make_interval(days => %(d)s), "
                         "closed_at = closed_at - make_interval(days => %(d)s) where id = %(run)s",
                         {"d": shift + days, "run": run})
        for run, ended in zip(runs[4::9], OTHERWISE * 3, strict=False):
            conn.execute("update runs set outcome = %s where id = %s", (ended, run))

    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Singapore")
    page.emulate_media(color_scheme="light")
    page.goto(f"{approving}/studio/")
    page.wait_for_selector(".agent-card >> text=watcher", timeout=30000)
    page.screenshot(path=f"{FOLDER}/a5s-studio-catalogue.png")

    page.click(".agent-card a.agent-name:text-is('assistant')")
    page.wait_for_selector(".agent-map .map-node >> text=change_due_date", timeout=30000)
    page.screenshot(path=f"{FOLDER}/a5s-studio-agent.png")

    page.click("table.grid-table a:has-text('assistant-finance')")
    page.wait_for_selector(".runs-chart .day", timeout=30000)
    page.screenshot(path=f"{FOLDER}/a5s-studio-dashboard.png")

    page.click("table.runs-table a:has-text('Open') >> nth=0")  # the latest
    page.wait_for_selector(".agent-map .map-count", timeout=30000)
    assert page.locator(".agent-map .map-count").count() == 2  # it looked a question up, then read it
    page.screenshot(path=f"{FOLDER}/a5s-studio-run.png")
