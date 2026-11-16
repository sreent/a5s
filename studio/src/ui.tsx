// What the studio's pages share: loading what a page shows, its heading with the way back, and
// the badges that say what a tool does, how something stands, and how a run ended.

import { type DependencyList, type ReactNode, useEffect, useRef, useState } from "react";
import type { AgentUses, Instance, Tool, Waiting as Wait } from "./api";
import { Badge, type Tone } from "./design/controls";
import { Loading, Skeleton } from "./design/feedback";
import { inside, justMoved, Link, type Route } from "./router";

/** What a page shows, once loaded; while it loads again, as for another period, what it
 * showed before stays, `stale`, so nothing jumps. */
export type Loaded<T> = { data?: T; error?: string; stale?: boolean };

/** What a page shows, and `reload`, which reads it again after someone acts and settles once
 * it's shown, so the page says what they did only with it in sight. */
export function useLoad<T>(load: () => Promise<T>, deps: DependencyList): Loaded<T> & { reload: () => Promise<void> } {
  const [state, setState] = useState<Loaded<T>>({});
  useEffect(() => {
    let current = true;
    setState((was) => ({ data: was.data, stale: was.data !== undefined }));
    load().then((data) => current && setState({ data }))
      .catch((error: Error) => current && setState({ error: error.message }));
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  const reload = async () => setState({ data: await load() });
  return { ...state, reload };
}

/** Words a5s said, as a sentence: its first letter a capital, but for a5s's own name, which
 * Ocean no longer capitalises for every line (round 13, C10). */
export function sentence(said: string): string {
  return said.startsWith("a5s") ? said : said.charAt(0).toUpperCase() + said.slice(1);
}

/** A word with its article, as it's said: "an obligation", "a message" (round 13, C12). */
export function an(word: string): string {
  return `${/^[aeiou]/i.test(word) ? "An" : "A"} ${word}`;
}

/** While a page loads what it shows, its shape, still (Ocean's Skeleton): a card's, or, as
 * `children`, the page's own layout of Shapes, such as a grid of cards; or what went wrong. */
export function Waiting({ error, lines, title, rows, block, children }:
  { error?: string; lines?: number; title?: boolean; rows?: number; block?: boolean; children?: ReactNode }) {
  return error ? <p className="problem" role="status">{sentence(error)}</p>
    : children ? <Loading>{children}</Loading>
    : <Skeleton lines={lines} title={title} rows={rows} block={block} />;
}

/** A table wider than its place scrolls sideways in its own frame, which the keyboard reaches,
 * as Ocean's figures-scroll does, not the whole page, as it did on a phone (round 13, C5). */
export function Wide({ label, children }: { label: string; children: ReactNode }) {
  return <div className="figures-scroll" tabIndex={0} role="region" aria-label={label}>{children}</div>;
}

export type Crumb = { label: string; to: Route };

export function PageHead({ crumbs = [], title, about, badges, children }:
  { crumbs?: Crumb[]; title: string; about?: string; badges?: ReactNode; children?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {  // each page its own title, for the tab, history and screen readers (round 13, C7)
    document.title = `${title} · a5s studio`;
  }, [title]);
  useEffect(() => {
    if (justMoved()) heading.current?.focus({ preventScroll: true });
  }, []);
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
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
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
      {tool.reads && <Badge tone="reads">reads</Badge>}
      {tool.writes && !tool.changes && <Badge tone="writes">writes</Badge>}
      {tool.changes && <Badge tone="changes">changes {tool.changes}</Badge>}
      {tool.destructive && <Badge tone="changes">destructive</Badge>}
      {tool.sends_outside && <Badge tone="outside">sends outside</Badge>}
      {tool.outside.length > 0 && <Badge tone="outside">reads outside content</Badge>}
      {tool.handles.length > 0 && <Badge>hands over {tool.handles.join(", ")}</Badge>}
      {tool.missing && <Badge tone="bad">not in the scenario</Badge>}
    </span>
  );
}

// The badges a page shows are Ocean's Badge, as the showcase shows it (pages/Design.tsx)
export function StatusBadge({ status }: { status: string }) {
  const tone = status === "active" ? "good" : status === "suspended" ? "warn" : undefined;
  return <Badge tone={tone} dot>{status}</Badge>;
}

// How a run ends, as core/status.py's OUTCOMES says it: done; failed, in one of these ways;
// or else cut short, such as with its budget spent
export const FAILED_OUTCOMES: readonly string[] = ["failed", "abandoned", "reply denied"];

export function outcomeTone(outcome: string): Tone {
  if (outcome === "done") return "good";
  if (FAILED_OUTCOMES.includes(outcome)) return "bad";
  return "warn";
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <Badge tone={outcomeTone(outcome)}>{outcome}</Badge>;
}

export function DecisionBadge({ decision }: { decision: string }) {
  return <Badge tone={decision === "allow" ? "good" : decision === "deny" ? "bad" : "warn"}>{decision}</Badge>;
}

/** What starts an agent's runs, as its release says: each kind, and what it says of it. */
export function triggers(agent: Pick<AgentUses, "triggers"> & Partial<Pick<AgentUses, "events">>):
  { kind: string; about: string }[] {
  return [...agent.triggers.flatMap((t) => Object.entries(t).map(([kind, about]) =>
    ({ kind, about: typeof about === "string" ? about : JSON.stringify(about) }))),
    // what other systems may tell it happened (core/events.py)
    ...(agent.events ?? []).map((e) => ({ kind: "event", about: `${e.type} from ${e.source}: ${e.task}` }))];
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

/** A way to where something's done: within the studio, without leaving it, or a page of its own. */
export function To({ go, children }: { go: string; children: ReactNode }) {
  const route = inside(go);
  return route ? <Link to={route}>{children}</Link> : <a href={go}>{children}</a>;
}

/** What waits for someone, each where they do it, on its own page or at the command line,
 * with why it's theirs and since when, as the home and an instance's page list it. */
export function WaitList({ waiting, none }: { waiting: Wait[]; none: string }) {
  if (waiting.length === 0) return <p className="note">{none}</p>;
  return (
    <ul className="waits">{waiting.map((w) => (
      <li key={`${w.kind}:${w.what}`} className={`wait wait-${w.kind}`}>
        {w.go ? <To go={w.go}>{w.what}</To> : <span>{w.what}</span>}
        {w.since && <span className="faint"> · since {when(w.since)}</span>}
        {w.how && <span className="faint"> · <span className="mono">{w.how}</span></span>}
        {w.why.length > 0 && <ul className="plain faint">{w.why.map((why) => <li key={why}>{why}</li>)}</ul>}
      </li>
    ))}</ul>
  );
}
