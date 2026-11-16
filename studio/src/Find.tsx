// Finding anything in the studio by name, from any page (Ctrl-K, or ⌘K on a Mac, or the button at
// the top of the sidebar): what waits on the person first, then the pages they may use, then the
// agents and instances they may see and their drafts. Only what they may open is there to find:
// each comes from what the studio's API already shows them, read afresh each time it opens.

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { type Catalogue, get, type Home } from "./api";
import { Palette, type PaletteOption } from "./design/palette";
import { Icon } from "./icons";
import { go, inside, type Route } from "./router";
import { shellOf } from "./Sidebar";

type Found = PaletteOption & { to: Route | string };

// The pages, as the sidebar names them, and the studio's own besides
const PAGES: Record<string, [string, string, Route | string]> = {
  studio: ["Your home", "studio", { page: "home" }],
  chat: ["Chat", "chat", "/chat/"],
  tasks: ["Your tasks", "tasks", { page: "tasks" }],
  notebook: ["Notebook", "book", { page: "notebook" }],
  decide: ["Decisions", "decide", { page: "decide" }],
  grade: ["Grading", "grade", { page: "grade" }],
  settings: ["Settings", "settings", { page: "settings" }],
  audit: ["Audit trail", "audit", { page: "audit" }],
  admin: ["Administration", "admin", { page: "admin" }],
  officer: ["Data protection", "officer", { page: "officer" }],
};

async function everything(): Promise<Found[]> {
  const [shell, home, catalogue] = await Promise.all([
    shellOf(true).catch(() => null), get<Home>("/studio/api/home").catch(() => null),
    get<Catalogue>("/studio/api").catch(() => null)]);
  const found: Found[] = [];
  for (const [n, wait] of (home?.waiting ?? []).entries()) {
    const to = wait.go ? inside(wait.go) ?? wait.go : null;
    if (to) found.push({ id: `wait-${n}`, name: wait.what, where: "waits on you", group: "Waiting on you", icon: "bell", to });
  }
  for (const [page, [name, icon, to]] of Object.entries(PAGES)) {  // home first, then as the sidebar has them
    if (shell?.pages.includes(page)) found.push({ id: `page-${page}`, name, where: "a page", group: "Pages", icon, to });
  }
  if (catalogue) found.push({ id: "page-agents", name: "All agents", where: "a page", group: "Pages", icon: "agent", to: { page: "agents" } });
  if (home?.authoring) found.push({ id: "page-new", name: "Start a new agent", where: "in the studio", group: "Pages", icon: "plus", to: { page: "new" } });
  found.push({ id: "page-you", name: "What you may do", where: "a page", group: "Pages", icon: "people", to: { page: "you" } });
  for (const agent of catalogue?.agents ?? []) {
    found.push({ id: `agent-${agent.id}`, name: agent.id, where: "an agent", group: "Agents", icon: "agent", to: { page: "agent", agent: agent.id } });
  }
  for (const agent of catalogue?.agents ?? []) {
    for (const inst of agent.instances) {
      found.push({ id: `instance-${inst.id}`, name: inst.id, where: `an instance of the ${agent.id}`, group: "Instances",
                   icon: "run", to: { page: "instance", instance: inst.id } });
    }
  }
  for (const draft of home?.drafts ?? []) {
    found.push({ id: `draft-${draft.id}`, name: `The draft of ${draft.agent}`, where: draft.published ? "a draft, published" : "a draft",
                 group: "Drafts", icon: "studio", to: { page: "draft", draft: draft.id } });
  }
  return found;
}

/** What it found for the words typed: those whose name and what it is hold every word. */
function matching(found: Found[], query: string): Found[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return found.filter((f) => words.every((word) => `${f.name} ${f.where}`.toLowerCase().includes(word))).slice(0, 60);
}

const Opener = createContext<() => void>(() => {});

/** The button that opens it, where the sidebar keeps the way about. */
export function FindButton({ rail = false, id }: { rail?: boolean; id?: string }) {
  const open = useContext(Opener);
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  if (rail) {
    return <button type="button" className="palette-open" aria-label="Find anything" title="Find anything" onClick={open}><Icon name="find" /></button>;
  }
  return (
    <button type="button" className="palette-open" id={id} onClick={open}>
      <Icon name="find" /><span>Find anything</span><kbd>{mac ? "⌘" : "Ctrl"}</kbd><kbd>K</kbd>
    </button>
  );
}

/** The palette, for every page of the studio, once someone's signed in. */
export function Find({ ready, children }: { ready: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found[]>([]);
  const show = useCallback(() => {
    if (!ready) return;
    setQuery("");
    setOpen(true);
    everything().then(setFound).catch(() => setFound([]));
  }, [ready]);
  useEffect(() => {
    const keys = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        show();
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [show]);
  const options = useMemo(() => matching(found, query), [found, query]);
  const choose = (option: PaletteOption) => {
    const to = found.find((f) => f.id === option.id)?.to;
    setOpen(false);
    if (typeof to === "string") location.assign(to);
    else if (to) go(to);
  };
  return (
    <Opener.Provider value={show}>
      {children}
      {ready && <Palette open={open} onClose={() => setOpen(false)} query={query} onQuery={setQuery}
                         options={options} onChoose={choose} />}
    </Opener.Provider>
  );
}
