// What the studio's pages share: loading what a page shows, its heading with the way back, and
// the badges that say what a tool does, how something stands, and how a run ended.

import { type DependencyList, type ReactNode, useEffect, useState } from "react";
import type { Agent, Instance, Tool } from "./api";
import { Link, type Route } from "./router";

export type Loaded<T> = { data?: T; error?: string };

export function useLoad<T>(load: () => Promise<T>, deps: DependencyList): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({});
  useEffect(() => {
    let current = true;
    setState({});
    load().then((data) => current && setState({ data }))
      .catch((error: Error) => current && setState({ error: error.message }));
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function Waiting({ error }: { error?: string }) {
  return <p className={error ? "problem" : "note"} role="status">{error ?? "Loading…"}</p>;
}

export type Crumb = { label: string; to: Route };

export function PageHead({ crumbs = [], title, about, badges, children }:
  { crumbs?: Crumb[]; title: string; about?: string; badges?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      {crumbs.length > 0 && (
        <nav className="crumbs" aria-label="Where this is">
          {crumbs.map((crumb) => (
            <span key={crumb.label}><Link to={crumb.to}>{crumb.label}</Link><span className="sep">/</span></span>
          ))}
        </nav>
      )}
      <div className="title-row">
        <h2>{title}</h2>
        {badges}
      </div>
      {about && <p className="about">{about}</p>}
      {children}
    </div>
  );
}

// What a tool does, most consequential first: changes a type of record, writes, sends
// outside the organisation, or only reads
export type Risk = "changes" | "writes" | "outside" | "reads";

export function risk(tool: Tool): Risk {
  if (tool.changes || tool.destructive) return "changes";
  if (tool.sends_outside) return "outside";
  if (tool.writes) return "writes";
  return "reads";
}

export const RISK_NAMES: Record<Risk, string> = {
  changes: "Changes records", writes: "Writes", outside: "Sends outside", reads: "Reads",
};

export function ToolBadges({ tool }: { tool: Tool }) {
  return (
    <span className="badges">
      {tool.reads && <span className="badge reads">reads</span>}
      {tool.writes && !tool.changes && <span className="badge writes">writes</span>}
      {tool.changes && <span className="badge changes">changes {tool.changes}</span>}
      {tool.destructive && <span className="badge changes">destructive</span>}
      {tool.sends_outside && <span className="badge outside">sends outside</span>}
      {tool.outside.length > 0 && <span className="badge outside">reads outside content</span>}
      {tool.handles.length > 0 && <span className="badge">hands over {tool.handles.join(", ")}</span>}
      {tool.missing && <span className="badge bad">not in the scenario</span>}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "active" ? "good" : status === "suspended" ? "warn" : "";
  return <span className={`badge ${tone}`}><span className="dot" />{status}</span>;
}

export function outcomeTone(outcome: string): string {
  if (outcome === "done") return "good";
  if (["failed", "abandoned", "reply denied"].includes(outcome)) return "bad";
  return "warn";
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <span className={`badge ${outcomeTone(outcome)}`}>{outcome}</span>;
}

export function DecisionBadge({ decision }: { decision: string }) {
  const tone = decision === "allow" ? "good" : decision === "deny" ? "bad" : "warn";
  return <span className={`badge ${tone}`}>{decision}</span>;
}

/** What starts an agent's runs, as its release says: each kind, and what it says of it. */
export function triggers(agent: Agent): { kind: string; about: string }[] {
  return agent.triggers.flatMap((t) => Object.entries(t).map(([kind, about]) =>
    ({ kind, about: typeof about === "string" ? about : JSON.stringify(about) })));
}

// Words and numbers

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
export const people = (n: number) => plural(n, "person", "people");
export const share = (x: number | null | undefined) =>
  x === null || x === undefined ? "none yet" : `${Math.round(x * 100)}%`;

const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const TIME = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });
export const when = (at: string) => WHEN.format(new Date(at));
export const time = (at: string) => TIME.format(new Date(at));

export function levels(autonomy: { start: number; max: number }): string {
  return autonomy.start === autonomy.max ? `level ${autonomy.start}` : `levels ${autonomy.start}–${autonomy.max}`;
}

export function aboutInstance(inst: Instance): string {
  const parts = Object.keys(inst.parts).join(", ") || "no part";
  return `level ${inst.level} · ${parts} · serving ${people(inst.people)}`;
}

export function runners(inst: Instance): string {
  return [inst.owner, inst.deputy].filter(Boolean).join(" and ") || "nobody";
}
