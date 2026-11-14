// An agent as a map: what starts its runs, on the left; the agent; a5s's checks, which every call
// to a tool passes through; and its tools, coloured by what they do, changes first. Read only:
// it shows how the agent is wired, and the release, not this page, is where that changes.

import { Background, Handle, type Node, type NodeProps, Position, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Agent } from "./api";
import { Icon } from "./icons";
import { levels, type Risk, risk, RISK_NAMES, triggers } from "./ui";

type Card = { icon: string; title: string; detail?: string; tone?: string; left?: boolean; right?: boolean };

function CardNode({ data }: NodeProps<Node<Card>>) {
  return (
    <div className={`map-node ${data.tone ?? ""}`}>
      {data.left && <Handle type="target" position={Position.Left} isConnectable={false} />}
      <Icon name={data.icon} className="icon map-icon" />
      <div className="map-text">
        <div className="map-title">{data.title}</div>
        {data.detail && <div className="map-detail">{data.detail}</div>}
      </div>
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
    found.push({ icon: "message", title: "A message", detail: `${t.about}, on ${agent.channels.join(", ") || "its channels"}` });
  }
  for (const s of agent.schedules) {
    found.push({ icon: "clock", title: s.name, detail: `${s.at.join(", ")}, ${s.days.length === 7 ? "every day" : s.days.join(" ")}` });
  }
  if (agent.obligations.length) found.push({ icon: "bell", title: "What people owe", detail: agent.obligations.join(", ") });
  if (agent.reminders) found.push({ icon: "bell", title: "Reminders", detail: "people asked for" });
  for (const source of agent.reports) found.push({ icon: "report", title: "A report", detail: `on ${source}` });
  for (const t of triggers(agent).filter((t) => t.kind !== "message")) found.push({ icon: "run", title: t.kind, detail: t.about });
  return found.length ? found : [{ icon: "run", title: "Nothing starts it" }];
}

export function AgentMap({ agent }: { agent: Agent }) {
  const left = starts(agent);
  const tools = [...agent.tools].sort((a, b) => ORDER.indexOf(risk(a)) - ORDER.indexOf(risk(b)));
  const right: (Card & { risk?: Risk })[] = tools.map((tool) => ({
    icon: "tool", title: tool.name, detail: tool.changes ? `changes ${tool.changes}` : RISK_NAMES[risk(tool)],
    tone: risk(tool), risk: risk(tool),
  }));
  if (agent.a5s_tools.length) {
    right.push({ icon: "agent", title: "a5s's own", detail: `${agent.a5s_tools.length} tools: tasks, reminders, notes…`, tone: "own" });
  }
  const rows = Math.max(left.length, right.length, 3);
  const middle = ((rows - 1) * ROW) / 2;
  const column = (cards: Card[], x: number, id: string, extra: Partial<Card>): Node<Card>[] =>
    cards.map((card, i) => ({
      id: `${id}-${i}`, type: "card", position: { x, y: middle - ((cards.length - 1) * ROW) / 2 + i * ROW },
      data: { ...card, ...extra },
    }));
  const nodes: Node<Card>[] = [
    ...column(left, 0, "start", { right: true }),
    { id: "agent", type: "card", position: { x: 320, y: middle },
      data: { icon: "agent", title: agent.id, detail: `${agent.model}, ${levels(agent.autonomy)}`, tone: "agent", left: true, right: true } },
    { id: "checks", type: "card", position: { x: 620, y: middle },
      data: { icon: "shield", title: "a5s's checks", detail: "policy, need-to-know, budget", tone: "checks", left: true, right: true } },
    ...column(right, 920, "tool", { left: true }),
  ];
  const edges: Edge[] = [
    ...left.map((_, i) => ({ id: `in-${i}`, source: `start-${i}`, target: "agent", type: "smoothstep" })),
    { id: "to-checks", source: "agent", target: "checks", type: "smoothstep" },
    ...right.map((card, i) => ({ id: `out-${i}`, source: "checks", target: `tool-${i}`, type: "smoothstep",
                                 className: `edge-${(card as { risk?: Risk }).risk ?? "own"}` })),
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
