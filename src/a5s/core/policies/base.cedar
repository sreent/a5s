// a5s's base policy pack. Anything these policies don't permit is denied.
// A scenario's pack can only add forbids.

@id("active-instances-use-their-grant")
permit (principal is Instance, action == Action::"call_tool", resource is Tool)
when { principal.status == "active" && principal.grants.contains(resource.name) };

@id("tools-match-the-release")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
unless { resource.pinned };

@id("level-0-only-observes")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && principal.level < 1 };

@id("marked-runs-never-act-at-level-2")
forbid (principal is Instance, action == Action::"call_tool", resource is Tool)
when { resource.writes && context.read_outside && principal.level >= 2 };

@id("active-instances-use-their-model")
permit (principal is Instance, action == Action::"call_model", resource is Model)
when { principal.status == "active" && resource.approved && principal.model == resource.name };

@id("messages-go-only-to-the-audience")
permit (principal is Instance, action == Action::"send_message", resource is Person)
when { principal.status == "active" && resource.in_audience };

@id("only-active-instances-act")
forbid (principal is Instance, action, resource)
unless { principal.status == "active" };
