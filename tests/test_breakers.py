"""Circuit breakers: a model that fails three times in a row isn't called for five minutes,
so people hear at once, and a5s tries it again on its own afterwards."""

from a5s.core import breakers


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_model_that_keeps_failing_isnt_called_for_a_while(stack):
    clock = Clock()
    stack.gateway.breakers = breakers.Breakers(clock=clock)
    stack.model.failing = 3
    for _ in range(3):
        assert stack.say("Hello").startswith("The model I use isn't answering right now")
    assert len(stack.model.requests) == 3
    told = stack.say("Hello again")  # not called: people hear at once
    assert told.startswith("The model I use isn't answering right now")
    assert len(stack.model.requests) == 3 and stack.gateway.breakers.open() == ["fake"]

    clock.now += breakers.WAIT  # five minutes on, a5s tries it again, and it answers
    stack.model.reply("Hello, Ana.")
    assert stack.say("Are you back?") == "Hello, Ana."
    assert stack.gateway.breakers.open() == []
    changes = [(e["action"], e["args"]["model"]) for e in stack.ledger() if e["kind"] == "breaker"]
    assert changes == [("open", "fake"), ("close", "fake")]


def test_one_failure_that_follows_a_success_starts_the_count_again():
    held = breakers.Breakers(clock=Clock())
    assert not held.failed("m") and not held.failed("m")
    assert not held.worked("m")  # it wasn't open
    assert not held.failed("m") and not held.failed("m") and held.failed("m")
    assert held.allow("m") is False


def test_after_the_wait_one_call_tries_it_and_the_rest_wait_for_how_it_goes():
    clock = Clock()
    held = breakers.Breakers(clock=clock)
    for _ in range(3):
        held.failed("m")
    clock.now += breakers.WAIT
    assert held.allow("m") is True and held.allow("m") is False
    held.failed("m")  # it failed again: another five minutes
    assert held.allow("m") is False
    clock.now += breakers.WAIT
    assert held.allow("m") is True and held.worked("m") is True and held.allow("m") is True
