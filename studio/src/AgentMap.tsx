// An agent as a map: what starts its runs, on the left; the agent; a5s's checks, which every call
// to a tool passes through; and its tools, coloured by what they do, changes first. Read only:
// it shows how the agent is wired, and the release, not this page, is where that changes.
//
// Given a run, the map shows that run's path through it: what started it, and each tool it
// called, how many times, and how many of those a5s refused; what it didn't use fades.

import { Background, type Edge, Handle, type Node, type NodeProps, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Agent, Call, Run } from "./api";
import { Icon } from "./icons";
import { levels, plural, type Risk, risk, RISK_NAMES, triggers } from "./ui";

type Card = {
  icon: string; title: string; detail?: string; tone?: string; left?: boolean; right?: boolean;
  kind?: string;    // of a start: the kind of trigger it stands for
  calls?: number;   // of the run's calls, how many went this way
  refused?: number; // and how many of those a5s refused
  dim?: boolean;    // not on the run's path
};

function CardNode({ data }: NodeProps<Node<Card>>) {
  return (
    <div className={`map-node ${data.tone ?? ""}${data.dim ? " dim" : ""}`}>
      {data.left && <Handle type="target" position={Position.Left} isConnectable={false} />}
      <Icon name={data.icon} className="icon map-icon" />
      <div className="map-text">
        <div className="map-title">{data.title}</div>
        {data.detail && <div className="map-detail">{data.detail}</div>}
      </div>
      {!!data.calls && (
        <span className={`map-count${data.refused ? " bad" : ""}`}>
          {data.refused ? `${data.refused} of ${data.calls} refused` : `×${data.calls}`}
        </span>
      )}
      {data.right && <Handle type="source" position={Position.Right} isConnectable={false} />}
    </div>
  );
}

const NODE_TYPES = { card: CardNode };
const ROW = 66;
const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];

function starts(agent: Agent): Card[] {
  const found: Card[] = [];
  for (const t of triggers(agent).filter((t) => t.kind === "message")) {
    found.push({ icon: "message", title: "A message", kind: "message",
                 detail: `${t.about}, on ${agent.channels.join(", ") || "its channels"}` });
  }
  for (const s of agent.schedules) {
    found.push({ icon: "clock", title: s.name, kind: "schedule",
                 detail: `${s.at.join(", ")}, ${s.days.length === 7 ? "every day" : s.days.join(" ")}` });
  }
  if (agent.obligations.length) {
    found.push({ icon: "bell", title: "What people owe", detail: agent.obligations.join(", "), kind: "obligation" });
  }
  if (agent.reminders) found.push({ icon: "bell", title: "Reminders", detail: "people asked for", kind: "reminder" });
  for (const source of agent.reports) found.push({ icon: "report", title: "A report", detail: `on ${source}`, kind: "report" });
  for (const t of triggers(agent).filter((t) => t.kind !== "message")) {
    found.push({ icon: "run", title: t.kind, detail: t.about, kind: t.kind });
  }
  return found.length ? found : [{ icon: "run", title: "Nothing starts it" }];
}

/** Of some calls, how many there were and how many a5s refused. */
function tally(calls: Call[]): Pick<Card, "calls" | "refused"> {
  return { calls: calls.length, refused: calls.filter((c) => c.decision === "deny").length };
}

export function AgentMap({ agent, run }: { agent: Agent; run?: Run }) {
  const kind = run ? String(run.started_by.kind ?? run.trigger ?? "") : undefined;
  const left = starts(agent).map((card) => ({ ...card, dim: run !== undefined && card.kind !== kind }));
  if (run && kind && !left.some((card) => card.kind === kind)) {  // started some other way
    left.push({ icon: "run", title: kind, detail: "how this run started", kind, dim: false });
  }
  const calls = run?.calls ?? [];
  const tools = [...agent.tools].sort((a, b) => ORDER.indexOf(risk(a)) - ORDER.indexOf(risk(b)));
  const right: (Card & { risk?: Risk })[] = tools.map((tool) => {
    const these = tally(calls.filter((c) => c.tool === tool.name));
    if (tool.missing) {  // as a draft may name it: a tool the scenario hasn't got
      return { icon: "tool", title: tool.name, tone: "denied", detail: "not one of the scenario's tools", ...these };
    }
    return { icon: "tool", title: tool.name, tone: risk(tool), risk: risk(tool), ...these,
             detail: tool.changes ? `changes ${tool.changes}` : RISK_NAMES[risk(tool)],
             dim: run !== undefined && !these.calls };
  });
  if (agent.a5s_tools.length) {
    const these = tally(calls.filter((c) => agent.a5s_tools.includes(c.tool)));
    right.push({ icon: "agent", title: "a5s's own", tone: "own", ...these, dim: run !== undefined && !these.calls,
                 detail: `${agent.a5s_tools.length} tools: tasks, reminders, notes…` });
  }
  const known = new Set([...agent.tools.map((t) => t.name), ...agent.a5s_tools]);
  for (const name of [...new Set(calls.map((c) => c.tool))].filter((n) => !known.has(n))) {
    right.push({ icon: "tool", title: name, tone: "denied", detail: "not among its tools",
                 ...tally(calls.filter((c) => c.tool === name)) });
  }
  const rows = Math.max(left.length, right.length, 3);
  const middle = ((rows - 1) * ROW) / 2;
  const column = (cards: Card[], x: number, id: string, extra: Partial<Card>): Node<Card>[] =>
    cards.map((card, i) => ({
      id: `${id}-${i}`, type: "card", position: { x, y: middle - ((cards.length - 1) * ROW) / 2 + i * ROW },
      data: { ...card, ...extra },
    }));
  const refused = calls.filter((c) => c.decision === "deny").length;
  const nodes: Node<Card>[] = [
    ...column(left, 0, "start", { right: true }),
    { id: "agent", type: "card", position: { x: 320, y: middle },
      data: { icon: "agent", title: agent.id, tone: "agent", left: true, right: true,
              detail: run ? `${run.model ?? agent.model}, ${plural(run.tokens, "token")}`
                          : `${agent.model}, ${levels(agent.autonomy)}` } },
    { id: "checks", type: "card", position: { x: 620, y: middle },
      data: { icon: "shield", title: "a5s's checks", tone: "checks", left: true, right: true,
              detail: run ? `${plural(calls.length, "call")}, ${refused} refused` : "policy, need-to-know, budget" } },
    ...column(right, 920, "tool", { left: true }),
  ];
  const path = (on: boolean) => (run === undefined ? "" : on ? "used" : "unused");
  const edges: Edge[] = [
    ...left.map((card, i) => ({ id: `in-${i}`, source: `start-${i}`, target: "agent", type: "smoothstep",
                                className: path(!card.dim) })),
    { id: "to-checks", source: "agent", target: "checks", type: "smoothstep", className: path(calls.length > 0) },
    ...right.map((card, i) => ({
      id: `out-${i}`, source: "checks", target: `tool-${i}`, type: "smoothstep",
      className: [`edge-${card.risk ?? (card.tone === "denied" ? "denied" : "own")}`, path(!!card.calls),
                  card.refused ? "refused" : ""].filter(Boolean).join(" "),
    })),
  ];
  return (
    <div className="agent-map" style={{ height: Math.max(rows * ROW + 60, 260) }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} colorMode="system" fitView
                 fitViewOptions={{ padding: 0.12 }} nodesDraggable={false} nodesConnectable={false}
                 elementsSelectable={false} zoomOnScroll={false} preventScrolling={false}
                 minZoom={0.4} maxZoom={1.4}>
        <Background gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}
