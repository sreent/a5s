"""Round 11, reviewer E: the web chat (E-2, E-5). Text the core kept as one record link showed in
the chat as two links, the second to anywhere; and the page told who spoke by the sender's name
alone, which an agent's could match."""

from pathlib import Path

import httpx
import pytest

from a5s import authoring, definitions
from a5s.core.gateway import sanitize
from conftest import ROOT
from test_webchat import answering, channels  # noqa: F401 - a fixture

RECORDS = ("https://sample.a5s.dev/",)
RECORD = "https://sample.a5s.dev/records/Q-1001"
OUT = "https://collect.attacker.test/c?d=IBAN-DE89370400440532013000"


@pytest.mark.parametrize("joint", ["'", '"', "`", "<"])
def test_an_address_ends_where_a_page_ends_a_link(joint):  # E-2
    kept, removed = sanitize(f"The record: {RECORD}{joint}{OUT}", RECORDS)
    assert OUT not in kept and RECORD in kept and removed == 1


def test_a_record_link_carries_nothing_past_its_target():  # E-2
    kept, _ = sanitize(f"[Q-1001]({RECORD}'{OUT})", RECORDS)
    assert kept == f"[Q-1001]({RECORD})"
    kept, removed = sanitize(f"[{OUT}]({RECORD})", RECORDS)  # its words hold an address
    assert OUT not in kept and RECORD in kept and removed == 1


@pytest.mark.usefixtures("answering")
def test_the_chat_links_only_records_and_a5s_own_pages(stack, browser):  # E-2
    stack.model.reply(f"Q-1001 is here: {RECORD} and not {OUT[:-1]}")
    with channels(stack) as url:
        config = httpx.get(f"{url}/chat/config").json()
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        page.fill("#text", "Where is Q-1001?")
        page.keyboard.press("Enter")
        page.wait_for_selector("li.agent a", timeout=30000)
        links = page.locator("li.agent a").evaluate_all("(as) => as.map((a) => a.href)")
    assert config["links"] == [*RECORDS, f"{stack.gateway.public_url}/"]
    assert links == [RECORD]  # the core removed the other, and the page links no other


def test_what_the_chat_shows_says_who_spoke_apart_from_their_name(stack):  # E-5
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with channels(stack) as url:
        said = httpx.get(f"{url}/channels/local/conversation",
                         params={"agent": "assistant", "person": "ana"}).json()["messages"]
    assert [(m["from"], m["by"]) for m in said] == [("you", "person"), ("assistant", "agent")]


@pytest.mark.parametrize("name", sorted(definitions.RESERVED))
def test_no_agent_is_called_you_or_a5s(name, tmp_path: Path):  # E-5
    with pytest.raises(ValueError, match=f"an agent can't be called {name}"):
        authoring.new(ROOT / "agents" / "assistant", name, tmp_path, {})
    folder = tmp_path / "copied"
    folder.mkdir()
    (folder / "AGENTS.md").write_text("Help.\n")
    spec = (ROOT / "agents" / "assistant" / "agent.yaml").read_text()
    (folder / "agent.yaml").write_text(spec.replace("id: assistant", f"id: {name}", 1))
    with pytest.raises(ValueError, match=f"an agent can't be called {name}"):
        definitions.load(folder)
