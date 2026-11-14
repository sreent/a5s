// One run: what started it, whom it acted for, and each of its calls to a tool, with a5s's
// decision on it and how it ended. What was said isn't shown: the team that runs a5s keeps it in
// the ledger, by its hash alone.

import { get, type Run } from "../api";
import { DecisionBadge, OutcomeBadge, PageHead, people, plural, time, useLoad, Waiting, when } from "../ui";

function whom(run: Run): string {
  const named = run.acts_for.map((p) => p.name || p.id).join(", ");
  return named || (run.people ? people(run.people) : "nobody");
}

function took(run: Run): string {
  if (!run.closed_at) return "still open";
  const seconds = Math.max(0, (new Date(run.closed_at).getTime() - new Date(run.opened_at).getTime()) / 1000);
  return seconds < 90 ? `${seconds.toFixed(1)} s` : `${Math.round(seconds / 60)} min`;
}

export function RunPage({ id }: { id: string }) {
  const { data: run, error } = useLoad(() => get<Run>(`/studio/api/runs/${encodeURIComponent(id)}`), [id]);
  const crumbs = run ? [
    { label: "Agents", to: { page: "agents" as const } },
    ...(run.agent ? [{ label: run.agent, to: { page: "agent" as const, agent: run.agent } }] : []),
    { label: run.instance, to: { page: "instance" as const, instance: run.instance } },
  ] : [{ label: "Agents", to: { page: "agents" as const } }];
  const started = run ? Object.entries(run.started_by).filter(([key]) => key !== "kind") : [];
  return (
    <>
      <PageHead crumbs={crumbs} title={run ? `A ${run.trigger ?? "run"}, ${when(run.opened_at)}` : "A run"}
                badges={run && <OutcomeBadge outcome={run.outcome} />} />
      {!run && <Waiting error={error} />}
      {run && (
        <>
          <div className="tiles">
            <div className="tile"><div className="tile-label">For</div><div className="tile-value small">{whom(run)}</div></div>
            <div className="tile"><div className="tile-label">Took</div><div className="tile-value small">{took(run)}</div></div>
            <div className="tile"><div className="tile-label">Tokens</div><div className="tile-value small">{run.tokens.toLocaleString()}</div>
              <div className="tile-detail">{run.tokens_in.toLocaleString()} in, {run.tokens_out.toLocaleString()} out, {run.tokens_cached.toLocaleString()} cached</div></div>
            <div className="tile"><div className="tile-label">Model</div><div className="tile-value small">{run.model ?? "none"}</div></div>
          </div>
          <div className="two-up">
            <section className="card">
              <h3>What started it</h3>
              <dl className="facts">
                <dt>Kind</dt><dd>{run.trigger ?? "other"}</dd>
                {started.map(([key, value]) => (
                  <div key={key} className="fact-pair"><dt>{key.replace(/_/g, " ")}</dt>
                    <dd className="mono">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>
                ))}
                <dt>Opened</dt><dd>{when(run.opened_at)}</dd>
                <dt>Closed</dt><dd>{run.closed_at ? when(run.closed_at) : "not yet"}</dd>
              </dl>
            </section>
            <section className="card">
              <h3>Records it read</h3>
              {run.records.length === 0 ? <p className="note">None.</p> :
                <div className="chips">{run.records.map((r) => <span key={r} className="chip mono">{r}</span>)}</div>}
              {run.read_outside && <p><span className="badge outside">read content from outside the organisation</span></p>}
            </section>
          </div>
          <section className="card wide">
            <h3>What it did</h3>
            {run.calls.length === 0 && <p className="note">It called no tools.</p>}
            {run.calls.length > 0 && (
              <ol className="steps">
                {run.calls.map((call) => (
                  <li key={call.seq} className={`step ${call.decision}`}>
                    <span className="step-time">{time(call.at)}</span>
                    <span className="mono step-tool">{call.tool}</span>
                    <DecisionBadge decision={call.decision} />
                    {call.outcome && <span className="badge">{call.outcome}</span>}
                    {call.reasons.length > 0 && <div className="faint step-why">{call.reasons.join(", ")}</div>}
                  </li>
                ))}
              </ol>
            )}
            <p className="note">{plural(run.calls.length, "call")} to tools. What was said isn't shown here: the team that runs a5s keeps it in the ledger, by its hash alone.</p>
          </section>
        </>
      )}
    </>
  );
}
