"""Round 11, reviewer D: need-to-know in the lists around the layers of what someone may know
of an agent (core/studio.py). The chat named every agent to anyone, without sign-in, and a
message to an agent that didn't serve its sender named the owners of the parts it works in."""

import httpx

from a5s.services.scheduler import NO_SUCH
from test_webchat import channels


def test_the_chats_config_names_no_agent(stack):  # D-1
    with channels(stack) as url:
        config = httpx.get(f"{url}/chat/config").json()
        assert "agents" not in config
        mine = httpx.get(f"{url}/channels/local/agents", params={"person": "ana"}).json()
        theirs = httpx.get(f"{url}/channels/local/agents", params={"person": "chen"}).json()
    assert mine == {"agents": ["assistant"]}  # the one that serves her
    assert theirs == {"agents": []}  # Chen: none serves him


def test_an_agent_its_sender_may_not_know_of_is_answered_as_one_there_isnt(stack):  # D-1
    unlisted = stack.say("hi", person="chen", agent="watcher")  # none of his, and unlisted
    made_up = stack.say("hi", person="chen", agent="made-up")
    assert unlisted == NO_SUCH.format(agent="watcher") and made_up == NO_SUCH.format(agent="made-up")
    assert "Ana" not in unlisted + made_up and not stack.model.requests


def test_someone_who_may_know_of_an_agent_is_told_to_ask_for_it_naming_nobody(stack):  # D-1
    said = stack.say("hi", person="priya")  # she owns the assistant, which doesn't serve her
    assert said == "There's no assistant for you yet. Ask for it on its page in the studio."
    assert "Ana" not in said and "billing" not in said
