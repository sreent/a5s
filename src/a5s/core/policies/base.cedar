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

// A change to a part's data, where the agent asks first or past the scenario's limits, waits
// for a person: the owner of the part its record is in decides it, on the core's own page, and
// the gateway makes it once approved. context.level is what the agent may do for the call:
// 0 reads only, 1 asks first, 2 acts on its own (a5s/levels.py).
@id("changes-wait-for-their-decider")
@reason("the agent asks first here: the owner of the record's part decides the change")
@hold("true")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "active" && resource.known && principal.grants.contains(resource.name)
  && resource.action != "" && context.level == 1 && !context.over_limit
};

@id("changes-past-a-limit-wait-for-their-decider")
@reason("past the scenario's limit for its type of action, a change waits for the owner of the record's part to decide it, even where the agent may act on its own")
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

@id("reading-only-writes-nothing")
@reason("the agent reads only here, so it can't use a tool that writes")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && context.level < 1 };

@id("lasting-or-outside-effects-only-on-its-own")
@reason("a tool that can't be undone, or that sends outside the organisation, runs only where the agent acts on its own")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { (resource.destructive || resource.sends_outside) && context.level < 2 && resource.action == "" };

@id("marked-runs-never-act-on-their-own")
@reason("a run that has read outside content never acts on its own")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  (resource.writes || resource.destructive || resource.sends_outside)
  && context.read_outside && context.level >= 2
};

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
unless { principal.status == "active" || principal.status == "shadow" };

// A shadow answers what the instance it shadows is asked, beside it, for graders to compare
// (core/shadows.py): it reads with the tools of its grant that only read, and its own model,
// and nothing it does writes, changes or sends. No permit lets it send a message.
@id("shadows-only-read")
@reason("a shadow reads with the tools in its grant that change nothing, and sends nothing")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "shadow" && resource.known && principal.grants.contains(resource.name)
  && resource.action == "" && !resource.writes && !resource.destructive && !resource.sends_outside
};

@id("shadows-change-nothing")
@reason("a shadow changes nothing, and sends nothing: it answers for graders alone")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "shadow"
  && (resource.action != "" || resource.writes || resource.destructive || resource.sends_outside)
};

@id("shadows-use-their-model")
@reason("the model is approved, and is the shadow's own")
permit (principal is Instance, action == Action::"call_model", resource is Model)
when { principal.status == "shadow" && resource.approved && principal.model == resource.name };
