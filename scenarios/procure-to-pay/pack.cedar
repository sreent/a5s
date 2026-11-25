// Procure-to-pay's pack, beside a5s's base pack, which it can only restrict
// (scenarios/procure-to-pay.md#its-pack). The release covers it, as it covers the rest of the
// scenario's folder. A level of 2 is acting on its own, and 1 asking first (a5s/levels.py).

// No invoice is ever approved for payment on an agent's word alone: whatever the settings say,
// it waits for payables' deciders, two of them above the settings' amount, since that's where
// a fraud pays out.
@id("p2p-payments-wait-for-people")
@reason("an invoice is approved for payment only by its deciders, never by an agent on its own")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.action == "approve-payment" && context.level >= 2 };
