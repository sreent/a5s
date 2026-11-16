// An instance's page: what of it waits, and where each is done; suspending or resuming it,
// signed in afresh for that alone; how far it may act in each part; how it's doing over a
// period, from the measures counted for it alone; and its runs, a page at a time, those whose
// every record the viewer may see.

import { useEffect, useState } from "react";
import { type Catalogue, type Figures, get, type Instance, type RunLine, type RunsPage, send,
         type Standing, type StatusAsked } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { Confirm, rung, useToast } from "../design";
import { Link } from "../router";
import { shellOf } from "../Sidebar";
import { RunsByDay } from "../RunsByDay";
import { aboutInstance, type Loaded, OutcomeBadge, PageHead, people, plural, runners, share, StatusBadge,
         useLoad, Waiting, WaitList, when } from "../ui";

/** What of it waits: the changes it asked for, its samples for a grade, and its notebook, each
 * where it's done, for the viewer or for others. */
function Waits({ standing }: { standing: Loaded<Standing> }) {
  return (
    <section className="card" id="instance-waiting">
      <h2>What waits on it</h2>
      {standing.data ? <WaitList waiting={standing.data.waiting} none="Nothing of it waits now." />
                     : <Waiting error={standing.error} />}
    </section>
  );
}

/** Suspending it, which stops it at its next step, or resuming it, which only whoever suspended
 * it may: each signed in afresh for that alone, and carried out by a5s within a minute, once it
 * has checked the sign-in again (core/suspension.py). */
function Stopping({ id, standing, problem, setProblem }: {
  id: string; standing?: Standing; problem?: string; setProblem: (problem: string) => void;
}) {
  const shell = useLoad(shellOf, []);
  const settles = Boolean(shell.data?.pages.includes("settings"));  // approves versions of the settings
  const go = (action: "suspend" | "resume") => () => {
    const salt = salted();  // the act's nonce, as core/suspension.py's `nonce` makes it
    hashed(`a5s ${action} instance ${id} ${salt}`)
      .then((nonce) => signInFor({ kind: "status", action, instance: id, salt }, nonce))
      .catch((e: Error) => setProblem(e.message));
  };
  const asked = standing?.asked;
  return (
    <>
      {asked && <p className="note" role="status" id="asked">{asked.by} asked to {asked.action} it, {when(asked.at)}: a5s does so within a minute, once it has checked that sign-in again.</p>}
      {problem && <p className="problem" role="alert">{problem}</p>}
      {(standing?.may || settles) && (
        <div className="actions">
          {settles && <Link to={{ page: "settings", search: `?instance=${encodeURIComponent(id)}` }} className="button"
                            id="its-settings">Change its settings</Link>}
          {standing?.may === "suspend"
            ? <Confirm label="Suspend it" danger title={`Suspend ${id}?`}
                       about="It stops at its next step, even in a run already going, and starts no runs, until whoever suspended it resumes it. Those it serves are told it's suspended. You'll sign in again, for this alone."
                       confirm="Sign in and suspend it" onConfirm={go("suspend")} />
            : standing?.may === "resume" && <Confirm label="Resume it" title={`Resume ${id}?`}
                       about="It works again as its settings say, from its next message. You'll sign in again, for this alone, with a second factor where your organisation asks for one."
                       confirm="Sign in and resume it" onConfirm={go("resume")} />}
        </div>
      )}
    </>
  );
}

/** How far it may act in each part, and each type of change its settings set a level for. */
function Reach({ inst }: { inst: Instance }) {
  const parts = Object.entries(inst.parts as Record<string, number>);
  const acts = inst.actions as Record<string, Record<string, number>>;
  return (
    <section className="card" id="reach">
      <h2>How far it may act</h2>
      {parts.length === 0 ? <p>Level {inst.level}, {rung(inst.level)}, in no part.</p> : (
        <table className="grid-table compact">
          <thead><tr><th>Part</th><th>Level</th><th>Each type of change at its own</th></tr></thead>
          <tbody>{parts.map(([part, level]) => {
            const own = Object.entries(acts[part] ?? {});
            return (
              <tr key={part}>
                <td>{part}</td>
                <td>{level} · {rung(level)}</td>
                <td>{own.length === 0 ? <span className="faint">none</span> : own.map(([action, at]) => (
                  <div key={action}><span className="mono">{action}</span> at {at} · {rung(at)}</div>
                ))}</td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
      <p className="note">As the settings its parts' owners signed give it. A type of change at level 2 is made on its own only where graded samples have raised a5s's cap on it; until they do, a person decides each.</p>
    </section>
  );
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {detail && <div className="tile-detail">{detail}</div>}
    </div>
  );
}

function Tiles({ figures }: { figures: Figures }) {
  const runs = figures.ended.reduce((n, e) => n + e.runs, 0);
  const done = figures.ended.filter((e) => e.outcome === "done").reduce((n, e) => n + e.runs, 0);
  const modelled = figures.runs.reduce((n, r) => n + r.runs, 0);
  const tokens = modelled ? Math.round(figures.runs.reduce((n, r) => n + r.runs * r.tokens_per_run, 0) / modelled) : 0;
  const cached = figures.runs.find((r) => r.cached_share !== null)?.cached_share ?? null;
  const denied = figures.denied.reduce((n, d) => n + d.times, 0);
  return (
    <div className="tiles">
      <Tile label="Runs" value={runs.toLocaleString()} detail={plural(modelled, "called a model", "called a model")} />
      <Tile label="Ended done" value={runs ? `${Math.round((done / runs) * 100)}%` : "none yet"} detail={`${done.toLocaleString()} of ${runs.toLocaleString()}`} />
      <Tile label="Tokens a run" value={tokens.toLocaleString()} detail={`${share(cached)} cached`} />
      <Tile label="Denied" value={denied.toLocaleString()} detail={figures.denied_partial ? "the latest only" : "calls a5s refused"} />
      <Tile label="Held changes" value={figures.held.held.toLocaleString()} detail={`${figures.held.waiting} waiting`} />
      <Tile label="Graded" value={figures.samples.graded.toLocaleString()} detail={figures.samples.graded ? `${figures.samples.right} right, ${figures.samples.critical} critical` : "no samples yet"} />
      {figures.judge.both > 0 && (
        <Tile label="Its judge agrees" value={share(figures.judge.agreed_share)}
              detail={`with people, on ${plural(figures.judge.both, "sample", "samples")}; it missed ${figures.judge.missed}`} />
      )}
    </div>
  );
}

function Breakdown({ figures }: { figures: Figures }) {
  const o = figures.obligations;
  const r = figures.reminders;
  return (
    <div className="two-up pairs">
      <section className="card">
        <h2>How runs ended</h2>
        {figures.ended.length === 0 ? <p className="note">No runs in this period.</p> : (
          <table className="grid-table compact">
            <thead><tr><th>Started by</th><th>Ended</th><th className="num">Runs</th></tr></thead>
            <tbody>{figures.ended.map((e) => (
              <tr key={`${e.kind}-${e.outcome}`}><td>{e.kind ?? "other"}</td><td><OutcomeBadge outcome={e.outcome} /></td><td className="num">{e.runs}</td></tr>
            ))}</tbody>
          </table>
        )}
      </section>
      <section className="card">
        <h2>What a5s refused</h2>
        {figures.denied.length === 0 ? <p className="note">Nothing was denied.</p> : (
          <ul className="plain">{figures.denied.map((d) => (
            <li key={`${d.kind}-${d.action}-${d.reasons.join()}`}>
              <span className="mono">{d.action}</span> · {plural(d.times, "time")}
              {d.reasons.length > 0 && <div className="faint">{d.reasons.join(", ")}</div>}
            </li>
          ))}</ul>
        )}
      </section>
      <section className="card">
        <h2>What fell due</h2>
        <dl className="facts">
          <dt>What people owed</dt><dd>{o.due ? `${o.due} due: ${o.on_time} on time, ${o.late} late, ${o.open} open; ${o.chased} chased, ${o.escalated} taken up the line` : "nothing"}</dd>
          <dt>Reminders</dt><dd>{r.due ? `${r.due} due: ${r.on_time} on time, ${r.missed} missed` : "none fell due"}</dd>
          <dt>Reports sent</dt><dd>{figures.reports.map((x) => `${x.source} ${x.outcome}: ${x.reports}`).join("; ") || "none"}</dd>
        </dl>
      </section>
      <section className="card">
        <h2>Who came back</h2>
        {figures.returning.length === 0 ? <p className="note">Nobody wrote before this period.</p> : (
          <ul className="plain">{figures.returning.map((x) => (
            <li key={x.agent}>{x.came_back} of the {people(x.wrote_before)} who wrote to the {x.agent} before</li>
          ))}</ul>
        )}
      </section>
    </div>
  );
}

function whom(run: RunLine): string {
  const named = run.acts_for.map((p) => p.name || p.id).join(", ");
  return named || (run.people ? people(run.people) : "nobody");
}

function Runs({ instance }: { instance: string }) {
  const [pages, setPages] = useState<RunsPage[]>([]);
  const [error, setError] = useState<string>();
  const first = useLoad(() => get<RunsPage>(`/studio/api/instances/${encodeURIComponent(instance)}/runs`), [instance]);
  const all = [...(first.data ? [first.data] : []), ...pages];
  const last = all[all.length - 1];
  const older = async () => {
    try {
      setPages([...pages, await get<RunsPage>(`/studio/api/instances/${encodeURIComponent(instance)}/runs?before=${encodeURIComponent(last.before ?? "")}`)]);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const runs = all.flatMap((p) => p.runs);
  const hidden = all.reduce((n, p) => n + p.hidden, 0);
  return (
    <section className="card wide">
      <h2>Runs</h2>
      {!first.data && <Waiting error={first.error} />}
      {first.data?.fewer && <p className="note">It serves fewer than {first.data.fewer} people, so its runs show only in its daily figures until the data protection officer agrees to name whom runs act for: one by one, each would say what one of them did.</p>}
      {first.data && !first.data.fewer && runs.length === 0 && <p className="note">No runs you may see.</p>}
      {runs.length > 0 && (
        <table className="grid-table runs-table">
          <thead><tr><th>When</th><th>Started by</th><th>For</th><th>Ended</th><th className="num">Tokens</th><th /></tr></thead>
          <tbody>{runs.map((run) => (
            <tr key={run.run}>
              <td>{when(run.opened_at)}</td>
              <td>{run.trigger ?? "other"}{run.read_outside && <span className="badge outside">read outside content</span>}</td>
              <td>{whom(run)}</td>
              <td><OutcomeBadge outcome={run.outcome} /></td>
              <td className="num">{run.tokens.toLocaleString()}</td>
              <td><Link to={{ page: "run", run: run.run }} label={`The run at ${when(run.opened_at)}`}>Open</Link></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {hidden > 0 && <p className="note">And {plural(hidden, "run")} that read records you may not see.</p>}
      {error && <p className="problem">{error}</p>}
      {last?.before && <button type="button" onClick={older}>Older runs</button>}
    </section>
  );
}

// The viewer's own time zone, for which days the runs fall on
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function InstancePage({ id }: { id: string }) {
  const toast = useToast();
  const [days, setDays] = useState(30);
  const [again, setAgain] = useState(0);  // to read how it stands again, once something's asked
  const [problem, setProblem] = useState<string>();
  const standing = useLoad(() => get<Standing>(
    `/studio/api/instances/${encodeURIComponent(id)}/standing`), [id, again]);
  useEffect(() => {  // back from signing in for an act on it: ask a5s to carry it out, once
    const act = takeAct();
    if (act?.kind !== "status" || act.instance !== id) return;
    send<StatusAsked>("POST", `/studio/api/instances/${encodeURIComponent(id)}/status`,
                      { action: act.action, salt: act.salt })
      .then(() => {
        setAgain((n) => n + 1);
        toast(`You asked to ${act.action} ${id}: a5s does it within a minute.`);
      })
      .catch((e: Error) => setProblem(e.message));
  }, [id, toast]);
  const catalogue = useLoad(() => get<Catalogue>("/studio/api"), [again]);
  const figures = useLoad(() => get<Figures>(
    `/studio/api/instances/${encodeURIComponent(id)}?days=${days}&zone=${encodeURIComponent(ZONE)}`), [id, days]);
  const inst = catalogue.data?.agents.flatMap((a) => a.instances).find((i) => i.id === id);
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } },
                         ...(inst ? [{ label: inst.agent, to: { page: "agent" as const, agent: inst.agent } }] : [])]}
                title={id} badges={inst && <StatusBadge status={inst.status} />}>
        {inst && <div className="meta"><span>{aboutInstance(inst)}</span><span>run by {runners(inst)}</span>{standing.data?.suspended_by && <span>suspended by {standing.data.suspended_by}</span>}{!inst.current && <span className="badge warn">still on release {inst.release}</span>}</div>}
        <Stopping id={id} standing={standing.data} problem={problem} setProblem={setProblem} />
        <label className="period">Over the last{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
          </select>
        </label>
      </PageHead>
      <div className="two-up">
        <Waits standing={standing} />
        {inst && <Reach inst={inst} />}
      </div>
      {!figures.data && <Waiting error={figures.error} />}
      {figures.data && (
        <div className={figures.stale ? "stale" : undefined}>
          <Tiles figures={figures.data} />
          <section className="card">
            <h2>Runs by day</h2>
            <RunsByDay days={figures.data.daily} zone={figures.data.zone} />
          </section>
          <Breakdown figures={figures.data} />
        </div>
      )}
      <Runs instance={id} />
    </>
  );
}
