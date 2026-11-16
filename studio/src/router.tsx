// Where in the studio someone is, in its address, so links and the browser's back button work:
// their home, what they may do, all the agents, one agent, an instance's dashboard, a run, a
// new agent, a draft of one, the settings, the notebook, someone's tasks, the administrators'
// page, the audit trail, the changes to decide, or the design system's showcase.

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
  | { page: "design" };

export function parse(path: string): Route {
  const [, , kind, id] = path.split("/").map((part) => decodeURIComponent(part));
  if (kind === "agents" && id) return { page: "agent", agent: id };
  if (kind === "instances" && id) return { page: "instance", instance: id };
  if (kind === "runs" && id) return { page: "run", run: id };
  if (kind === "drafts" && id) return { page: "draft", draft: id };
  if (kind === "new") return { page: "new" };
  if (kind === "agents") return { page: "agents" };
  if (kind === "you") return { page: "you" };
  if (kind === "design") return { page: "design" };
  if (kind === "settings") return { page: "settings" };
  if (kind === "notebook") return { page: "notebook" };
  if (kind === "tasks") return { page: "tasks" };
  if (kind === "admin") return { page: "admin" };
  if (kind === "audit") return { page: "audit" };
  if (kind === "decide") return { page: "decide" };
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
    default: return "/studio/";
  }
}

const listeners = new Set<() => void>();

/** Read the address again, as when signing in has put back where someone was going. */
export function reread(): void {
  listeners.forEach((then) => then());
}

export function go(route: Route): void {
  history.pushState(null, "", href(route));
  listeners.forEach((then) => then());
  window.scrollTo(0, 0);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(location.pathname));
  useEffect(() => {
    const moved = () => setRoute(parse(location.pathname));
    listeners.add(moved);
    window.addEventListener("popstate", moved);
    return () => {
      listeners.delete(moved);
      window.removeEventListener("popstate", moved);
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

/** A page of the studio's, from an address such as a wait's: null for anywhere else. */
export function inside(path: string): Route | null {
  return /^\/studio\/[\w./-]*$/.test(path) ? parse(path) : null;
}
