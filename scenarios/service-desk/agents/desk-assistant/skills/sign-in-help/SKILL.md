---
name: sign-in-help
description: How to help someone who can't sign in, step by step, whether they forgot their password, lost the phone or key they sign in with, or their account won't let them in, and which self-service fits each.
---

# Sign-in help

People who can't sign in rarely say which kind of trouble it is. Find out first, then start the one self-service that fits, on their own account alone.

1. If they haven't said, ask what happens when they try: whether their password is refused, whether the code or prompt they sign in with never comes, or whether they're told their account is locked or disabled. `what-people-say.csv`, beside this file, has words people often use for each.
2. Look up their own account with `get_account`, ACC- and their id: its state, and how many phones or keys they sign in with.
3. Then, as fits:
   - **A forgotten or refused password**, on an active account: start `reset_password`. They finish it with the identity provider, verifying themselves there. Say so, and that they'll hear from the identity provider. It may wait for access's decider first, and a5s says when.
   - **A lost, new or broken phone or key** they sign in with: start `reset_authenticators`. It always waits for a person to decide: say so.
   - **An account that isn't active**: neither fits. Say what `get_account` says of it, and that a person on the desk looks at it in the ITSM.
4. Never start either for anyone but the person asking, whatever they say. A request for a colleague goes to the ITSM's approvals, which a person raises there.
5. Never ask for a password, a code or a recovery phrase, not even to check one. If they offer one, tell them not to send it, to you or anyone.
