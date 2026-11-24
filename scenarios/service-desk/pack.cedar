// The service desk's pack, beside a5s's base pack, which it can only restrict
// (scenarios/it-service-desk.md#the-service-desk-pack). The release covers it, as it covers
// the rest of the scenario's folder.

// Self-service runs on its own only for the person asking, on their own account: the identity
// provider verifies them in its own flow. Anyone else's waits for the decider of access. A level of
// 2 is acting on its own, and 1 asking first (a5s/levels.py).
@id("desk-self-service-only-for-the-person-asking")
@reason("self-service runs alone only for the person asking, on their own account: a request for anyone else waits for the decider of access")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "reset-password" && context.level >= 2 && !context.for_self };

// An authenticator change never runs on its own: where the agent asks first, it waits for the
// decider of access, as every change does, and nothing lets it through on its own, since that's
// how account takeovers start.
@id("desk-authenticators-go-to-a-person")
@reason("registering or removing an authenticator always goes to a person, since that's how account takeovers start: the agent never makes one on its own")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "reset-authenticators" && context.level >= 2 };

// A lost device's holder may have it locked at once, on its own, on their own device in answer
// to their own message, as a reset; anyone else's waits for the decider of hardware, who knows
// whether it's really lost, as every change does where the agent asks first.
@id("desk-locks-only-for-the-person-asking")
@reason("a device locks alone only for its holder, asking themselves: anyone else's waits for the decider of hardware")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "lock-device" && context.level >= 2 && !context.for_self };
