// a5s's base policy pack. Anything these policies don't permit is denied.
// A scenario's pack can only add forbids. Each policy's @reason says, in
// words, what the agent and people see when it decides a call.

@id("active-instances-use-their-grant")
@reason("the tool is in the instance's grant")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when {
  principal.status == "active" && resource.known && principal.grants.contains(resource.name)
};

@id("tools-match-the-release")
@reason("the tool has changed since the release pinned it")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.known && !resource.pinned };

@id("level-0-only-observes")
@reason("at level 0 the agent only observes, so it can't use a tool that writes")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && principal.level < 1 };

@id("marked-runs-never-act-at-level-2")
@reason("a run that has read outside content can't act at level 2")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && context.read_outside && principal.level >= 2 };

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
