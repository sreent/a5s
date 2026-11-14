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

export function TryIt({ draft, name, ready, keep }: {
  draft: string; name: string; ready: boolean; keep: (testCase: Case) => void;
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
    </div>
  );
}
