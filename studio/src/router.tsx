// Where in the studio someone is, in its address, so links and the browser's back button work:
// their home, what they may do, all the agents, one agent, an instance's dashboard, a run, a
// new agent, a draft of one, the settings, the notebook, someone's tasks, the administrators'
// page, the audit trail, the changes to decide, the work to grade, the officer's requests, a
// version of the settings to approve, the map of what depends on what, a month's spending, the
// way back from connecting an account, a change to undo, the conversations handed to someone's
// teams, or the design system's showcase.

import { type MouseEvent, type ReactNode, useEffect, useState } from "react";

export type Route =
  | { page: "home" }
  | { page: "you" }
  | { page: "agents" }
  | { page: "agent"; agent: string }
  | { page: "instance"; instance: string }
  | { page: "run"; run: string }
  | { page: "new" }
  | { page: "draft"; draft: string }
  | { page: "settings"; search?: string }  // such as ?add=<agent>, an agent to put to work
  | { page: "notebook" }
  | { page: "tasks" }
  | { page: "admin" }
  | { page: "audit" }
  | { page: "decide" }
  | { page: "grade" }
  | { page: "officer" }
  | { page: "approve"; settings: string }  // the version, by its digest
  | { page: "map"; at?: string }  // and what's chosen on it, such as agent:assistant
  | { page: "spending"; month?: string }  // such as 2026-10, or this month
  | { page: "health" }  // each model's day, measured (core/health_api.py)
  | { page: "connections" }  // back from connecting an account, so agents act as them there
  | { page: "undo"; change: string }  // a change an agent made, to undo, by its id
  | { page: "handovers" }  // the conversations handed to someone's teams
  | { page: "handover"; id: string }  // one of them
  | { page: "shadows" }  // what new versions answered beside those at work, for graders
  | { page: "design" };

export function parse(path: string, search = ""): Route {
  const [, , kind, id] = path.split("/").map((part) => decodeURIComponent(part));
  if (kind === "agents" && id) return { page: "agent", agent: id };
  if (kind === "instances" && id) return { page: "instance", instance: id };
  if (kind === "runs" && id) return { page: "run", run: id };
  if (kind === "drafts" && id) return { page: "draft", draft: id };
  if (kind === "handovers" && id) return { page: "handover", id };
  if (kind === "handovers") return { page: "handovers" };
  if (kind === "shadows") return { page: "shadows" };
  if (kind === "new") return { page: "new" };
  if (kind === "agents") return { page: "agents" };
  if (kind === "you") return { page: "you" };
  if (kind === "design") return { page: "design" };
  if (kind === "settings") return search ? { page: "settings", search } : { page: "settings" };
  if (kind === "notebook") return { page: "notebook" };
  if (kind === "tasks") return { page: "tasks" };
  if (kind === "admin") return { page: "admin" };
  if (kind === "audit") return { page: "audit" };
  if (kind === "decide") return { page: "decide" };
  if (kind === "grade") return { page: "grade" };
  if (kind === "officer") return { page: "officer" };
  if (kind === "map") {
    const at = new URLSearchParams(search).get("at");
    return at ? { page: "map", at } : { page: "map" };
  }
  if (kind === "spending") {
    const month = new URLSearchParams(search).get("month");
    return month ? { page: "spending", month } : { page: "spending" };
  }
  if (kind === "health") return { page: "health" };
  if (kind === "connections") return { page: "connections" };
  if (kind === "undo") return { page: "undo", change: new URLSearchParams(search).get("change") ?? "" };
  if (kind === "approve") return { page: "approve", settings: new URLSearchParams(search).get("settings") ?? "" };
  return { page: "home" };
}

export function href(route: Route): string {
  switch (route.page) {
    case "agent": return `/studio/agents/${encodeURIComponent(route.agent)}`;
    case "instance": return `/studio/instances/${encodeURIComponent(route.instance)}`;
    case "run": return `/studio/runs/${encodeURIComponent(route.run)}`;
    case "draft": return `/studio/drafts/${encodeURIComponent(route.draft)}`;
    case "new": return "/studio/new";
    case "agents": return "/studio/agents";
    case "you": return "/studio/you";
    case "design": return "/studio/design";
    case "settings": return `/studio/settings${route.search ?? ""}`;
    case "notebook": return "/studio/notebook";
    case "tasks": return "/studio/tasks";
    case "admin": return "/studio/admin";
    case "audit": return "/studio/audit";
    case "decide": return "/studio/decide";
    case "grade": return "/studio/grade";
    case "officer": return "/studio/officer";
    case "map": return `/studio/map${route.at ? `?at=${encodeURIComponent(route.at)}` : ""}`;
    case "spending": return `/studio/spending${route.month ? `?month=${encodeURIComponent(route.month)}` : ""}`;
    case "approve": return `/studio/approve?settings=${encodeURIComponent(route.settings)}`;
    case "connections": return "/studio/connections";
    case "undo": return `/studio/undo?change=${encodeURIComponent(route.change)}`;
    case "handovers": return "/studio/handovers";
    case "handover": return `/studio/handovers/${encodeURIComponent(route.id)}`;
    case "shadows": return "/studio/shadows";
    default: return "/studio/";
  }
}

const listeners = new Set<() => void>();

/** Read the address again, as when signing in has put back where someone was going. */
export function reread(): void {
  listeners.forEach((then) => then());
}

let moved = false;  // went to another page within the studio: its heading takes the focus

/** Whether the studio has just gone to another page, once: its heading takes the keyboard's
 * focus, so a screen reader says where they are, as a page loaded afresh would (round 13, C7). */
export function justMoved(): boolean {
  const was = moved;
  moved = false;
  return was;
}

export function go(route: Route): void {
  history.pushState(null, "", href(route));
  moved = true;
  listeners.forEach((then) => then());
  window.scrollTo(0, 0);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(location.pathname, location.search));
  useEffect(() => {
    const back = () => {  // back or forward, as a link
      moved = true;
      setRoute(parse(location.pathname, location.search));
    };
    const reread = () => setRoute(parse(location.pathname, location.search));
    listeners.add(reread);
    window.addEventListener("popstate", back);
    return () => {
      listeners.delete(reread);
      window.removeEventListener("popstate", back);
    };
  }, []);
  return route;
}

export function Link({ to, className, children, label, id, title, current }:
  { to: Route; className?: string; children: ReactNode; label?: string; id?: string; title?: string;
    current?: boolean }) {
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    go(to);
  };
  return (
    <a href={href(to)} className={className} onClick={open} aria-label={label} id={id} title={title}
       aria-current={current ? "page" : undefined}>{children}</a>
  );
}

/** A page of the studio's, from an address such as a wait's, with what it asks for in plain
 * words, where the page keeps it, such as the version to approve: null for anywhere else, and
 * for a page that would lose what its address asks for, which opens as a page of its own. */
export function inside(address: string): Route | null {
  const [path, query] = address.split("?", 2);
  if (!/^\/studio\/[\w./-]*$/.test(path) || !/^[\w=&,.:@%+-]*$/.test(query ?? "")) return null;
  const route = parse(path, query ? `?${query}` : "");
  return !query || href(route) === address ? route : null;
}
