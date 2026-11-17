// One run: what started it, whom it acted for, and each of its calls to a tool, as time, with
// a5s's decision on it and how it ended. What was said isn't shown: the team that runs a5s keeps
// it in the ledger, by its hash alone.

import { AgentMap } from "../AgentMap";
import { KeepAsCase } from "../RunCase";
import { type AgentKnown, type Call, get, type Run, usesOf } from "../api";
import { RunTimeline, Shapes, type Step, type Tone } from "../design";
import { locale, t } from "../i18n";
import { OutcomeBadge, outcomeName, outcomeTone, PageHead, people, plural, risk, time, useLoad, Waiting,
         when } from "../ui";

const DECIDED: Record<string, string> = {  // each in the language spoken whenever it's read
  get allow() { return t("allowed"); }, get deny() { return t("refused"); }, get hold() { return t("held for a decision"); },
};

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
    { at: time(run.opened_at), tone: "idle", detail: t("for {whom}", { whom: whom(run) }),
      what: run.trigger ? (/^[aeiou]/i.test(run.trigger) ? t("An {trigger} started it", { trigger: run.trigger })
        : t("A {trigger} started it", { trigger: run.trigger })) : t("It started") },
    ...run.calls.map((call) => ({
      at: time(call.at), tone: tone(call), what: <code>{call.tool}</code>,
      detail: [DECIDED[call.decision] ?? call.decision, call.outcome, ...call.reasons].filter(Boolean).join(" · "),
    })),
    ...(run.closed_at ? [{ at: time(run.closed_at), tone: outcomeTone(run.outcome),
                           what: t("Ended: {outcome}", { outcome: outcomeName(run.outcome) }),
                           detail: t("after {took}", { took: took(run) }) }] : []),
  ];
}

function whom(run: Run): string {
  const named = run.acts_for.map((p) => p.name || p.id).join(", ");
  return named || (run.people ? people(run.people) : t("nobody"));
}

function took(run: Run): string {
  if (!run.closed_at) return t("still open");
  const seconds = Math.max(0, (new Date(run.closed_at).getTime() - new Date(run.opened_at).getTime()) / 1000);
  return seconds < 90 ? t("{seconds} s", { seconds: seconds.toFixed(1) })
    : t("{minutes} min", { minutes: Math.round(seconds / 60) });
}

/** What its page is called: what started it, with its article, and when it did. */
function heading(run: Run): string {
  const at = when(run.opened_at);
  if (run.trigger === null || run.trigger === undefined) return t("A run, {when}", { when: at });
  return /^[aeiou]/i.test(run.trigger) ? t("An {trigger}, {when}", { trigger: run.trigger, when: at })
    : t("A {trigger}, {when}", { trigger: run.trigger, when: at });
}

export function RunPage({ id }: { id: string }) {
  const { data: run, error } = useLoad(() => get<Run>(`/studio/api/runs/${encodeURIComponent(id)}`), [id]);
  const agent = useLoad(() => (run?.agent ? get<AgentKnown>(`/studio/api/agents/${encodeURIComponent(run.agent)}`)
                                          : Promise.resolve(undefined)), [run?.agent]);
  const crumbs = run ? [
    { label: t("Agents"), to: { page: "agents" as const } },
    ...(run.agent ? [{ label: run.agent, to: { page: "agent" as const, agent: run.agent } }] : []),
    { label: run.instance, to: { page: "instance" as const, instance: run.instance } },
  ] : [{ label: t("Agents"), to: { page: "agents" as const } }];
  const started = run ? Object.entries(run.started_by).filter(([key]) => key !== "kind") : [];
  return (
    <>
      <PageHead crumbs={crumbs} title={run ? heading(run) : t("A run")}
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
            <div className="tile"><div className="tile-label">{t("For")}</div><div className="tile-value small">{whom(run)}</div></div>
            <div className="tile"><div className="tile-label">{t("Took")}</div><div className="tile-value small">{took(run)}</div></div>
            <div className="tile"><div className="tile-label">{t("Tokens")}</div><div className="tile-value small">{run.tokens.toLocaleString(locale())}</div>
              <div className="tile-detail">{t("{tokens_in} in, {tokens_out} out, {cached} cached", { tokens_in: run.tokens_in.toLocaleString(locale()),
                tokens_out: run.tokens_out.toLocaleString(locale()), cached: run.tokens_cached.toLocaleString(locale()) })}</div></div>
            <div className="tile"><div className="tile-label">{t("Model")}</div><div className="tile-value small">{run.model ?? t("none")}</div></div>
          </div>
          <div className="two-up">
            <section className="card">
              <h2>{t("What started it")}</h2>
              <dl className="facts">
                <dt>{t("Kind")}</dt><dd>{run.trigger ?? t("other")}</dd>
                {started.map(([key, value]) => (
                  <div key={key} className="fact-pair"><dt>{key.replace(/_/g, " ")}</dt>
                    <dd className="mono">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>
                ))}
                <dt>{t("Opened")}</dt><dd>{when(run.opened_at)}</dd>
                <dt>{t("Closed")}</dt><dd>{run.closed_at ? when(run.closed_at) : t("not yet")}</dd>
              </dl>
            </section>
            <section className="card">
              <h2>{t("Records it read")}</h2>
              {run.records.length === 0 ? <p className="note">{t("None.")}</p> :
                <div className="chips">{run.records.map((r) => <span key={r} className="chip mono">{r}</span>)}</div>}
              {run.read_outside && <p><span className="badge outside">{t("read content from outside the organisation")}</span></p>}
            </section>
          </div>
          {agent.data && usesOf(agent.data) && (
            <section className="card map-card">
              <h2>{t("Its path")}</h2>
              <p className="note">{t("What started it, and the tools it called through a5s's checks, with how many times and how many a5s refused, on its agent's map. What it didn't use is faded.")}</p>
              <AgentMap agent={agent.data} run={run} />
            </section>
          )}
          <section className="card wide">
            <h2>{t("What it did, in order")}</h2>
            <RunTimeline steps={steps(run, agent.data)} />
            <p className="note">{t("{calls} to tools. What was said isn't shown here: the team that runs a5s keeps it in the ledger, by its hash alone.", { calls: plural(run.calls.length, "call") })}</p>
          </section>
          <KeepAsCase run={run.run} />
        </>
      )}
    </>
  );
}
