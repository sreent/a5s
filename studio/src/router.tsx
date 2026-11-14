// Where in the studio someone is, in its address, so links and the browser's back button work:
// all the agents, one agent, an instance's dashboard, a run, a new agent, or a draft of one.

import { type MouseEvent, type ReactNode, useEffect, useState } from "react";

export type Route =
  | { page: "agents" }
  | { page: "agent"; agent: string }
  | { page: "instance"; instance: string }
  | { page: "run"; run: string }
  | { page: "new" }
  | { page: "draft"; draft: string };

export function parse(path: string): Route {
  const [, , kind, id] = path.split("/").map((part) => decodeURIComponent(part));
  if (kind === "agents" && id) return { page: "agent", agent: id };
  if (kind === "instances" && id) return { page: "instance", instance: id };
  if (kind === "runs" && id) return { page: "run", run: id };
  if (kind === "drafts" && id) return { page: "draft", draft: id };
  if (kind === "new") return { page: "new" };
  return { page: "agents" };
}

export function href(route: Route): string {
  switch (route.page) {
    case "agent": return `/studio/agents/${encodeURIComponent(route.agent)}`;
    case "instance": return `/studio/instances/${encodeURIComponent(route.instance)}`;
    case "run": return `/studio/runs/${encodeURIComponent(route.run)}`;
    case "draft": return `/studio/drafts/${encodeURIComponent(route.draft)}`;
    case "new": return "/studio/new";
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

export function Link({ to, className, children, label }:
  { to: Route; className?: string; children: ReactNode; label?: string }) {
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    go(to);
  };
  return <a href={href(to)} className={className} onClick={open} aria-label={label}>{children}</a>;
}
