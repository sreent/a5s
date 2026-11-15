// An agent on a canvas, as Ocean draws steps (FlowNode: n8n's way, in Ocean's colours). What
// starts its runs is on the left, rounded where nothing comes in; then the agent, wide, in the
// agent colour; then what each run ends in, its reply. Below the agent, from the slots along its
// foot, hangs what it works with: its model, a5s's checks, which every call to a tool passes,
// and its tools, each icon in the colour of what the tool does, so risk shows before anything
// runs. An agent isn't a chain of steps, as a workflow is: its model chooses which tools to call,
// in any order, so they hang from it, and never stand in a line that would say otherwise.
//
// Given `pick`, each step is a button: choosing one shows it, and the arrow keys move from step
// to step. Without it, the canvas is a picture of how the agent is wired, or of what a run did.

import { type Edge, Handle, type Node, type NodeProps, Position, ReactFlow, ReactFlowProvider,
  useReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/base.css";  // React Flow's own, never its style.css: Ocean draws the rest
import { type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "./icons";

export type Tone = "reads" | "writes" | "changes" | "outside" | "own" | "refused" | "agent";  // agent: another agent
export type Slot = "model" | "checks" | "tools";

/** A step on the canvas: what it is, in its words, and how it stands. */
export type Step = {
  key: string;
  icon: string;
  name: string;
  about?: string;
  tone?: Tone;
  slot?: Slot;  // what hangs from the agent: which slot of its foot
  state?: "good" | "warn" | "bad";  // in its corner: how it stood after a run
  stateSays?: string;  // that state, in words, for whoever can't see it
  problems?: number;  // a count, on --bad, in its top corner
  dim?: boolean;  // what a run didn't use
  path?: "ran" | "refused";  // where a run went: its curve green, or red where a5s refused it
};

export type Flow = { starts: Step[]; agent: Step; end: Step | null; hanging: Step[] };

type Kind = "trigger" | "agent" | "end" | "hanging" | "stub";
type Data = { step: Step; kind: Kind; chosen: boolean; pick?: (key: string, keyboard: boolean) => void };

const STATES = { good: "check", warn: "clock", bad: "cross" } as const;
const SLOTS: [Slot, string][] = [["model", "Model"], ["checks", "Checks"], ["tools", "Tools"]];
// Where steps stand, in pixels at a rem of 15: a column of what starts it, the agent, its end,
// and below them, in rows of five, what hangs from it
const STEP = 120, GAP_Y = 150, AGENT_X = 250, AGENT_W = 210, END_X = 590, HANG_GAP = 132, HANG_Y = 210;
const PER_ROW = 5, ROW_Y = 150, STARTS_FOOT = 130;

function FlowStep({ data }: NodeProps<Node<Data>>) {
  const { step, kind, chosen, pick } = data;
  const classes = ["flow-step", step.tone === "agent" ? "agent-tone" : step.tone ?? "", kind === "end" ? "last" : kind,
                   chosen ? "chosen" : "", step.dim ? "dim" : ""].filter(Boolean).join(" ");
  const inside: ReactNode = (
    <>
      <Icon name={step.icon} />
      {kind === "agent" && <span className="flow-agent-text"><strong>{step.name}</strong><span>{step.about}</span></span>}
      {step.state && (
        <span className={`flow-state ${step.state === "good" ? "" : step.state}`} role="img" aria-label={step.stateSays ?? step.state}>
          <Icon name={STATES[step.state]} />
        </span>
      )}
      {!!step.problems && <span className="flow-problems" role="img" aria-label={`${step.problems} refused`}>{step.problems}</span>}
      {kind === "agent" && (
        <span className="flow-slots">{SLOTS.map(([slot, label]) => <span key={slot} className="flow-slot"><span>{label}</span></span>)}</span>
      )}
    </>
  );
  const label = step.about ? `${step.name}: ${step.about}` : step.name;
  return (
    <div className={classes} data-key={step.key}>
      {pick ? (
        <button type="button" className="flow-box nodrag" data-step={step.key} aria-pressed={chosen} aria-label={label}
                onClick={(e) => pick(step.key, e.detail === 0)}>{inside}</button>
      ) : <div className="flow-box">{inside}</div>}
      {kind !== "agent" && <span className="flow-name">{step.name}</span>}
      {kind !== "agent" && step.about && <span className="flow-about">{step.about}</span>}
      {kind === "trigger" && <Handle type="source" position={Position.Right} className="at-right" isConnectable={false} />}
      {kind === "end" && <Handle type="target" position={Position.Left} className="at-left" isConnectable={false} />}
      {kind === "hanging" && <Handle type="target" position={Position.Top} className="at-top" isConnectable={false} />}
      {kind === "agent" && (
        <>
          <Handle type="target" position={Position.Left} className="at-left" isConnectable={false} />
          <Handle type="source" position={Position.Right} className="at-right" id="end" isConnectable={false} />
          {SLOTS.map(([slot]) => (
            <Handle key={slot} type="source" position={Position.Bottom} className={`at-${slot}`} id={slot} isConnectable={false} />
          ))}
        </>
      )}
    </div>
  );
}

function Stub({ data }: NodeProps<Node<Data>>) {
  return (
    <button type="button" className="flow-stub nodrag" aria-label={data.step.name} title={data.step.name}
            data-step={data.step.key} onClick={(e) => data.pick?.(data.step.key, e.detail === 0)}>+</button>
  );
}

const NODE_TYPES = { step: FlowStep, stub: Stub };

/** The canvas's own buttons: zooming at the left of its foot, as n8n has them. */
function Zoom() {
  const flow = useReactFlow();
  return (
    <div className="flow-tools">
      <button type="button" aria-label="Zoom in" onClick={() => flow.zoomIn()}>+</button>
      <button type="button" aria-label="Zoom out" onClick={() => flow.zoomOut()}>−</button>
      <button type="button" onClick={() => flow.fitView({ padding: 0.12 })}>Show it all</button>
    </div>
  );
}

/** The steps of a flow, placed: what starts it, the agent and its end, and what hangs below,
 * clear of what starts it, in rows each centred under the agent. */
function placed(flow: Flow, chosen: string | null, pick: Data["pick"], stubs: Step[]) {
  const middle = (Math.max(flow.starts.length - 1, 0) * GAP_Y) / 2;
  const node = (step: Step, kind: Kind, x: number, y: number): Node<Data> =>
    ({ id: step.key, type: kind === "stub" ? "stub" : "step", position: { x, y },
       data: { step, kind, chosen: chosen === step.key, pick } });
  const centre = AGENT_X + AGENT_W / 2;
  const foot = flow.starts.length ? (flow.starts.length - 1) * GAP_Y + STARTS_FOOT : 0;
  const top = Math.max(middle + HANG_Y, foot + 50);
  const hanging: [Step, Kind][] = [...flow.hanging.map((s): [Step, Kind] => [s, "hanging"]),
                                   ...stubs.filter((s) => s.slot).map((s): [Step, Kind] => [s, "stub"])];
  const at = (i: number) => {  // the place of the i-th thing that hangs: its row, and in it
    const row = Math.floor(i / PER_ROW);
    const across = Math.min(PER_ROW, hanging.length - row * PER_ROW);
    const stagger = row % 2 ? HANG_GAP / 2 : 0;  // so the curves to a row pass between the steps above it
    return { x: centre - ((across - 1) * HANG_GAP) / 2 - STEP / 2 + (i % PER_ROW) * HANG_GAP + stagger,
             y: top + row * ROW_Y };
  };
  const nodes: Node<Data>[] = [
    ...flow.starts.map((s, i) => node(s, "trigger", 0, i * GAP_Y)),
    node(flow.agent, "agent", AGENT_X, middle),
    ...(flow.end ? [node(flow.end, "end", END_X, middle)] : []),
    // what hangs, then a way to add another after it; and below what starts it, a way to add one
    ...hanging.map(([s, kind], i) => (kind === "stub" ? node(s, "stub", at(i).x + STEP / 2 - 13, at(i).y + 12)
                                                       : node(s, kind, at(i).x, at(i).y))),
    ...stubs.filter((s) => !s.slot).map((s) => node(s, "stub", 46, foot + 4)),
  ];
  const edges: Edge[] = [
    ...flow.starts.map((s) => ({ id: `in-${s.key}`, source: s.key, target: flow.agent.key,
                                 className: [s.dim ? "dim" : "", s.path ?? ""].filter(Boolean).join(" ") })),
    ...(flow.end ? [{ id: "out", source: flow.agent.key, sourceHandle: "end", target: flow.end.key }] : []),
    ...flow.hanging.map((s) => ({ id: `hangs-${s.key}`, source: flow.agent.key, sourceHandle: s.slot ?? "tools",
                                  target: s.key, className: ["hangs", s.dim ? "dim" : "", s.path ?? ""].filter(Boolean).join(" ") })),
  ];
  return { nodes, edges };
}

/** Which step the arrow keys move to from one, by where steps stand on the canvas. */
function moved(flow: Flow, from: string, key: string): string | null {
  const starts = flow.starts.map((s) => s.key);
  const hanging = flow.hanging.map((s) => s.key);
  const agent = flow.agent.key;
  if (starts.includes(from)) {
    const i = starts.indexOf(from);
    return key === "ArrowRight" ? agent : key === "ArrowUp" ? starts[i - 1] ?? null : key === "ArrowDown" ? starts[i + 1] ?? null : null;
  }
  if (from === agent) {
    return key === "ArrowLeft" ? starts[Math.floor((starts.length - 1) / 2)] ?? null
      : key === "ArrowRight" ? flow.end?.key ?? null : key === "ArrowDown" ? hanging[0] ?? null : null;
  }
  if (flow.end && from === flow.end.key) return key === "ArrowLeft" ? agent : null;
  const i = hanging.indexOf(from);
  if (i < 0) return null;
  return key === "ArrowLeft" ? hanging[i - 1] ?? null : key === "ArrowRight" ? hanging[i + 1] ?? null
    : key === "ArrowUp" ? agent : null;
}

export function FlowMap({ flow, label, chosen = null, pick, stubs = [], drop, remove, children, height }: {
  flow: Flow;
  label: string;
  chosen?: string | null;
  pick?: (key: string, keyboard: boolean) => void;
  stubs?: Step[];  // ways to add, on the canvas
  drop?: (dragged: DataTransfer) => boolean;  // something dragged onto it, such as a tool
  remove?: (key: string) => void;  // a step taken away from the keyboard
  children?: ReactNode;  // what sits on the canvas: its one thing to do, a way to add
  height?: number;
}) {
  const { nodes, edges } = placed(flow, chosen, pick, pick ? stubs : []);
  const keys = (e: KeyboardEvent) => {
    const from = (e.target as HTMLElement).closest("[data-step]")?.getAttribute("data-step");
    if (!from || !pick) return;
    if ((e.key === "Delete" || e.key === "Backspace") && remove) {
      e.preventDefault();
      remove(from);
      return;
    }
    const to = moved(flow, from, e.key);
    if (to) {
      e.preventDefault();
      document.querySelector<HTMLElement>(`.flow [data-step="${CSS.escape(to)}"]`)?.focus();
    }
  };
  const over = (e: DragEvent) => {
    if (!drop) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };
  return (
    <ReactFlowProvider>
      <section className="flow flow-canvas" aria-label={label} onKeyDown={keys} style={height ? { height } : undefined}>
        <ReactFlow key={nodes.length} nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} colorMode="system" fitView
                   fitViewOptions={{ padding: 0.12, maxZoom: 1 }} nodesDraggable={false} nodesConnectable={false}
                   nodesFocusable={false} edgesFocusable={false} elementsSelectable={false} panOnDrag={Boolean(pick)}
                   panOnScroll={Boolean(pick)} zoomOnScroll={false} zoomOnPinch={Boolean(pick)} zoomOnDoubleClick={false}
                   preventScrolling={Boolean(pick)} minZoom={0.35} maxZoom={1.5} proOptions={{ hideAttribution: false }}
                   onNodeClick={pick ? () => undefined : undefined}  // React Flow gives steps the pointer only then
                   onDragOver={over} onDrop={(e) => {
                     if (drop?.(e.dataTransfer)) e.preventDefault();
                   }} />
        {pick && <Zoom />}
        {children}
      </section>
    </ReactFlowProvider>
  );
}
