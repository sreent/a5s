"""Round 5, reviewer a: two checks that hold only for the forms they expect.

Approving: the page asks the provider for a fresh sign-in (max_age=0), but the core only
refuses a sign-in whose auth_time is old. A sign-in that doesn't say when the person signed
in, as a provider gives one that wasn't asked to be fresh, is taken as fresh.

Provenance: an amount or a date the agent writes in a common form the matcher doesn't know,
such as GBP before the number, or the month before the day, isn't flagged as its own.
"""

import secrets

from a5s.core import approvals
from test_approvals import decide, proposed


def test_approving_needs_a_sign_in_that_says_its_fresh(stack, approving, provider):
    asked = proposed(stack, level=0)
    salt = secrets.token_urlsafe(32)
    # From an existing session at the provider, with no max_age asked: it says no auth_time
    silent = provider.id_token(approvals.nonce(asked["digest"], salt), "ana")
    assert decide(approving, asked["digest"], silent, salt).status_code == 401


def test_an_amount_the_agent_made_up_is_flagged_in_any_common_form(stack):
    stack.model.reply("The refund is £9,999.00, paid on 30 Nov.")
    assert "(a5s: £9,999.00 and 30 Nov came from the assistant itself" in stack.say("The refund?")
    stack.model.reply("The refund is GBP 9,999.00, paid on Nov 30.")
    told = stack.say("And the other refund?")
    assert "(a5s:" in told, told  # today: nothing says it's the agent's own
