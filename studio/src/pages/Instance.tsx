// An instance's dashboard: how it's doing over a period, from the measures counted for it alone,
// and its runs, a page at a time, those whose every record the viewer may see.

import { useState } from "react";
import { type Catalogue, type Figures, get, type RunLine, type RunsPage } from "../api";
import { Link } from "../router";
import { aboutInstance, OutcomeBadge, PageHead, people, plural, runners, share, StatusBadge, useLoad,
         Waiting, when } from "../ui";

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
    </div>
  );
}

function Breakdown({ figures }: { figures: Figures }) {
  const o = figures.obligations;
  const r = figures.reminders;
  return (
    <div className="two-up pairs">
      <section className="card">
        <h3>How runs ended</h3>
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
        <h3>What a5s refused</h3>
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
        <h3>What fell due</h3>
        <dl className="facts">
          <dt>What people owed</dt><dd>{o.due ? `${o.due} due: ${o.on_time} on time, ${o.late} late, ${o.open} open; ${o.chased} chased, ${o.escalated} taken up the line` : "nothing"}</dd>
          <dt>Reminders</dt><dd>{r.due ? `${r.due} due: ${r.on_time} on time, ${r.missed} missed` : "none fell due"}</dd>
          <dt>Reports sent</dt><dd>{figures.reports.map((x) => `${x.source} ${x.outcome}: ${x.reports}`).join("; ") || "none"}</dd>
        </dl>
      </section>
      <section className="card">
        <h3>Who came back</h3>
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
      <h3>Runs</h3>
      {!first.data && <Waiting error={first.error} />}
      {first.data && runs.length === 0 && <p className="note">No runs you may see.</p>}
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

export function InstancePage({ id }: { id: string }) {
  const [days, setDays] = useState(30);
  const catalogue = useLoad(() => get<Catalogue>("/studio/api"), []);
  const figures = useLoad(() => get<Figures>(`/studio/api/instances/${encodeURIComponent(id)}?days=${days}`), [id, days]);
  const inst = catalogue.data?.agents.flatMap((a) => a.instances).find((i) => i.id === id);
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } },
                         ...(inst ? [{ label: inst.agent, to: { page: "agent" as const, agent: inst.agent } }] : [])]}
                title={id} badges={inst && <StatusBadge status={inst.status} />}>
        {inst && <div className="meta"><span>{aboutInstance(inst)}</span><span>run by {runners(inst)}</span>{!inst.current && <span className="badge warn">still on release {inst.release}</span>}</div>}
        <label className="period">Over the last{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
          </select>
        </label>
      </PageHead>
      {!figures.data && <Waiting error={figures.error} />}
      {figures.data && <><Tiles figures={figures.data} /><Breakdown figures={figures.data} /></>}
      <Runs instance={id} />
    </>
  );
}
