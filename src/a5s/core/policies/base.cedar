// a5s's base policy pack. Anything these policies don't permit is denied.
// A scenario's pack can only add forbids. Each policy's @reason says, in
// words, what the agent and people see when it decides a call.

@id("active-instances-use-their-grant")
@reason("the tool is in the instance's grant")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "active" && resource.known && principal.grants.contains(resource.name)
  && (resource.action == "" || (context.level >= 2 && !context.over_limit))
};

// A change to a part's data, below level 2 or past the scenario's limits, waits for a person:
// the owner of the part its record is in decides it, on the core's own page, and the gateway
// makes it once approved.
@id("level-1-changes-wait-for-their-decider")
@reason("below level 2, a change waits for the owner of the record's part to decide it")
@hold("true")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "active" && resource.known && principal.grants.contains(resource.name)
  && resource.action != "" && context.level == 1 && !context.over_limit
};

@id("changes-past-a-limit-wait-for-their-decider")
@reason("past the scenario's limit for its type of action, a change waits for the owner of the record's part to decide it, whatever the level")
@hold("true")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "active" && resource.known && principal.grants.contains(resource.name)
  && resource.action != "" && context.level >= 1 && context.over_limit
};

@id("tools-match-the-release")
@reason("the tool has changed since the release pinned it")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.known && !resource.pinned };

@id("level-0-only-observes")
@reason("at level 0 the agent only observes, so it can't use a tool that writes")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && context.level < 1 };

@id("lasting-or-outside-effects-need-level-2")
@reason("a tool that can't be undone, or that sends outside the organisation, needs level 2")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { (resource.destructive || resource.sends_outside) && context.level < 2 };

@id("marked-runs-never-act-at-level-2")
@reason("a run that has read outside content can't act at level 2")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && context.read_outside && context.level >= 2 };

@id("instances-work-only-in-their-parts")
@reason("the record is in a part the instance doesn't work in")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
unless { context.in_scope };

@id("people-see-only-what-they-may")
@reason("someone the run acts for may not see that record, or there's no such record")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
unless { context.visible };

@id("active-instances-use-their-model")
@reason("the model is approved, and is the instance's own")
permit (principal is Instance, action == Action::"call_model", resource is Model)
when { principal.status == "active" && resource.approved && principal.model == resource.name };

@id("models-see-only-data-they-are-approved-for")
@reason("the model isn't approved for the class of data the scenario holds")
forbid (principal is Instance, action == Action::"call_model", resource is Model)
unless { resource.classes.contains(context.data_class) };

@id("messages-go-only-to-the-audience")
@reason("the person is in the scenario's audience")
permit (principal is Instance, action == Action::"send_message", resource is Person)
when { principal.status == "active" && resource.in_audience };

@id("only-active-instances-act")
@reason("the instance is suspended or retired")
forbid (principal is Instance, action, resource)
unless { principal.status == "active" };
