// What depends on what, on a canvas (core/dependencies.py): a column for each kind of thing, as
// Ocean draws steps, left to right from the parts the settings name to the models agents call:
// parts, the instances at work in them, the agents they run, the tools each may call, the
// systems those come from, and the models. Each curve joins something to what it depends on.
//
// Choosing one marks it, and everything it depends on, and everything that depends on it, so a
// change to it shows what it reaches; the rest stays, dimmed. The arrow keys move up and down a
// column, and across to the nearest in the next.

import { type Edge, Handle, type Node, type NodeProps, Position, ReactFlow, ReactFlowProvider,
  useReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/base.css";  // React Flow's own, never its style.css: Ocean draws the rest
import type { KeyboardEvent } from "react";
import type * as gen from "./api.gen";
import { breakable } from "./FlowMap";
import { t } from "./i18n";
import { Icon } from "./icons";

export type MapNode = gen.MapNode;
export type MapEdge = gen.MapEdge;

export const KINDS = ["part", "instance", "agent", "tool", "system", "model"] as const;
export const KIND_NAMES: Record<string, string> = {  // one of each, in the language spoken when read
  get part() { return t("Part"); }, get instance() { return t("Instance"); }, get agent() { return t("Agent"); },
  get tool() { return t("Tool"); }, get system() { return t("System"); }, get model() { return t("Model"); },
};
const ICONS: Record<string, string> = {
  part: "settings", instance: "run", agent: "agent", tool: "tool", system: "plug", model: "model",
};
// Where steps stand, in pixels at a rem of 15: a column for each kind there is, and in each, a
// step under the one before. Each is a step as Ocean draws one, with a dot on each side where it
// joins what's left and right of it; its words are its name, and for a part, an instance, a
// system or a model, what it is in a few words: a tool's or an agent's own words are long, and
// are said when it's chosen
const COLUMN = 230, ROW = 165;
const SHORT = new Set(["part", "instance", "system", "model"]);

type Data = { node: MapNode; chosen: boolean; near: boolean; dim: boolean; pick: (key: string) => void };

/** What something depends on, and what depends on it, along the edges: each way, nearest first;
 * and the parts it reaches, where the instances that depend on it work, whose owners decide
 * what those do there. */
export function reaching(edges: MapEdge[], key: string): { on: string[]; by: string[]; parts: string[] } {
  const walk = (next: (e: MapEdge) => [string, string]) => {
    const seen = new Set([key]);
    const found: string[] = [];
    const queue = [key];
    while (queue.length) {
      const at = queue.shift()!;
      for (const e of edges) {
        const [from, to] = next(e);
        if (from === at && !seen.has(to)) {
          seen.add(to);
          found.push(to);
          queue.push(to);
        }
      }
    }
    return found;
  };
  const [on, by] = [walk((e) => [e.from, e.to]), walk((e) => [e.to, e.from])];
  const parts = [...new Set(edges.filter((e) => by.includes(e.from) && e.from.startsWith("instance:")
                                              && e.to.startsWith("part:")).map((e) => e.to))]
    .filter((part) => part !== key && !on.includes(part));
  return { on, by, parts };
}

function Thing({ data }: NodeProps<Node<Data>>) {
  const { node, chosen, near, dim, pick } = data;
  const tone = node.kind === "agent" ? "agent-tone" : node.tone ?? "";
  const classes = ["flow-step", tone, chosen ? "chosen" : "", dim && !near ? "dim" : ""]
    .filter(Boolean).join(" ");
  const kind = KIND_NAMES[node.kind] ?? node.kind;
  return (
    <div className={classes} data-key={node.key}>
      <button type="button" className="flow-box nodrag" data-step={node.key} aria-pressed={chosen}
              aria-label={`${kind}: ${node.name}${node.about ? `, ${node.about}` : ""}`} onClick={() => pick(node.key)}>
        <Icon name={ICONS[node.kind] ?? "tool"} />
      </button>
      <span className="flow-name">{breakable(node.name)}</span>
      {node.about && SHORT.has(node.kind) && <span className="flow-about">{node.about}</span>}
      <Handle type="target" position={Position.Left} className="at-left" id="in" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="at-right" id="out" isConnectable={false} />
      <Handle type="target" position={Position.Right} className="at-right" id="beside" isConnectable={false} />
    </div>
  );
}

const NODE_TYPES = { thing: Thing };

/** Each kind's column, of those there are, and each thing's place in it. */
export function columns(nodes: MapNode[]): MapNode[][] {
  return KINDS.map((kind) => nodes.filter((n) => n.kind === kind)).filter((col) => col.length);
}

function placed(nodes: MapNode[], edges: MapEdge[], chosen: string | null, pick: (key: string) => void) {
  const cols = columns(nodes);
  const column = new Map(cols.flatMap((col, x) => col.map((n) => [n.key, x] as const)));
  const tallest = Math.max(...cols.map((col) => col.length));
  const reach = chosen ? reaching(edges, chosen) : null;
  const near = new Set(reach ? [chosen!, ...reach.on, ...reach.by, ...reach.parts] : []);
  const placedNodes: Node<Data>[] = cols.flatMap((col, x) => col.map((node, y) => ({
    id: node.key, type: "thing",
    position: { x: x * COLUMN, y: (y + (tallest - col.length) / 2) * ROW },  // each column centred
    data: { node, chosen: node.key === chosen, near: near.has(node.key), dim: Boolean(chosen), pick },
  })));
  const placedEdges: Edge[] = edges.map((e) => {
    const [a, b] = [column.get(e.from) ?? 0, column.get(e.to) ?? 0];
    const [source, target] = a <= b ? [e.from, e.to] : [e.to, e.from];  // drawn left to right
    const lit = !chosen || (near.has(e.from) && near.has(e.to));
    return { id: `${e.from}>${e.to}`, source, target, sourceHandle: "out", targetHandle: a === b ? "beside" : "in",
             className: lit ? "" : "dim", ariaLabel: `${e.from} ${e.says} ${e.to}` };
  });
  return { nodes: placedNodes, edges: placedEdges, cols, tallest };
}

/** The canvas's own buttons, as the agent's canvas has them. */
function Zoom() {
  const flow = useReactFlow();
  return (
    <div className="flow-tools">
      <button type="button" aria-label={t("Zoom in")} onClick={() => flow.zoomIn()}>+</button>
      <button type="button" aria-label={t("Zoom out")} onClick={() => flow.zoomOut()}>−</button>
      <button type="button" onClick={() => flow.fitView({ padding: 0.1 })}>{t("Show it all")}</button>
    </div>
  );
}

export function DependsMap({ nodes, edges, chosen, pick, label }: {
  nodes: MapNode[];
  edges: MapEdge[];
  chosen: string | null;
  pick: (key: string) => void;
  label: string;
}) {
  const shown = placed(nodes, edges, chosen, pick);
  const keys = (e: KeyboardEvent) => {
    const from = (e.target as HTMLElement).closest("[data-step]")?.getAttribute("data-step");
    if (!from) return;
    const x = shown.cols.findIndex((col) => col.some((n) => n.key === from));
    const y = shown.cols[x]?.findIndex((n) => n.key === from) ?? -1;
    let to: MapNode | undefined;
    if (e.key === "ArrowUp") to = shown.cols[x][y - 1];
    if (e.key === "ArrowDown") to = shown.cols[x][y + 1];
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {  // the nearest in the next column
      const next = shown.cols[x + (e.key === "ArrowLeft" ? -1 : 1)];
      if (next) to = next[Math.min(Math.round((y / Math.max(shown.cols[x].length - 1, 1)) * (next.length - 1)), next.length - 1)];
    }
    if (to) {
      e.preventDefault();
      document.querySelector<HTMLElement>(`.flow [data-step="${CSS.escape(to.key)}"]`)?.focus();
    }
  };
  return (
    <ReactFlowProvider>
      <section className="flow flow-canvas" aria-label={label} onKeyDown={keys}
               style={{ height: Math.min(Math.max(shown.tallest * ROW + 140, 380), 720) }}>
        <ReactFlow key={nodes.length} nodes={shown.nodes} edges={shown.edges} nodeTypes={NODE_TYPES} colorMode="system"
                   fitView fitViewOptions={{ padding: 0.1, maxZoom: 1 }} nodesDraggable={false} nodesConnectable={false}
                   nodesFocusable={false} edgesFocusable={false} elementsSelectable={false} panOnDrag panOnScroll
                   zoomOnScroll={false} zoomOnPinch zoomOnDoubleClick={false} preventScrolling minZoom={0.25} maxZoom={1.5}
                   proOptions={{ hideAttribution: false }} onNodeClick={() => undefined} />
        <Zoom />
      </section>
    </ReactFlowProvider>
  );
}
