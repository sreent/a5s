// A draft of an agent, as its author edits it: what it works for and does, its model and levels,
// its tools from the scenario's, each by what it does, its instructions, and any of its files as
// text. Each change is kept a moment after it's made, its tools pinned by a5s, and what would
// stop its release said beside the map of how it's wired, as both stand now.

import { useEffect, useRef, useState } from "react";
import { AgentMap } from "../AgentMap";
import { type CoAuthors, type Draft, get, type Offer, type Offered, type Sandbox, send } from "../api";
import { CASES, keptCases, read, Unreadable, withCase, withTool, withValue } from "../definition";
import { JourneyPath, type Stage } from "../design";
import { Publish } from "../Publish";
import { go, Link } from "../router";
import { TryIt } from "../TryIt";
import { PageHead, type Risk, risk, RISK_NAMES, ToolBadges, useLoad, Waiting, when } from "../ui";

type Files = Record<string, string>;
type Tab = "basics" | "tools" | "instructions" | "files";
const TABS: [Tab, string][] = [["basics", "Basics"], ["tools", "Tools"], ["instructions", "Instructions"], ["files", "Files"]];
const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];
const WAIT = 600;  // ms after the last change before it's kept

type Kept = "kept" | "keeping" | { problem: string };

function Basics({ files, models, change }: { files: Files; models: string[]; change: (f: Files) => void }) {
  const spec = read(files["agent.yaml"] ?? "");
  if (!spec) return <p className="problem">{new Unreadable().message}</p>;
  const set = (path: string[], value: string | number) =>
    change({ ...files, "agent.yaml": withValue(files["agent.yaml"], path, value) });
  return (
    <div className="form-grid">
      <label className="field"><span>Works for</span>
        <input id="works-for" value={spec.works_for} onChange={(e) => set(["works_for"], e.target.value)} /></label>
      <label className="field"><span>What it does</span>
        <textarea id="does" rows={4} value={spec.does} onChange={(e) => set(["does"], e.target.value)} /></label>
      <label className="field"><span>Model, of those the deployment approves</span>
        <select id="model" value={spec.model} onChange={(e) => set(["model"], e.target.value)}>
          {[...new Set([spec.model, ...models])].map((m) => <option key={m} value={m}>{m}</option>)}
        </select></label>
      <div className="field-pair">
        {(["start", "max"] as const).map((end) => (
          <label key={end} className="field"><span>{end === "start" ? "Level it starts at" : "Highest level"}</span>
            <select id={`level-${end}`} value={spec.autonomy[end]}
                    onChange={(e) => set(["autonomy", end], Number(e.target.value))}>
              {[0, 1, 2].map((n) => <option key={n} value={n}>{n}</option>)}
            </select></label>
        ))}
      </div>
    </div>
  );
}

function Tools({ files, offered, change }: { files: Files; offered: Offered[]; change: (f: Files) => void }) {
  const spec = read(files["agent.yaml"] ?? "");
  if (!spec) return <p className="problem">{new Unreadable().message}</p>;
  const has = new Set(Object.values(spec.tools).flat());
  const kinds = new Map(offered.map((t) => [t.name, risk({ ...t, group: "", pinned: null, missing: false })]));
  const kindOf = (name: string) => kinds.get(name) ?? "reads";
  const flip = (tool: Offered, on: boolean) =>
    change({ ...files, "agent.yaml": withTool(files["agent.yaml"], tool.name, on, kindOf(tool.name), kindOf) });
  return (
    <div className="tool-picker">
      {ORDER.map((kind) => {
        const these = offered.filter((t) => kindOf(t.name) === kind);
        if (!these.length) return null;
        return (
          <div key={kind} className="tool-group">
            <div className={`label tone-${kind}`}>{RISK_NAMES[kind]}</div>
            {these.map((tool) => (
              <label key={tool.name} className="tool-row pick">
                <input type="checkbox" checked={has.has(tool.name)} onChange={(e) => flip(tool, e.target.checked)}
                       aria-label={tool.name} />
                <span>
                  <span className="tool-name mono">{tool.name}</span>
                  {tool.description && <span className="tool-about">{tool.description}</span>}
                  <ToolBadges tool={{ ...tool, group: "", pinned: null, missing: false }} />
                </span>
              </label>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function Raw({ files, change, readOnly = false }: { files: Files; change: (f: Files) => void; readOnly?: boolean }) {
  const names = Object.keys(files).sort();
  const [open, setOpen] = useState(names.includes("agent.yaml") ? "agent.yaml" : names[0]);
  const pinned = open === "tools.lock";
  return (
    <div className="raw">
      <ul className="file-list" aria-label="Its files">
        {names.map((name) => (
          <li key={name}><button type="button" className={name === open ? "on" : ""} onClick={() => setOpen(name)}>{name}</button></li>
        ))}
      </ul>
      <div className="raw-file">
        {pinned && <p className="note">a5s pins its tools as the scenario has them each time it's kept, as `a5s pin` does.</p>}
        <textarea id="file-text" aria-label={open} spellCheck={false} readOnly={pinned || readOnly} value={files[open] ?? ""}
                  onChange={(e) => change({ ...files, [open]: e.target.value })} />
      </div>
    </div>
  );
}

/** A co-author's draft, read only: what would stop its release, who'd sign it, its map and its
 * files, and a copy of it into a draft of one's own, to change it. */
function TheirDraft({ draft }: { draft: Draft }) {
  const [problem, setProblem] = useState<string | null>(null);
  const copy = async () => {
    try {
      const made = await send<Draft>("POST", "/studio/api/drafts", { copy_of: draft.id });
      go({ page: "draft", draft: made.id });
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } }]} title={draft.agent}
                badges={<><span className="chip">draft</span> <span className="chip">read only</span></>}
                about={`${draft.author}'s draft, from ${draft.based_on}, kept ${when(draft.updated_at)}. You may author the ${draft.agent} too, so you may read it: copy it into a draft of your own to change it.`}>
        <div className="meta"><button type="button" className="primary" id="copy-draft" onClick={copy}>Make a copy of your own</button></div>
      </PageHead>
      {problem && <p className="problem">{problem}</p>}
      <section className={`card ${draft.problems.length ? "" : "ready"}`} id="problems">
        {draft.problems.length === 0
          ? <p><span className="badge good">ready</span> Nothing would stop its release here, by the checks <span className="mono">a5s agent check</span> makes.</p>
          : <><h2>What would stop its release</h2><ul className="plain">{draft.problems.map((p) => <li key={p}>{p}</li>)}</ul></>}
      </section>
      <section className="card map-card">
        <h2>How it's wired</h2>
        {draft.preview ? <AgentMap agent={draft.preview} /> : <p className="note">Its map shows once its definition loads.</p>}
      </section>
      <section className="card editor" id="their-files">
        <h2>Its files</h2>
        <Raw files={draft.files} change={() => undefined} readOnly />
      </section>
    </>
  );
}

/** Who drafted it before its author, as its pull request names them: never as if it were all
 * theirs (round 11, E-4). */
function handedBy(draft: Draft): string {
  const went = draft.drafted_before.map((d) => d.how === "handed"
    ? `${d.name} handed it over ${when(d.at)}` : `it copies a draft ${d.name} wrote`);
  return went.length ? ` Before you, ${went.join("; then ")}.` : "";
}

/** Hand one's own draft over to a co-author, who may author its agent too: it's theirs then. */
function HandOver({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const people = useLoad(() => (open ? get<CoAuthors>(
    `/studio/api/drafts/${encodeURIComponent(id)}/co-authors`) : Promise.resolve({ people: [] })), [open, id]);
  if (!open) return <button type="button" className="quiet" id="hand-over" onClick={() => setOpen(true)}>Hand it over</button>;
  const found = people.data?.people ?? [];
  const hand = async () => {
    try {
      await send("POST", `/studio/api/drafts/${encodeURIComponent(id)}/hand-over`, { to: to || found[0]?.id });
      go({ page: "agents" });
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  return (
    <span className="hand-over">
      {people.data && found.length === 0 && <span className="faint">Nobody else may take it: they may author its agent, and have no draft of it.</span>}
      {found.length > 0 && (
        <>
          <select id="hand-to" value={to || found[0].id} onChange={(e) => setTo(e.target.value)} aria-label="Hand it over to">
            {found.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button type="button" className="primary" id="hand-over-to" onClick={hand}>Hand it over to them</button>
        </>
      )}
      <button type="button" className="quiet" onClick={() => setOpen(false)}>Keep it</button>
      {problem && <span className="problem"> {problem}</span>}
    </span>
  );
}

const named = (them: string[]) => them.length > 1 ? `${them.slice(0, -1).join(", ")} and ${them[them.length - 1]}` : them[0];

type Said = Pick<Draft, "problems" | "preview" | "signers" | "released" | "at_work">;

/** Where a draft stands on its way to work, and the one thing to do next: shape it and try it,
 * publish it, have its release signed, which a5s then deploys, put it to work, and watch it.
 * Once the release here holds it as it is, the rest follows its agent: at work or not yet. */
function Journey({ draft, said, files }: { draft: Draft; said: Said; files: Files }) {
  const sandbox = useLoad(() => get<Sandbox>("/studio/api/sandbox"), []);
  const shaped = said.problems.length === 0;
  const cases = keptCases(files[CASES]);
  const { released, at_work: atWork } = said;
  const published = Boolean(draft.published) || released;
  const untried = !cases && !sandbox.error && !published;  // a sandbox to try it in, before it's out
  const signers = [...new Set((said.signers ?? []).map((s) => s.who))];
  const stages: Stage[] = [
    { name: "Shape and try it", state: released || (shaped && !untried) ? "done" : "now",
      about: !shaped ? `${said.problems.length === 1 ? "One thing stops" : `${said.problems.length} things stop`} its release.`
        : cases ? `Nothing stops its release, and ${cases} test case${cases === 1 ? "" : "s"} kept from the sandbox.`
        : untried ? "Nothing stops its release. Try it in the sandbox, and keep what it should do as test cases."
        : sandbox.error ? "Nothing stops its release. There's no sandbox here to try it in." : "Nothing stops its release." },
    { name: "Publish it", state: published ? "done" : shaped && !untried ? "now" : "later",
      about: draft.publishing ? "As a pull request, which a5s opens as you." : "As a pull request, which you open with the words a5s gives." },
    { name: "Have its release signed", state: released ? "done" : published ? "now" : "later",
      about: released ? "It's released here as it is, and a5s deployed it."
        : `By ${signers.length ? named(signers) : "whoever its release needs"}. a5s deploys it once they have.` },
    { name: "Put it to work", state: released && atWork ? "done" : released ? "now" : "later",
      about: released && atWork ? "An instance runs it." : "An instance in the settings, for a few people first, at level 0 or 1." },
    { name: "Watch it", state: released && atWork ? "now" : "later", about: "Its runs and how they end, on its page." },
  ];
  const to = (section: string) => () => {
    const at = document.getElementById(section);
    at?.scrollIntoView({ behavior: "smooth", block: "start" });
    at?.focus({ preventScroll: true });
  };
  const page = { page: "agent" as const, agent: draft.agent };
  const next = released
    ? <Link to={page} className="button primary">{atWork ? "Watch it on its page" : "Put it to work, from its page"}</Link>
    : !shaped
    ? <button type="button" className="primary" onClick={to("problems")}>See what stops its release</button>
    : draft.published
      ? <a className="button primary" href={draft.published ?? "#"} target="_blank" rel="noopener noreferrer">Open its pull request</a>
      : untried
        ? <><button type="button" className="primary" onClick={to("try")}>Try it in the sandbox</button>
            <button type="button" className="quiet" onClick={to("publishing")}>Publish it without trying it</button></>
        : <button type="button" className="primary" onClick={to("publishing")}>Publish it</button>;
  return (
    <section className="card" id="journey" aria-labelledby="journey-title">
      <h2 id="journey-title" className="hidden">Where it stands</h2>
      <JourneyPath stages={stages} next={next} />
    </section>
  );
}

export function DraftPage({ id }: { id: string }) {
  const loaded = useLoad(() => get<Draft>(`/studio/api/drafts/${encodeURIComponent(id)}`), [id]);
  const tools = useLoad(() => get<Offer>("/studio/api/tools"), []);
  const [files, setFiles] = useState<Files | null>(null);
  const [said, setSaid] = useState<Said | null>(null);
  const [kept, setKept] = useState<Kept>("kept");
  const [revision, setRevision] = useState(0);  // each time a change is kept
  const [tab, setTab] = useState<Tab>("basics");
  const latest = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (loaded.data && files === null) {
      setFiles(loaded.data.files);
      const { problems, preview, signers, released, at_work } = loaded.data;
      setSaid({ problems, preview, signers, released, at_work });
    }
  }, [loaded.data, files]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const keep = async (next: Files, mine: number) => {
    try {
      const saved = await send<Draft>("PUT", `/studio/api/drafts/${encodeURIComponent(id)}`, { files: next });
      if (mine !== latest.current) return;  // a later change is on its way
      const { problems, preview, signers, released, at_work } = saved;
      setSaid({ problems, preview, signers, released, at_work });
      setFiles((now) => {  // a5s's pins, beside what they've typed since
        if (!now) return now;
        const { ["tools.lock"]: _old, ...rest } = now;
        return saved.files["tools.lock"] === undefined ? rest : { ...rest, "tools.lock": saved.files["tools.lock"] };
      });
      setKept("kept");
      setRevision((n) => n + 1);
    } catch (e) {
      if (mine === latest.current) setKept({ problem: (e as Error).message });
    }
  };
  const change = (next: Files) => {
    setFiles(next);
    setKept("keeping");
    const mine = ++latest.current;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => keep(next, mine), WAIT);
  };
  const edit = (make: () => Files) => {
    try {
      change(make());
    } catch (e) {
      setKept({ problem: (e as Error).message });
    }
  };
  const drop = async () => {
    if (!window.confirm("Drop this draft? It can't be had back.")) return;
    await send("DELETE", `/studio/api/drafts/${encodeURIComponent(id)}`);
    go({ page: "agents" });
  };

  const draft = loaded.data;
  if (draft && !draft.yours) return <TheirDraft draft={draft} />;
  const status = typeof kept === "object" ? <span className="badge bad">{kept.problem}</span>
    : kept === "keeping" ? <span className="badge">keeping…</span> : <span className="badge good">kept</span>;
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } }]} title={draft ? draft.agent : "A draft"}
                badges={draft && <span className="chip">draft</span>}
                about={draft && `From ${draft.based_on}, started ${when(draft.created_at)}.${handedBy(draft)} Yours to change, and readable by the agent's other owners and authors: nothing runs it until it's published and its release signed.`}>
        {draft && <div className="meta"><span id="kept">{status}</span>
          <HandOver id={id} />
          <button type="button" className="quiet" onClick={drop}>Drop the draft</button></div>}
      </PageHead>
      {(!draft || !files || !said) && <Waiting error={loaded.error} />}
      {draft && files && said && (
        <>
          <Journey draft={draft} said={said} files={files} />
          <section className={`card ${said.problems.length ? "" : "ready"}`} id="problems" aria-live="polite" tabIndex={-1}>
            {said.problems.length === 0
              ? <p><span className="badge good">ready</span> Nothing would stop its release here, by the checks <span className="mono">a5s agent check</span> makes.</p>
              : <><h2>What would stop its release</h2><ul className="plain">{said.problems.map((p) => <li key={p}>{p}</li>)}</ul></>}
          </section>
          <section className="card" id="signers">
            <h2>Who would sign its release</h2>
            {said.signers === null && <p className="note">Once its definition loads.</p>}
            {said.signers?.length === 0 && <p className="note">Nobody yet: it changes nothing of what's released here.</p>}
            {said.signers && said.signers.length > 0 && (
              <ul className="plain">{said.signers.map((s) => (
                <li key={s.role}><strong>{s.who}</strong><span className="faint">, because {s.why}</span></li>
              ))}</ul>
            )}
            <p className="note">As <span className="mono">a5s release</span> works it out, from what it changes of the agents released here. The pull request it's published as names them.</p>
          </section>
          <section className="card map-card">
            <h2>How it's wired</h2>
            {said.preview ? <AgentMap agent={said.preview} /> : <p className="note">Its map shows once its definition loads.</p>}
          </section>
          <section className="card editor">
            <div className="tabs" role="tablist">
              {TABS.map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""}
                        onClick={() => setTab(key)}>{label}</button>
              ))}
            </div>
            {tab === "basics" && <Basics files={files} models={tools.data?.models ?? []} change={(f) => edit(() => f)} />}
            {tab === "tools" && (tools.data ? <Tools files={files} offered={tools.data.tools} change={(f) => edit(() => f)} />
                                            : <Waiting error={tools.error} />)}
            {tab === "instructions" && (
              <label className="field"><span>What it's told at the start of each run, its AGENTS.md</span>
                <textarea id="instructions" rows={18} value={files["AGENTS.md"] ?? ""}
                          onChange={(e) => change({ ...files, "AGENTS.md": e.target.value })} /></label>
            )}
            {tab === "files" && <Raw files={files} change={change} />}
          </section>
          <section className="card" id="try" tabIndex={-1}>
            <h2>Try it in the sandbox</h2>
            <TryIt draft={id} name={draft.agent} ready={said.problems.length === 0 && kept === "kept"}
                   keep={(testCase) => change({ ...files, [CASES]: withCase(files[CASES] ?? "", testCase) })}
                   revision={revision} />
          </section>
          <section className="card" id="publishing" tabIndex={-1}>
            <h2>Publish it</h2>
            <Publish draft={id} name={draft.agent} ready={said.problems.length === 0 && kept === "kept"}
                     published={draft.published} publishing={draft.publishing} revision={revision} />
          </section>
        </>
      )}
    </>
  );
}
