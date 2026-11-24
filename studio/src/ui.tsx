// What the studio's pages share: loading what a page shows, its heading with the way back, and
// the badges that say what a tool does, how something stands, and how a run ended.

import { locale, t } from "./i18n";
import { type DependencyList, type ReactNode, useEffect, useRef, useState } from "react";
import type { AgentUses, Instance, Tool, Waiting as Wait } from "./api";
import { Badge, type Tone } from "./design/controls";
import { Loading, Skeleton } from "./design/feedback";
import { levelName } from "./levels";
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
    document.title = t("{title} · a5s studio", { title });
  }, [title]);
  useEffect(() => {
    if (justMoved()) heading.current?.focus({ preventScroll: true });
  }, []);
  return (
    <div className="page-head">
      {crumbs.length > 0 && (
        <nav className="crumbs" aria-label={t("Where this is")}>
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

// Each in the language spoken when it's read, as are the other words kept below by what they name
export const RISK_NAMES: Record<Risk, string> = {
  get changes() { return t("Changes records"); }, get writes() { return t("Writes"); },
  get outside() { return t("Sends outside"); }, get reads() { return t("Reads"); },
};

export function ToolBadges({ tool }: { tool: Tool }) {
  return (
    <span className="badges">
      {tool.reads && <Badge tone="reads">{t("reads")}</Badge>}
      {tool.writes && !tool.changes && <Badge tone="writes">{t("writes")}</Badge>}
      {tool.changes && <Badge tone="changes">{t("changes {record}", { record: tool.changes })}</Badge>}
      {tool.destructive && <Badge tone="changes">{t("destructive")}</Badge>}
      {tool.sends_outside && <Badge tone="outside">{t("sends outside")}</Badge>}
      {(tool.outside.length > 0 || tool.marks) && <Badge tone="outside">{t("reads outside content")}</Badge>}
      {tool.handles.length > 0 && <Badge>{t("hands over {records}", { records: tool.handles.join(", ") })}</Badge>}
      {tool.missing && <Badge tone="bad">{t("not in the scenario")}</Badge>}
    </span>
  );
}

// An instance's status, in words: any other as a5s says it
const STATUSES: Record<string, string> = {
  get proposed() { return t("proposed"); }, get active() { return t("active"); },
  get suspended() { return t("suspended"); }, get retired() { return t("retired"); },
  get shadow() { return t("a shadow, answering beside another"); },
};

// The badges a page shows are Ocean's Badge, as the showcase shows it (pages/Design.tsx)
export function StatusBadge({ status }: { status: string }) {
  const tone = status === "active" ? "good" : status === "suspended" ? "warn" : undefined;
  return <Badge tone={tone} dot>{STATUSES[status] ?? status}</Badge>;
}

// How a run ends, as core/status.py's OUTCOMES says it: done; failed, in one of these ways;
// or else cut short, such as with its budget spent
export const FAILED_OUTCOMES: readonly string[] = ["failed", "abandoned", "reply denied"];

export function outcomeTone(outcome: string): Tone {
  if (outcome === "done") return "good";
  if (FAILED_OUTCOMES.includes(outcome)) return "bad";
  return "warn";
}

// Those outcomes in words, and the figures' open and other: any other as a5s says it
const OUTCOMES: Record<string, string> = {
  get done() { return t("done"); }, get "done, leaving some out"() { return t("done, leaving some out"); },
  get failed() { return t("failed"); }, get "reply denied"() { return t("reply denied"); },
  get "model unavailable"() { return t("model unavailable"); }, get "budget spent"() { return t("budget spent"); },
  get stopped() { return t("stopped"); }, get abandoned() { return t("abandoned"); },
  get open() { return t("open"); }, get other() { return t("other"); },
};

/** How a run ended, in words. */
export const outcomeName = (outcome: string): string => OUTCOMES[outcome] ?? outcome;

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <Badge tone={outcomeTone(outcome)}>{outcomeName(outcome)}</Badge>;
}

const DECISIONS: Record<string, string> = {
  get allow() { return t("allow"); }, get deny() { return t("deny"); }, get hold() { return t("hold"); },
};

export function DecisionBadge({ decision }: { decision: string }) {
  return <Badge tone={decision === "allow" ? "good" : decision === "deny" ? "bad" : "warn"}>{DECISIONS[decision] ?? decision}</Badge>;
}

/** What starts an agent's runs, as its release says: each kind, and what it says of it. */
export function triggers(agent: Pick<AgentUses, "triggers"> & Partial<Pick<AgentUses, "events">>):
  { kind: string; about: string }[] {
  return [...agent.triggers.flatMap((trigger) => Object.entries(trigger).map(([kind, about]) =>
    ({ kind, about: typeof about === "string" ? about : JSON.stringify(about) }))),
    // what other systems may tell it happened (core/events.py)
    ...(agent.events ?? []).map((e) => ({ kind: "event", about: t("{type} from {source}: {task}", { type: e.type, source: e.source, task: e.task }) }))];
}

// Words and numbers

/** An amount in the currency models.yaml prices models in, or a plain figure where it names none:
 * to the cent, or to two figures below a cent, so a cheap model's month isn't shown as nothing. */
export function money(n: number, currency: string | null | undefined): string {
  const digits: Intl.NumberFormatOptions = n !== 0 && Math.abs(n) < 0.01
    ? { maximumSignificantDigits: 2 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return currency ? n.toLocaleString(locale(), { style: "currency", currency, ...digits })
    : n.toLocaleString(locale(), digits);
}

/** Someone's initials, for their avatar, as a person's, never an agent's. */
export const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2)
  .map((w) => w[0].toUpperCase()).join("");

export const plural = (n: number, one: string, many = `${one}s`) =>
  `${n.toLocaleString(locale())} ${n === 1 ? one : many}`;
export const people = (n: number) => plural(n, "person", "people");
export const share = (x: number | null | undefined) =>
  x === null || x === undefined ? t("none yet") : `${Math.round(x * 100)}%`;

const formats = new Map<string, Intl.DateTimeFormat>();  // each style, once
/** Dates and times in a style of Intl's. */
export const format = (style: Intl.DateTimeFormatOptions) => {
  const key = JSON.stringify(style);
  let found = formats.get(key);
  if (!found) formats.set(key, found = new Intl.DateTimeFormat(locale(), style));
  return found;
};
export const when = (at: string) => format({ dateStyle: "medium", timeStyle: "short" }).format(new Date(at));
export const time = (at: string) => format({ timeStyle: "medium" }).format(new Date(at));

export function levels(autonomy: { start: number; max: number }): string {  // by name (levels.ts)
  return autonomy.start === autonomy.max ? levelName(autonomy.start)
    : t("{start}, at most {max}", { start: levelName(autonomy.start), max: levelName(autonomy.max) });
}

export function aboutInstance(inst: Instance): string {
  const parts = Object.keys(inst.parts).join(", ") || t("no part");
  return t("{level} · {parts} · serving {people}", { level: levelName(inst.level), parts, people: people(inst.people) });
}

/** Names one after another, as a sentence says them: "Ana and Ben and Cleo". */
export const together = (names: string[]): string =>
  names.length ? names.reduce((all, name) => t("{all} and {name}", { all, name })) : "";

export function runners(inst: Instance): string {
  return together([inst.owner, inst.deputy].filter((who): who is string => Boolean(who))) || t("nobody");
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
        {w.since && <span className="faint"> · {t("since {when}", { when: when(w.since) })}</span>}
        {w.how && <span className="faint"> · <span className="mono">{w.how}</span></span>}
        {w.why.length > 0 && <ul className="plain faint">{w.why.map((why) => <li key={why}>{why}</li>)}</ul>}
      </li>
    ))}</ul>
  );
}

/** After an act, where the keyboard goes next, once the page shows what the act changed (round
 * 14, E-L1): the first of these on the page, looked for until it's drawn, which takes the focus
 * as a control does, or as a heading or a note can, so the keyboard never falls back to the
 * page's start, where an act's button that's gone leaves it. */
export function focusNext(...selectors: string[]): void {
  let tries = 0;
  const look = () => {
    for (const selector of selectors) {
      const found = document.querySelector<HTMLElement>(selector);
      if (found) {
        if (!found.matches("a[href], button, input, select, textarea, [tabindex]")) found.tabIndex = -1;
        found.focus();
        return;
      }
    }
    if ((tries += 1) < 50) setTimeout(look, 100);
  };
  setTimeout(look, 0);
}

/** A canvas, or the same as a list: a page that draws something on a canvas, such as an agent's
 * designer or the map, shows it as a list on a narrow screen, where a canvas is too small to read
 * or to tap (round 14, E-L8), or as someone chose last on this browser. */
export type View = "canvas" | "list";
const NARROW = "(max-width: 56rem)";

export function useView(kept: string): [View, (v: View) => void] {
  const [shown, setShown] = useState<View>(() => {
    try {
      const was = window.localStorage.getItem(kept);
      if (was === "canvas" || was === "list") return was;
    } catch { /* a browser that keeps nothing starts afresh */ }
    return window.matchMedia?.(NARROW).matches ? "list" : "canvas";
  });
  return [shown, (v: View) => {
    setShown(v);
    try { window.localStorage.setItem(kept, v); } catch { /* as above */ }
  }];
}

/** Canvas or list, a choice of views, as Ocean's FlowList has it: `canvas` names the canvas. */
export function Views({ shown, show, canvas }: { shown: View; show: (v: View) => void; canvas: string }) {
  return (
    <div className="modes" role="group" aria-label={t("Show it")}>
      <button type="button" aria-pressed={shown === "canvas"} onClick={() => show("canvas")}>{canvas}</button>
      <button type="button" aria-pressed={shown === "list"} onClick={() => show("list")}>{t("List")}</button>
    </div>
  );
}
