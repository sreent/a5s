// A draft of an agent, on the workbench (Ocean's Workbench): the whole window given to the work,
// a toolbar that says which agent this is, whether what's been done is kept, what would stop its
// release, its views and its one thing to do, Publish it. Its first view is the designer, where
// the agent is built by hand on its canvas (Designer.tsx); the others are its instructions, the
// sandbox to try it in, and its files as text, which a change in any of them keeps in step. Each
// change is kept a moment after it's made, its tools pinned by a5s, and what would stop its
// release said as it stands.

import { type ReactNode, useEffect, useRef, useState } from "react";
import { AgentMap } from "../AgentMap";
import { type CoAuthors, type Draft, get, type Offer, type Plan, type Sandbox, send, whole } from "../api";
import { CASES, keptCases, withCase } from "../definition";
import { JourneyPath, type Stage } from "../design";
import { Designer } from "../Designer";
import { Icon } from "../icons";
import { Publish } from "../Publish";
import { go, Link } from "../router";
import { shellOf } from "../Sidebar";
import { TryIt } from "../TryIt";
import { useLoad, Waiting, when } from "../ui";

type Files = Record<string, string>;
type View = "design" | "instructions" | "try" | "files" | "publish";
const VIEWS: [View, string][] = [["design", "Design"], ["instructions", "Instructions"], ["try", "Try it"], ["files", "Files"]];
const WAIT = 600;  // ms after the last change before it's kept

type Kept = "kept" | "keeping" | { problem: string };
type Said = Pick<Draft, "problems" | "preview" | "signers" | "released" | "at_work">;

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

/** What would stop its release, as a5s's checks say it now. */
function Problems({ problems }: { problems: string[] }) {
  return (
    <section className={`gates ${problems.length ? "" : "ready"}`} id="problems" aria-live="polite" tabIndex={-1}
             aria-labelledby="problems-title">
      <h2 id="problems-title">What stops its release</h2>
      {problems.length === 0
        ? <p><span className="badge good"><Icon name="check" />ready</span> Nothing would stop its release here, by the checks <span className="mono">a5s agent check</span> makes.</p>
        : <ul className="plain">{problems.map((p) => <li key={p}><span className="badge bad"><Icon name="cross" />stops it</span> {p}</li>)}</ul>}
    </section>
  );
}

/** A co-author's draft, read only: what would stop its release, how it's wired, its files, and a
 * copy of it into a draft of one's own, to change it. */
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
      <header className="wb-bar">
        <Link to={{ page: "agents" }} className="crumb"><Icon name="back" />Agents</Link>
        <h1>{draft.agent}</h1>
        <span className="chip">draft</span> <span className="chip">read only</span>
        <span className="wb-spacer" />
        <button type="button" className="primary" id="copy-draft" onClick={copy}>Make a copy of your own</button>
      </header>
      <div className="wb-body whole">
        <div className="wb-view">
          <p className="note">{draft.author}'s draft, from {draft.based_on}, kept {when(draft.updated_at)}. You may author
            the {draft.agent} too, so you may read it: copy it into a draft of your own to change it.</p>
          {problem && <p className="problem">{problem}</p>}
          <Problems problems={draft.problems} />
          <section aria-labelledby="their-map"><h2 id="their-map">How it's wired</h2>
            {draft.preview ? <AgentMap agent={draft.preview} /> : <p className="note">Its map shows once its definition loads.</p>}</section>
          <section id="their-files" aria-labelledby="their-files-title"><h2 id="their-files-title">Its files</h2>
            <Raw files={draft.files} change={() => undefined} readOnly /></section>
        </div>
      </div>
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
          <button type="button" id="hand-over-to" onClick={hand}>Hand it over to them</button>
        </>
      )}
      <button type="button" className="quiet" onClick={() => setOpen(false)}>Keep it</button>
      {problem && <span className="problem"> {problem}</span>}
    </span>
  );
}

const named = (them: string[]) => them.length > 1 ? `${them.slice(0, -1).join(", ")} and ${them[them.length - 1]}` : them[0];

/** Where a draft stands on its way to work, and the one thing to do next: shape it and try it,
 * publish it, have its release signed, which a5s then deploys, put it to work, and watch it.
 * Once the release here holds it as it is, the rest follows its agent: at work or not yet. */
/** Where to put a released agent to work: with a plan for its first instance, the settings app's
 * form, starting from it, for those who may use it; else its page, which says how, or how to ask
 * for it. */
function toWork(agent: string, plan: Plan, settles: boolean): { href: string } | null {
  if (!settles || !(plan.parts.length || plan.serves.length || plan.asks.length)) return null;
  const listed = (key: keyof Plan) => (plan[key]?.length ? `&${key}=${plan[key].map(encodeURIComponent).join(",")}` : "");
  return { href: `/settings/?add=${encodeURIComponent(agent)}${listed("parts")}${listed("serves")}${listed("asks")}` };
}

function Journey({ draft, said, files, plan, open }: { draft: Draft; said: Said; files: Files; plan: Plan;
  open: (view: View | "problems") => void }) {
  const sandbox = useLoad(() => get<Sandbox>("/studio/api/sandbox"), []);
  const shell = useLoad(shellOf, []);
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
  const page = { page: "agent" as const, agent: draft.agent };
  const settings = !atWork && toWork(draft.agent, plan, Boolean(shell.data?.pages.includes("settings")));
  const next = released
    ? settings ? <a className="button primary" id="put-to-work" href={settings.href}>Put it to work in the settings</a>
      : <Link to={page} className="button primary">{atWork ? "Watch it on its page" : "Put it to work, from its page"}</Link>
    : !shaped
    ? <button type="button" className="primary" onClick={() => open("problems")}>See what stops its release</button>
    : draft.published
      ? <a className="button primary" href={draft.published ?? "#"} target="_blank" rel="noopener noreferrer">Open its pull request</a>
      : untried
        ? <><button type="button" className="primary" onClick={() => open("try")}>Try it in the sandbox</button>
            <button type="button" className="quiet" onClick={() => open("publish")}>Publish it without trying it</button></>
        : <button type="button" className="primary" onClick={() => open("publish")}>Publish it</button>;
  return (
    <section id="journey" aria-labelledby="journey-title">
      <h2 id="journey-title">Where it stands</h2>
      <JourneyPath stages={stages} next={next} />
    </section>
  );
}

export function DraftPage({ id }: { id: string }) {
  const loaded = useLoad(() => get<Draft>(`/studio/api/drafts/${encodeURIComponent(id)}`), [id]);
  const tools = useLoad(() => get<Offer>("/studio/api/tools"), []);
  const [files, setFiles] = useState<Files | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);  // for its first instance, beside its files
  const [said, setSaid] = useState<Said | null>(null);
  const [kept, setKept] = useState<Kept>("kept");
  const [revision, setRevision] = useState(0);  // each time a change is kept
  const [view, setView] = useState<View>("design");
  const [asked, setAsked] = useState(0);  // each time someone asks to see what stops its release
  const latest = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const planned = useRef<{ plan: Plan; changed: boolean }>({ plan: { parts: [], serves: [], asks: [] }, changed: false });
  useEffect(() => {
    if (loaded.data && files === null) {
      setFiles(loaded.data.files);
      setPlan(whole(loaded.data.plan));
      planned.current = { plan: whole(loaded.data.plan), changed: false };
      const { problems, preview, signers, released, at_work } = loaded.data;
      setSaid({ problems, preview, signers, released, at_work });
    }
  }, [loaded.data, files]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {  // the view opened takes the keyboard's focus, as a section scrolled to did
    if (view === "try" || view === "publish") document.getElementById(view === "try" ? "try" : "publishing")?.focus();
  }, [view]);

  const keep = async (next: Files, mine: number) => {
    try {
      const sending = planned.current.changed ? planned.current.plan : undefined;  // only once it changes
      const saved = await send<Draft>("PUT", `/studio/api/drafts/${encodeURIComponent(id)}`,
                                      { files: next, ...(sending ? { plan: sending } : {}) });
      if (mine !== latest.current) return;  // a later change is on its way
      if (sending === planned.current.plan) planned.current.changed = false;
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
  const changePlan = (next: Plan, nextFiles?: Files) => {  // kept as its files are, with them
    setPlan(next);
    planned.current = { plan: next, changed: true };
    if (files) change(nextFiles ?? files);
  };
  const drop = async () => {
    if (!window.confirm("Drop this draft? It can't be had back.")) return;
    await send("DELETE", `/studio/api/drafts/${encodeURIComponent(id)}`);
    go({ page: "agents" });
  };
  const open = (to: View | "problems") => {
    if (to === "problems") {
      setView("design");
      setAsked((n) => n + 1);
    } else setView(to);
  };

  const draft = loaded.data;
  if (draft && !draft.yours) return <TheirDraft draft={draft} />;
  const status = typeof kept === "object" ? <span className="badge bad"><Icon name="cross" />{kept.problem}</span>
    : kept === "keeping" ? <>Keeping…</> : <><Icon name="check" />Kept</>;
  const ready = Boolean(said && said.problems.length === 0 && kept === "kept");
  const bar = (
    <header className="wb-bar">
      <Link to={{ page: "agents" }} className="crumb"><Icon name="back" />Agents</Link>
      <h1>{draft ? draft.agent : "A draft"}</h1>
      {draft && <span className="chip">draft</span>}
      {draft && <span className="chip mono">{draft.based_on}</span>}
      {draft && <span className="wb-saved" id="kept">{status}</span>}
      {said && (
        <button type="button" className={`badge ${said.problems.length ? "bad" : "good"}`} id="problem-count" onClick={() => open("problems")}>
          <Icon name={said.problems.length ? "cross" : "check"} />
          {said.problems.length ? `${said.problems.length} problem${said.problems.length === 1 ? "" : "s"}` : "No problems"}
        </button>
      )}
      <span className="wb-spacer" />
      {draft && (
        <>
          <div className="modes" role="group" aria-label="The draft">
            {VIEWS.map(([key, label]) => (
              <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>
            ))}
          </div>
          <HandOver id={id} />
          <button type="button" className="quiet" onClick={drop}>Drop the draft</button>
          <button type="button" className="primary" id="to-publish" aria-pressed={view === "publish"} onClick={() => setView("publish")}>Publish it</button>
        </>
      )}
    </header>
  );
  if (!draft || !files || !said || !tools.data || !plan) {
    return <>{bar}<div className="wb-body whole"><div className="wb-view"><Waiting error={loaded.error ?? tools.error} /></div></div></>;
  }
  const overview: ReactNode = (
    <>
      <p className="note" id="about-draft">From {draft.based_on}, started {when(draft.created_at)}.{handedBy(draft)} Yours to change,
        and readable by the agent's other owners and authors: nothing runs it until it's published and its release signed.</p>
      <Journey draft={draft} said={said} files={files} plan={plan} open={open} />
      <Problems problems={said.problems} />
    </>
  );
  const cases = keptCases(files[CASES]);
  const tryIt = (
    <>
      <button type="button" className="primary" id="try-it" onClick={() => setView("try")}><Icon name="run" />Try it</button>
      <p className="note">{said.problems.length ? `${said.problems.length === 1 ? "One thing stops" : `${said.problems.length} things stop`} its release`
        : cases ? `${cases} test case${cases === 1 ? "" : "s"} kept` : "Nothing stops its release"}</p>
    </>
  );
  return (
    <>
      {bar}
      {view === "design" && (
        <Designer name={draft.agent} files={files} offer={tools.data} signers={said.signers} problems={said.problems.length}
                  change={(f) => edit(() => f)} plan={plan} changePlan={changePlan} overview={overview} tryIt={tryIt}
                  asked={asked} />
      )}
      <div className="wb-body whole" hidden={view === "design"}>
        {view === "instructions" && (
          <section className="wb-view" aria-labelledby="instructions-title">
            <h2 id="instructions-title">Its instructions</h2>
            <label className="wb-field"><span className="wb-label">What it's told at the start of each run, its AGENTS.md</span>
              <textarea id="instructions" rows={24} value={files["AGENTS.md"] ?? ""}
                        onChange={(e) => change({ ...files, "AGENTS.md": e.target.value })} /></label>
          </section>
        )}
        {view === "files" && (
          <section className="wb-view" aria-labelledby="files-title">
            <Problems problems={said.problems} />
            <h2 id="files-title">Its files</h2>
            <Raw files={files} change={change} />
          </section>
        )}
        <section className="wb-view" id="try" tabIndex={-1} hidden={view !== "try"} aria-labelledby="try-title">
          <h2 id="try-title">Try it in the sandbox</h2>
          <TryIt draft={id} name={draft.agent} ready={ready}
                 keep={(testCase) => change({ ...files, [CASES]: withCase(files[CASES] ?? "", testCase) })}
                 revision={revision} />
        </section>
        <section className="wb-view" id="publishing" tabIndex={-1} hidden={view !== "publish"} aria-labelledby="publish-title">
          <h2 id="publish-title">Publish it</h2>
          <Publish draft={id} name={draft.agent} ready={ready} published={draft.published} publishing={draft.publishing}
                   revision={revision} />
        </section>
      </div>
    </>
  );
}
