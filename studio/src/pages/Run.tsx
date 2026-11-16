// One run: what started it, whom it acted for, and each of its calls to a tool, as time, with
// a5s's decision on it and how it ended. What was said isn't shown: the team that runs a5s keeps
// it in the ledger, by its hash alone.

import { AgentMap } from "../AgentMap";
import { type AgentKnown, type Call, get, type Run, usesOf } from "../api";
import { RunTimeline, Shapes, type Step, type Tone } from "../design";
import { an, OutcomeBadge, outcomeTone, PageHead, people, plural, risk, time, useLoad, Waiting, when } from "../ui";

const DECIDED: Record<string, string> = { allow: "allowed", deny: "refused", hold: "held for a decision" };

/** The run as time: what started it, each call in the colour of what its tool does, or of a5s's
 * refusing or holding it, and how it ended. */
function steps(run: Run, agent: AgentKnown | undefined): Step[] {
  const uses = agent && usesOf(agent) ? agent : undefined;
  const tools = new Map((uses ? uses.tools : []).map((tool) => [tool.name, tool]));
  const tone = (call: Call): Tone => {
    if (call.decision === "deny") return "bad";
    if (call.decision === "hold") return "warn";
    const tool = tools.get(call.tool);
    return tool ? risk(tool) : "own";  // a5s's own tools aren't the agent's to list
  };
  return [
    { at: time(run.opened_at), tone: "idle", detail: `for ${whom(run)}`,
      what: run.trigger ? `${/^[aeiou]/i.test(run.trigger) ? "An" : "A"} ${run.trigger} started it` : "It started" },
    ...run.calls.map((call) => ({
      at: time(call.at), tone: tone(call), what: <code>{call.tool}</code>,
      detail: [DECIDED[call.decision] ?? call.decision, call.outcome, ...call.reasons].filter(Boolean).join(" · "),
    })),
    ...(run.closed_at ? [{ at: time(run.closed_at), tone: outcomeTone(run.outcome) as Tone,
                           what: `Ended: ${run.outcome}`, detail: `after ${took(run)}` }] : []),
  ];
}

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
  const agent = useLoad(() => (run?.agent ? get<AgentKnown>(`/studio/api/agents/${encodeURIComponent(run.agent)}`)
                                          : Promise.resolve(undefined)), [run?.agent]);
  const crumbs = run ? [
    { label: "Agents", to: { page: "agents" as const } },
    ...(run.agent ? [{ label: run.agent, to: { page: "agent" as const, agent: run.agent } }] : []),
    { label: run.instance, to: { page: "instance" as const, instance: run.instance } },
  ] : [{ label: "Agents", to: { page: "agents" as const } }];
  const started = run ? Object.entries(run.started_by).filter(([key]) => key !== "kind") : [];
  return (
    <>
      <PageHead crumbs={crumbs} title={run ? `${an(run.trigger ?? "run")}, ${when(run.opened_at)}` : "A run"}
                badges={run && <OutcomeBadge outcome={run.outcome} />} />
      {!run && (
        <Waiting error={error}>  {/* its figures, two cards and its map, as they will be (round 13, C11) */}
          <div className="tiles">{[0, 1, 2, 3].map((n) => <div key={n} className="tile"><Shapes lines={1} /></div>)}</div>
          <div className="two-up">
            <section className="card"><Shapes lines={4} /></section>
            <section className="card"><Shapes lines={2} /></section>
          </div>
          <section className="card map-card"><Shapes block /></section>
        </Waiting>
      )}
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
              <h2>What started it</h2>
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
              <h2>Records it read</h2>
              {run.records.length === 0 ? <p className="note">None.</p> :
                <div className="chips">{run.records.map((r) => <span key={r} className="chip mono">{r}</span>)}</div>}
              {run.read_outside && <p><span className="badge outside">read content from outside the organisation</span></p>}
            </section>
          </div>
          {agent.data && usesOf(agent.data) && (
            <section className="card map-card">
              <h2>Its path</h2>
              <p className="note">What started it, and the tools it called through a5s's checks, with how many times and how many a5s refused, on its agent's map. What it didn't use is faded.</p>
              <AgentMap agent={agent.data} run={run} />
            </section>
          )}
          <section className="card wide">
            <h2>What it did, in order</h2>
            <RunTimeline steps={steps(run, agent.data)} />
            <p className="note">{plural(run.calls.length, "call")} to tools. What was said isn't shown here: the team that runs a5s keeps it in the ledger, by its hash alone.</p>
          </section>
        </>
      )}
    </>
  );
}
