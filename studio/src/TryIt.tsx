// Trying a draft in the sandbox, a deployment of a5s of its own: say something to the draft as one
// of the sandbox's made-up people, on its stand-in model or a real one it has, and see what it
// answered, each call it made with the policy's decision, and what the model was sent and said.
// Nothing said here reaches anyone's real records, and nothing of it is kept in this deployment.

import { type FormEvent, useState } from "react";
import { get, type Run, send } from "./api";
import { type Case, CASES } from "./definition";
import { DecisionBadge, useLoad } from "./ui";

type Offered = { people: { id: string; name: string }[]; models: string[] };
type Message = { role: string; content?: string | null; tool_calls?: { function: { name: string; arguments: string } }[] };
type ModelCall = { sent: { messages: Message[]; tools?: { function: { name: string } }[] }; came: unknown; status: number };
type Tried = { agent: string; reply: string; run: Run | null; model_calls: ModelCall[] };
type Turn = { id: number; as: string; said: string; model: string; tried?: Tried; problem?: string };

const SHOWN = 3000;  // characters of each message shown before it's cut
const STAND_IN = "stand-in";

type CaseLine = { number: number; name: string; file: string; suite_alone: string[] };
type CaseStep = { say: string; reply: string; called: string[]; wrong: string[] };
type CaseRun = { name: string; file: string; ran: boolean; why?: string; passed?: boolean;
                 problems?: string[]; steps?: CaseStep[] };
type Outcome = { running: true } | { problem: string } | { run: CaseRun };

/** A draft's test cases, run in the sandbox one at a time, each in a conversation of its own,
 * as its suite runs them: those that need what the suite alone does, it says so of. */
function Cases({ draft, model, ready, revision }: { draft: string; model: string; ready: boolean; revision: number }) {
  const listed = useLoad(() => get<{ cases: CaseLine[]; problem?: string }>(
    `/studio/api/drafts/${encodeURIComponent(draft)}/cases`), [draft, revision]);
  const [outcomes, setOutcomes] = useState<Record<number, Outcome>>({});
  const [running, setRunning] = useState(false);
  if (listed.error) return <p className="problem">{listed.error}</p>;
  if (!listed.data) return null;
  if (listed.data.problem) return <p className="problem" id="cases">{listed.data.problem}</p>;
  const all = listed.data.cases;
  const runnable = all.filter((c) => c.suite_alone.length === 0);
  const run = async () => {
    setRunning(true);
    setOutcomes({});
    for (const c of runnable) {
      setOutcomes((o) => ({ ...o, [c.number]: { running: true } }));
      try {
        const ran = await send<CaseRun>("POST", `/studio/api/drafts/${encodeURIComponent(draft)}/cases/${c.number}`, { model });
        setOutcomes((o) => ({ ...o, [c.number]: { run: ran } }));
      } catch (e) {
        setOutcomes((o) => ({ ...o, [c.number]: { problem: (e as Error).message } }));
      }
    }
    setRunning(false);
  };
  const ran = Object.values(outcomes).flatMap((o) => ("run" in o && o.run.ran ? [o.run] : []));
  const passed = ran.filter((r) => r.passed).length;
  return (
    <div className="cases" id="cases">
      <div className="cases-head">
        <h4>Its test cases</h4>
        <button type="button" className="quiet" id="run-cases" disabled={!ready || running || runnable.length === 0} onClick={run}>
          {running ? "Running them…" : `Run the ${runnable.length} the sandbox can`}</button>
      </div>
      {all.length === 0 && <p className="note">It has none yet: keep what you said to it as one, above.</p>}
      {all.length > 0 && model === STAND_IN && <p className="note">On the stand-in, a case shows how the draft is wired, not what it would say: run them on a real model for that.</p>}
      {ran.length > 0 && !running && (
        <p id="cases-summary"><span className={`badge ${passed === ran.length ? "good" : "bad"}`}>{passed} of {ran.length} passed</span></p>
      )}
      <ol className="case-list">
        {all.map((c) => {
          const outcome = outcomes[c.number];
          const done = outcome && "run" in outcome ? outcome.run : null;
          return (
            <li key={c.number} className="case">
              <div className="case-line">
                <span className="case-name">{c.name}</span>
                <span className="faint mono">{c.file}</span>
                {c.suite_alone.length > 0 && <span className="badge">its suite alone</span>}
                {outcome && "running" in outcome && <span className="badge">running…</span>}
                {outcome && "problem" in outcome && <span className="badge bad">{outcome.problem}</span>}
                {done && done.ran && <span className={`badge ${done.passed ? "good" : "bad"}`}>{done.passed ? "passed" : "failed"}</span>}
                {done && !done.ran && <span className="badge">not run</span>}
              </div>
              {c.suite_alone.length > 0 && <div className="faint">It needs {c.suite_alone.join(", ")}, which the agent's suite runs, on a stack of its own.</div>}
              {done && !done.ran && <div className="faint">{done.why}</div>}
              {done?.problems && done.problems.length > 0 && (
                <ul className="plain case-problems">{done.problems.map((p) => <li key={p}>{p}</li>)}</ul>
              )}
              {done?.steps && (
                <details className="sent">
                  <summary>What it was told, and answered</summary>
                  {done.steps.map((step, i) => (
                    <div key={i} className="case-step">
                      <div><span className="faint">Told</span> {step.say}</div>
                      <div><span className="faint">Answered</span> {step.reply || "(nothing)"}</div>
                      {step.called.length > 0 && <div className="faint mono">used {step.called.join(", ")}</div>}
                    </div>
                  ))}
                </details>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** The tools a turn's run used, and a5s let it, or held for someone to decide, as an agent's
 * suite counts them. */
function used(tried: Tried): string[] {
  const calls = tried.run?.calls ?? [];
  return [...new Set(calls.filter((c) => c.decision === "hold" || (c.decision === "allow" && c.outcome === "ok"))
    .map((c) => c.tool))];
}

function shown(message: Message): string {
  const text = message.content ?? "";
  const calls = (message.tool_calls ?? []).map((c) => `→ ${c.function.name}(${c.function.arguments})`).join("\n");
  const whole = [text, calls].filter(Boolean).join("\n");
  return whole.length > SHOWN ? `${whole.slice(0, SHOWN)}…` : whole;
}

function Answer({ tried, name }: { tried: Tried; name: string }) {
  const calls = tried.run?.calls ?? [];
  return (
    <div className="try-answer">
      <div className="faint">{name} answered</div>
      <p className="try-reply">{tried.reply || "(nothing)"}</p>
      {calls.length > 0 && (
        <ol className="steps">
          {calls.map((call) => (
            <li key={call.seq} className={`step ${call.decision}`}>
              <span className="mono step-tool">{call.tool}</span>
              <DecisionBadge decision={call.decision} />
              {call.outcome && <span className="badge">{call.outcome}</span>}
              {call.reasons.length > 0 && <div className="faint step-why">{call.reasons.join(", ")}</div>}
            </li>
          ))}
        </ol>
      )}
      {tried.model_calls.length > 0 && (
        <details className="sent">
          <summary>What the model was sent and said, {tried.model_calls.length === 1 ? "once" : `${tried.model_calls.length} times`}</summary>
          {tried.model_calls.map((call, i) => {
            const before = i > 0 ? tried.model_calls[i - 1].sent.messages.length : 0;  // what it was sent last time
            return (
              <div key={i} className="model-call">
                <div className="faint">Call {i + 1}{call.sent.tools ? `, with ${call.sent.tools.length} tools offered` : ""}
                  {before > 0 && `: all call ${i} was sent, then`}</div>
                {call.sent.messages.slice(before).map((m, j) => (
                  <div key={j} className={`said-to role-${m.role}`}><span className="label">{m.role}</span><pre>{shown(m)}</pre></div>
                ))}
              </div>
            );
          })}
        </details>
      )}
    </div>
  );
}

export function TryIt({ draft, name, ready, keep, revision }: {
  draft: string; name: string; ready: boolean; keep: (testCase: Case) => void; revision: number;
}) {
  const offered = useLoad(() => get<Offered>("/studio/api/sandbox"), []);
  const [person, setPerson] = useState("");
  const [model, setModel] = useState("stand-in");
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [caseName, setCaseName] = useState("");
  const [keptCase, setKeptCase] = useState<{ said: string } | { problem: string } | null>(null);
  if (offered.error) return <p className="note" id="no-sandbox">{offered.error}</p>;
  if (!offered.data) return <p className="note">Asking the sandbox…</p>;
  const people = offered.data.people;
  const as = person || people[0]?.id || "";
  const named = (id: string) => people.find((p) => p.id === id)?.name ?? id;
  const say = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || busy) return;
    const turn: Turn = { id: turns.length, as, said: text.trim(), model };
    const settle = (change: Partial<Turn>) => setTurns((all) => all.map((t) => (t.id === turn.id ? { ...t, ...change } : t)));
    setTurns((all) => [...all, turn]);
    setText("");
    setBusy(true);
    try {
      settle({ tried: await send<Tried>("POST", `/studio/api/drafts/${encodeURIComponent(draft)}/try`,
                                        { person: turn.as, text: turn.said, model: turn.model }) });
    } catch (e) {
      settle({ problem: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const theirs = turns.filter((t) => t.as === as && t.tried);  // what this person said, answered
  const keepIt = (event: FormEvent) => {
    event.preventDefault();
    const named = caseName.trim() || theirs[0]?.said.slice(0, 60) || "";
    if (!theirs.length || !named) return;
    try {
      keep({ name: named, as, steps: theirs.map((t) => {
        const uses = t.model === STAND_IN ? [] : used(t.tried as Tried);  // the stand-in's aren't the agent's
        return uses.length ? { say: t.said, uses } : { say: t.said };
      }) });
      setCaseName("");
      setKeptCase({ said: `Kept as ${named}, in ${CASES}.` });
    } catch (e) {
      setKeptCase({ problem: (e as Error).message });
    }
  };
  return (
    <div className="try-it">
      <p className="note">The sandbox is a deployment of its own: its records and its people are made up, and nothing said here reaches anyone's real records. It tries the draft as it was last kept. Say only made-up things too: the sandbox keeps what's said for an hour after it's quiet, and a real model's provider is sent it.</p>
      <div className="field-pair">
        <label className="field"><span>Say it as</span>
          <select id="try-as" value={as} onChange={(e) => setPerson(e.target.value)}>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
        <label className="field"><span>On the model</span>
          <select id="try-model" value={model} onChange={(e) => setModel(e.target.value)}>
            {offered.data.models.map((m) => <option key={m} value={m}>{m === "stand-in" ? "the stand-in, which thinks nothing" : m}</option>)}
          </select></label>
      </div>
      {turns.length > 0 && (
        <ol className="try-turns" aria-live="polite">
          {turns.map((turn) => (
            <li key={turn.id}>
              <div className="try-said"><span className="faint">{named(turn.as)} said</span><p>{turn.said}</p></div>
              {!turn.tried && !turn.problem && <p className="note">The sandbox is running it…</p>}
              {turn.problem && <p className="problem">{turn.problem}</p>}
              {turn.tried && <Answer tried={turn.tried} name={name} />}
            </li>
          ))}
        </ol>
      )}
      {theirs.length > 0 && (
        <form className="try-keep" onSubmit={keepIt}>
          <label className="field"><span>Keep what {named(as)} said to it as a test case, which its suite runs on its model{theirs.some((t) => t.model === STAND_IN) ? ": on the stand-in, what they said alone, since what the stand-in used isn't the agent's choice" : ", with the tools it used"}</span>
            <input id="case-name" value={caseName} placeholder={theirs[0].said.slice(0, 60)}
                   onChange={(e) => setCaseName(e.target.value)} autoComplete="off" /></label>
          <button type="submit" className="quiet" id="keep-case">Keep as a test case</button>
          {keptCase && ("said" in keptCase ? <p className="note" id="case-kept">{keptCase.said}</p>
                                           : <p className="problem">{keptCase.problem}</p>)}
        </form>
      )}
      <form className="try-say" onSubmit={say}>
        <input id="try-text" value={text} placeholder={ready ? "Say something to it" : "Put right what would stop its release first"}
               disabled={!ready} onChange={(e) => setText(e.target.value)} autoComplete="off" />
        <button type="submit" className="primary" disabled={!ready || busy || !text.trim()}>{busy ? "Running…" : "Say it"}</button>
      </form>
      <Cases draft={draft} model={model} ready={ready && !busy} revision={revision} />
    </div>
  );
}
