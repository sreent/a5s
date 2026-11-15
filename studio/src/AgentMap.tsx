// An agent on its canvas, read only, as the designer draws it (FlowMap.tsx, Ocean's FlowNode):
// what starts its runs; the agent and its reply; and, hanging below it, its model, a5s's checks,
// which every call to a tool passes, and its tools, each in the colour of what it does. It shows
// how the agent is wired; a draft, not this map, is where that changes.
//
// Given a run, the map shows that run's path through it: what started it, and each tool it
// called, with a tick and how many times, in green, and a count of those a5s refused, in red;
// what it didn't use fades.

import type { AgentUses, Call, Run } from "./api";
import { type Flow, FlowMap, type Step } from "./FlowMap";
import { levels, plural, type Risk, risk, RISK_NAMES, triggers } from "./ui";

// What the map draws of an agent: what starts its runs, and what it may do. An agent as someone
// sees it has it, if they may see what it does, and so has a draft's preview.
type Mapped = Pick<AgentUses, "id" | "model" | "autonomy" | "tools" | "a5s_tools" | "triggers" |
  "schedules" | "reports" | "obligations" | "reminders" | "channels">;

const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];
const times = (n: number) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);

/** What starts its runs, each by the kind of trigger it stands for. */
function starts(agent: Mapped): (Step & { kind: string })[] {
  const found: (Step & { kind: string })[] = [];
  for (const t of triggers(agent).filter((t) => t.kind === "message")) {
    found.push({ key: "messages", kind: "message", icon: "message", name: "A message",
                 about: `${t.about}, on ${agent.channels.join(", ") || "its channels"}` });
  }
  agent.schedules.forEach((s, i) => found.push({
    key: `schedule:${i}`, kind: "schedule", icon: "clock", name: s.name,
    about: `${s.at.join(", ")}, ${s.days.length === 7 ? "every day" : s.days.join(" ")}` }));
  if (agent.obligations.length) {
    found.push({ key: "obligations", kind: "obligation", icon: "bell", name: "What people owe", about: agent.obligations.join(", ") });
  }
  if (agent.reminders) found.push({ key: "reminders", kind: "reminder", icon: "bell", name: "Reminders", about: "people asked for" });
  agent.reports.forEach((source, i) => found.push({ key: `report:${i}`, kind: "report", icon: "report", name: "A report", about: `on ${source}` }));
  triggers(agent).filter((t) => t.kind !== "message").forEach((t, i) => found.push({
    key: `trigger:${i}`, kind: t.kind, icon: "run", name: t.kind, about: t.about }));
  return found.length ? found : [{ key: "nothing", kind: "", icon: "run", name: "Nothing starts it" }];
}

/** Of some calls: a tick and how many, and a count of those a5s refused. */
function marked(step: Step, calls: Call[], run: Run | undefined): Step {
  if (!run) return step;
  const refused = calls.filter((c) => c.decision === "deny").length;
  if (!calls.length) return { ...step, dim: true };
  return { ...step, about: `${step.about ? `${step.about}, ` : ""}called ${times(calls.length)}`,
           state: refused < calls.length ? "good" : undefined, stateSays: `called ${times(calls.length)}`,
           problems: refused || undefined, path: refused ? "refused" : "ran" };
}

export function flowOf(agent: Mapped, run?: Run): Flow {
  const kind = run ? String(run.started_by.kind ?? run.trigger ?? "") : undefined;
  const calls = run?.calls ?? [];
  const left: Step[] = starts(agent).map(({ kind: of, ...step }) =>
    (run ? { ...step, dim: of !== kind, path: of === kind ? "ran" as const : undefined } : step));
  if (run && kind && !left.some((s) => !s.dim)) {  // started some other way
    left.push({ key: "started", icon: "run", name: kind, about: "how this run started", path: "ran" });
  }
  const tools = [...agent.tools].sort((a, b) => ORDER.indexOf(risk(a)) - ORDER.indexOf(risk(b)));
  const hanging: Step[] = tools.map((tool): Step => {
    const these = calls.filter((c) => c.tool === tool.name);
    if (tool.missing) {  // as a draft may name it: a tool the scenario hasn't got
      return marked({ key: `tool:${tool.name}`, icon: "tool", name: tool.name, tone: "refused", slot: "tools",
                      about: "not one of the scenario's tools" }, these, run);
    }
    return marked({ key: `tool:${tool.name}`, icon: "tool", name: tool.name, tone: risk(tool), slot: "tools",
                    about: tool.changes ? `changes ${tool.changes}` : RISK_NAMES[risk(tool)].toLowerCase() }, these, run);
  });
  if (agent.a5s_tools.length) {
    hanging.push(marked({ key: "own", icon: "agent", name: "a5s's own", tone: "own", slot: "tools",
                          about: plural(agent.a5s_tools.length, "tool") },
                        calls.filter((c) => agent.a5s_tools.includes(c.tool)), run));
  }
  const known = new Set([...agent.tools.map((t) => t.name), ...agent.a5s_tools]);
  for (const name of [...new Set(calls.map((c) => c.tool))].filter((n) => !known.has(n))) {
    hanging.push(marked({ key: `tool:${name}`, icon: "tool", name, tone: "refused", slot: "tools", about: "not among its tools" },
                        calls.filter((c) => c.tool === name), run));
  }
  const refused = calls.filter((c) => c.decision === "deny").length;
  return {
    starts: left,
    agent: { key: "agent", icon: "agent", name: agent.id,
             about: run ? `${run.model ?? agent.model}, ${plural(run.tokens, "token")}` : `${agent.model}, ${levels(agent.autonomy)}` },
    end: { key: "reply", icon: "message", name: "Reply", about: "to whoever it acts for", tone: "own" },
    hanging: [
      { key: "model", icon: "model", name: "Model", about: run?.model ?? agent.model, slot: "model", path: run ? "ran" : undefined },
      { key: "checks", icon: "shield", name: "a5s's checks", tone: "own", slot: "checks",
        about: run ? `${plural(calls.length, "call")}, ${refused} refused` : "policy, need-to-know, limits",
        path: run && calls.length ? "ran" : undefined },
      ...hanging,
    ],
  };
}

export function AgentMap({ agent, run }: { agent: Mapped; run?: Run }) {
  const flow = flowOf(agent, run);
  const rows = Math.ceil((flow.hanging.length) / 5);
  return (
    <div className="agent-map">
      <FlowMap flow={flow} label={run ? "Its path through its agent" : "How it's wired"}
               height={Math.min(Math.max(320 + rows * 110 + flow.starts.length * 40, 380), 640)} />
    </div>
  );
}
