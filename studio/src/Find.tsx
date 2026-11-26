// Finding anything in the studio by name, from any page (Ctrl-K, or ⌘K on a Mac, or the button at
// the top of the sidebar): what waits on the person first, then the pages they may use, then the
// agents and instances they may see and their drafts. Only what they may open is there to find:
// each comes from what the studio's API already shows them, read afresh each time it opens.

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { type Catalogue, get, type Home } from "./api";
import { Palette, type PaletteOption } from "./design/palette";
import { t } from "./i18n";
import { Icon } from "./icons";
import { go, inside, type Route } from "./router";
import { shellOf } from "./Sidebar";

type Found = PaletteOption & { to: Route | string };

async function everything(): Promise<Found[]> {
  const [shell, home, catalogue] = await Promise.all([
    shellOf(true).catch(() => null), get<Home>("/studio/api/home").catch(() => null),
    get<Catalogue>("/studio/api").catch(() => null)]);
  const found: Found[] = [];
  for (const [n, wait] of (home?.waiting ?? []).entries()) {
    const to = wait.go ? inside(wait.go) ?? wait.go : null;
    if (to) found.push({ id: `wait-${n}`, name: wait.what, where: t("waits on you"), group: t("Waiting on you"), icon: "bell", to });
  }
  for (const place of shell?.pages ?? []) {  // as the sidebar names and orders them
    found.push({ id: `page-${place.page}`, name: place.name, where: t("a page"), group: t("Pages"), icon: place.icon,
                 to: inside(place.at) ?? place.at });
  }
  found.push({ id: "page-you", name: t("What you may do"), where: t("a page"), group: t("Pages"), icon: "people", to: { page: "you" } });
  for (const agent of catalogue?.agents ?? []) {
    found.push({ id: `agent-${agent.id}`, name: agent.id, where: t("an agent"), group: t("Agents"), icon: "agent", to: { page: "agent", agent: agent.id } });
  }
  for (const agent of catalogue?.agents ?? []) {
    for (const inst of agent.instances) {
      found.push({ id: `instance-${inst.id}`, name: inst.id, where: t("an instance of the {agent}", { agent: agent.id }), group: t("Instances"),
                   icon: "run", to: { page: "instance", instance: inst.id } });
    }
  }
  for (const draft of home?.drafts ?? []) {
    found.push({ id: `draft-${draft.id}`, name: `The draft of ${draft.agent}`, where: draft.published ? "a draft, published" : "a draft",
                 group: t("Drafts"), icon: "studio", to: { page: "draft", draft: draft.id } });
  }
  // each once, as the palette keys its rows by id: two of one id left rows behind as it
  // narrowed, and marked two chosen (round 17, C1)
  const seen = new Set<string>();
  return found.filter((f) => !seen.has(f.id) && Boolean(seen.add(f.id)));
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
    return <button type="button" className="palette-open" aria-label={t("Find anything")} title={t("Find anything")} onClick={open}><Icon name="find" /></button>;
  }
  return (
    <button type="button" className="palette-open" id={id} onClick={open}>
      <Icon name="find" /><span>{t("Find anything")}</span><kbd>{mac ? "⌘" : "Ctrl"}</kbd><kbd>K</kbd>
    </button>
  );
}

/** The palette, for every page of the studio, once someone's signed in. */
export function Find({ ready, children }: { ready: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found[]>([]);
  const [looked, setLooked] = useState(false);  // found what there is at least once
  const look = useCallback(() => everything().then(setFound).catch(() => setFound([]))
    .finally(() => setLooked(true)), []);
  useEffect(() => {  // what there is, found as the studio opens, so it's there at Ctrl-K (round 13, C9)
    if (ready) void look();
  }, [ready, look]);
  const show = useCallback(() => {
    if (!ready) return;
    setQuery("");
    setOpen(true);
    void look();  // afresh each time it opens, what it found before shown meanwhile
  }, [ready, look]);
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
                         options={options} onChoose={choose} looking={!looked} />}
    </Opener.Provider>
  );
}
