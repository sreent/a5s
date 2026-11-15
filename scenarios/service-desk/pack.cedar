// The service desk's pack, beside a5s's base pack, which it can only restrict
// (scenarios/it-service-desk.md#the-service-desk-pack). The release covers it, as it covers
// the rest of the scenario's folder.

// Self-service runs alone, at level 2, only for the person asking, on their own account: the
// identity provider verifies them in its own flow. Anyone else's goes to the ITSM's approvals.
@id("desk-self-service-only-for-the-person-asking")
@reason("self-service runs alone only for the person asking, on their own account: a request for anyone else goes to the ITSM's approvals")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "reset-password" && context.level >= 2 && !context.for_self };

// An authenticator change never runs alone: below level 2 it waits for the decider of access,
// as every change does, and no level lets it through, since that's how account takeovers start.
@id("desk-authenticators-go-to-a-person")
@reason("registering or removing an authenticator always goes to a person, since that's how account takeovers start: at level 1, it waits for one")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "reset-authenticators" && context.level >= 2 };
