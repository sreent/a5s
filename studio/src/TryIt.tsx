// Trying a draft in the sandbox, a deployment of a5s of its own: say something to the draft as one
// of the sandbox's made-up people, on its stand-in model or a real one it has, and see what it
// answered, each call it made with the policy's decision, and what the model was sent and said.
// Nothing said here reaches anyone's real records, and nothing of it is kept in this deployment.

import { type FormEvent, useState } from "react";
import { ApiError, type CaseRan, type Cases, get, type Sandbox, type SentMessage, send,
         type Tried } from "./api";
import { type Case, CASES } from "./definition";
import { locale, t } from "./i18n";
import { DecisionBadge, money, useLoad } from "./ui";

type Turn = { id: number; as: string; said: string; model: string; tried?: Tried; problem?: string };

const SHOWN = 3000;  // characters of each message shown before it's cut
const STAND_IN = "stand-in";

type Outcome = { running: true } | { problem: string } | { run: CaseRan };

/** How a model did on a draft's cases: how many it ran and passed, and what they took. */
type Compared = { model: string; ran: number; passed: number; seconds: number; tokens: number;
                  cost: number; unpriced: boolean; problems: number; done: boolean };

/** A draft's cases run on each of the models chosen, one after another, side by side: how many
 * each passed, how long they took, their tokens, and what they cost at each model's prices, in
 * the deployment's currency, so its author picks the cheapest that's good enough. A judge's grade
 * counts as its step's, and the judge is the draft's own on every model. A refusal for the day's
 * tokens, or while the sandbox is busy, stops it, saying so: the rest would be refused too. */
function Compare({ draft, runnable, models, ready, currency }: { draft: string; runnable: { number: number }[];
                                                               models: string[]; ready: boolean; currency: string | null }) {
  const [chosen, setChosen] = useState<string[]>([]);
  const [rows, setRows] = useState<Compared[]>([]);
  const [now, setNow] = useState<string>();
  const [stopped, setStopped] = useState<string>();
  const compare = async () => {
    const found: Compared[] = [];
    let refused: string | undefined;
    setStopped(undefined);
    for (const model of chosen) {
      const row: Compared = { model, ran: 0, passed: 0, seconds: 0, tokens: 0, cost: 0, unpriced: false, problems: 0, done: false };
      found.push(row);
      for (const [i, c] of runnable.entries()) {
        setNow(t("Case {n} of {total} on {model}…", { n: i + 1, total: runnable.length, model }));
        setRows(found.map((r) => ({ ...r })));
        try {
          const ran = await send<CaseRan>("POST", `/studio/api/drafts/${encodeURIComponent(draft)}/cases/${c.number}`, { model });
          if (ran.ran) {
            row.ran += 1;
            row.passed += ran.passed ? 1 : 0;
            row.seconds += ran.seconds ?? 0;
            row.tokens += ran.tokens ?? 0;
            if (ran.cost == null) row.unpriced = true;
            else row.cost += ran.cost;
          }
        } catch (e) {
          row.problems += 1;
          if (e instanceof ApiError && e.status === 429) {
            refused = e.message;
            break;
          }
        }
      }
      row.done = true;
      setRows(found.map((r) => ({ ...r })));
      if (refused) break;
    }
    setStopped(refused);
    setNow(undefined);
  };
  const whole = rows.filter((r) => r.done && r.problems === 0 && r.ran === runnable.length && r.passed === r.ran);
  const cheapest = whole.filter((r) => !r.unpriced).sort((a, b) => a.cost - b.cost)[0];
  const unpriced = whole.filter((r) => r.unpriced).map((r) => r.model);
  return (
    <div className="compare" id="compare-models">
      <h3>{t("Compare models on them")}</h3>
      <p className="note">{t("Run them on each model you choose, one after another, and see how many each passes, how long they take, and what they cost at its prices, to pick the cheapest that's good enough. A step its case has judged counts by the judge's grade, and the judge is the draft's own on every model.")}</p>
      <fieldset className="choice-group column">
        <legend className="hidden">{t("Models to compare")}</legend>
        {models.map((m) => (
          <label key={m} className="choice">
            <input type="checkbox" checked={chosen.includes(m)} disabled={Boolean(now)}
                   onChange={(e) => setChosen(e.target.checked ? [...chosen, m] : chosen.filter((x) => x !== m))} />
            {m}{m === STAND_IN ? t(" (how it's wired, not what it would say)") : ""}
          </label>
        ))}
      </fieldset>
      <button type="button" id="compare-run" disabled={!ready || Boolean(now) || chosen.length < 2 || runnable.length === 0}
              onClick={compare}>{now ?? (chosen.length < 2 ? t("Compare two or more models") : t("Compare {n} models", { n: chosen.length }))}</button>
      {rows.length > 0 && (
        <table className="grid-table compact" id="compare-table">
          <thead><tr><th scope="col">{t("Model")}</th><th scope="col">{t("Passed")}</th><th scope="col">{t("Took")}</th>
                     <th scope="col">{t("Tokens")}</th><th scope="col">{t("Cost, at its prices")}</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.model} data-model={r.model}>
              <th scope="row">{r.model}</th>
              <td><span className={`badge ${!r.done ? "" : r.passed === runnable.length ? "good" : "bad"}`}>{t("{passed} of {total}", { passed: r.passed, total: runnable.length })}</span>
                {r.problems > 0 && <span className="faint"> {t("{n} couldn't run", { n: r.problems })}</span>}</td>
              <td className="num">{t("{seconds} s", { seconds: r.seconds.toFixed(1) })}</td>
              <td className="num">{r.tokens.toLocaleString(locale())}</td>
              <td className="num">{r.unpriced ? t("its prices aren't known") : money(r.cost, currency)}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {!now && rows.length > 0 && (
        <p id="compare-verdict" role="status">{stopped ? t("It stopped: {why}", { why: stopped })
          : cheapest ? t("{model} passed every case for the least: {cost} at its prices.", { model: cheapest.model, cost: money(cheapest.cost, currency) })
            + (unpriced.length ? " " + t("{models} passed every case too, at prices a5s doesn't know.", { models: unpriced.join(", ") }) : "")
          : unpriced.length ? t("{models} passed every case, and a5s doesn't know their prices, so it can't say which costs least: models.yaml gives them.", { models: unpriced.join(", ") })
          : t("No model passed every case.")}</p>
      )}
    </div>
  );
}

/** A draft's test cases, run in the sandbox one at a time, each in a conversation of its own,
 * as its suite runs them: those that need what the suite alone does, it says so of. */
function Cases({ draft, model, ready, revision, models, currency }: { draft: string; model: string; ready: boolean; revision: number;
                                                                       models: string[]; currency: string | null }) {
  const listed = useLoad(() => get<Cases>(
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
        const ran = await send<CaseRan>("POST", `/studio/api/drafts/${encodeURIComponent(draft)}/cases/${c.number}`, { model });
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
        <h3>{t("Its test cases")}</h3>
        <button type="button" id="run-cases" disabled={!ready || running || runnable.length === 0} onClick={run}>
          {running ? t("Running them…") : t("Run the {n} the sandbox can", { n: runnable.length })}</button>
      </div>
      {all.length === 0 && <p className="note">{t("It has none yet: keep what you said to it as one, above.")}</p>}
      {all.length > 0 && model === STAND_IN && <p className="note">{t("On the stand-in, a case shows how the draft is wired, not what it would say: run them on a real model for that.")}</p>}
      {ran.length > 0 && !running && (
        <p id="cases-summary"><span className={`badge ${passed === ran.length ? "good" : "bad"}`}>{t("{passed} of {total} passed", { passed, total: ran.length })}</span></p>
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
                {c.suite_alone.length > 0 && <span className="badge">{t("its suite alone")}</span>}
                {outcome && "running" in outcome && <span className="badge">{t("running…")}</span>}
                {outcome && "problem" in outcome && <span className="badge bad">{outcome.problem}</span>}
                {done && done.ran && <span className={`badge ${done.passed ? "good" : "bad"}`}>{done.passed ? t("passed") : t("failed")}</span>}
                {done && !done.ran && <span className="badge">{t("not run")}</span>}
              </div>
              {c.suite_alone.length > 0 && <div className="faint">{t("It needs {what}, which the agent's suite runs, on a stack of its own.", { what: c.suite_alone.join(", ") })}</div>}
              {done && !done.ran && <div className="faint">{done.why}</div>}
              {done?.problems && done.problems.length > 0 && (
                <ul className="plain case-problems">{done.problems.map((p) => <li key={p}>{p}</li>)}</ul>
              )}
              {done?.steps && (
                <details className="sent">
                  <summary>{t("What it was told, and answered")}</summary>
                  {done.steps.map((step, i) => (
                    <div key={i} className="case-step">
                      <div><span className="faint">{t("Told")}</span> {step.say}</div>
                      <div><span className="faint">{t("Answered")}</span> {step.reply || t("(nothing)")}</div>
                      {step.called.length > 0 && <div className="faint mono">{t("used {tools}", { tools: step.called.join(", ") })}</div>}
                      {step.judged && (
                        <div className="case-judged">
                          <span className="faint">{step.judged.judge === STAND_IN ? t("The stand-in judged it")
                            : step.judged.judge ? t("Its judge, {judge}, found it", { judge: step.judged.judge }) : t("Nobody judged it")}</span>{" "}
                          {step.judged.grade && <span className={`badge ${step.judged.grade === "right" ? "good" : "bad"}`}>{step.judged.grade}</span>}{" "}
                          {step.judged.why}
                        </div>
                      )}
                    </div>
                  ))}
                </details>
              )}
            </li>
          );
        })}
      </ol>
      {runnable.length > 0 && models.length > 1 && <Compare draft={draft} runnable={runnable} models={models} ready={ready && !running} currency={currency} />}
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

// A model's message as the provider's own format has it: its text, and each tool it called, in
// the OpenAI-style form the gateway speaks; anything else of it, as it came
type Called = { function?: { name?: string; arguments?: string } };

function shown(message: SentMessage): string {
  const said = message.content;
  const text = typeof said === "string" ? said : said == null ? "" : JSON.stringify(said);
  const calls = ((message.tool_calls ?? []) as Called[])
    .map((c) => `→ ${c.function?.name}(${c.function?.arguments ?? ""})`).join("\n");
  const whole = [text, calls].filter(Boolean).join("\n");
  return whole.length > SHOWN ? `${whole.slice(0, SHOWN)}…` : whole;
}

function Answer({ tried, name }: { tried: Tried; name: string }) {
  const calls = tried.run?.calls ?? [];
  return (
    <div className="try-answer">
      <div className="faint">{t("{name} answered", { name })}</div>
      <p className="try-reply">{tried.reply || t("(nothing)")}</p>
      {calls.length > 0 && (
        <ol className="run-calls">
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
          <summary>{tried.model_calls.length === 1 ? t("What the model was sent and said, once")
            : t("What the model was sent and said, {n} times", { n: tried.model_calls.length })}</summary>
          {tried.model_calls.map((call, i) => {
            const before = i > 0 ? tried.model_calls[i - 1].sent.messages.length : 0;  // what it was sent last time
            return (
              <div key={i} className="model-call">
                <div className="faint">{call.sent.tools
                  ? (before > 0 ? t("Call {n}, with {tools} tools offered: all call {before} was sent, then", { n: i + 1, tools: call.sent.tools.length, before: i })
                    : t("Call {n}, with {tools} tools offered", { n: i + 1, tools: call.sent.tools.length }))
                  : (before > 0 ? t("Call {n}: all call {before} was sent, then", { n: i + 1, before: i }) : t("Call {n}", { n: i + 1 }))}</div>
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

/** Words apart by commas, as a list, each once. */
function words(text: string): string[] {
  return [...new Set(text.split(",").map((w) => w.trim()).filter(Boolean))];
}

export function TryIt({ draft, name, ready, keep, revision, acts }: {
  draft: string; name: string; ready: boolean; keep: (testCase: Case) => void; revision: number;
  acts: string[];  // its tools that change, write or send something: what a case may say it must never use
}) {
  const offered = useLoad(() => get<Sandbox>("/studio/api/sandbox"), []);
  const [person, setPerson] = useState("");
  const [model, setModel] = useState("stand-in");
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [caseName, setCaseName] = useState("");
  const [neverUses, setNeverUses] = useState<string[]>([]);
  const [neverSays, setNeverSays] = useState("");
  const [judged, setJudged] = useState("");
  const [keptCase, setKeptCase] = useState<{ said: string } | { problem: string } | null>(null);
  if (offered.error) return <p className="note" id="no-sandbox">{offered.error}</p>;
  if (!offered.data) return <p className="note">{t("Asking the sandbox…")}</p>;
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
    const avoids = acts.filter((t) => neverUses.includes(t));
    const never = words(neverSays);
    try {
      const right = judged.trim();
      keep({ name: named, as, steps: theirs.map((t, i) => {
        const uses = t.model === STAND_IN ? [] : used(t.tried as Tried);  // the stand-in's aren't the agent's
        return { say: t.said, ...(uses.length ? { uses } : {}), ...(avoids.length ? { avoids } : {}),
                 ...(never.length ? { never_says: never } : {}),
                 ...(right && i === theirs.length - 1 ? { judged: right } : {}) };  // what it came to
      }) });
      setCaseName("");
      setNeverUses([]);
      setNeverSays("");
      setJudged("");
      setKeptCase({ said: t("Kept as {name}, in {file}.", { name: named, file: CASES }) });
    } catch (e) {
      setKeptCase({ problem: (e as Error).message });
    }
  };
  return (
    <div className="try-it">
      <p className="note">{t("The sandbox is a deployment of its own: its records and its people are made up, and nothing said here reaches anyone's real records. It tries the draft as it was last kept. Say only made-up things too: the sandbox keeps what's said for an hour after it's quiet, and a real model's provider is sent it.")}</p>
      <div className="field-pair">
        <label className="field"><span>{t("Say it as")}</span>
          <select id="try-as" value={as} onChange={(e) => setPerson(e.target.value)}>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
        <label className="field"><span>{t("On the model")}</span>
          <select id="try-model" value={model} onChange={(e) => setModel(e.target.value)}>
            {offered.data.models.map((m) => <option key={m} value={m}>{m === "stand-in" ? t("the stand-in, which thinks nothing") : m}</option>)}
          </select></label>
      </div>
      {turns.length > 0 && (
        <ol className="try-turns" aria-live="polite">
          {turns.map((turn) => (
            <li key={turn.id}>
              <div className="try-said"><span className="faint">{t("{name} said", { name: named(turn.as) })}</span><p>{turn.said}</p></div>
              {!turn.tried && !turn.problem && <p className="note">{t("The sandbox is running it…")}</p>}
              {turn.problem && <p className="problem">{turn.problem}</p>}
              {turn.tried && <Answer tried={turn.tried} name={name} />}
            </li>
          ))}
        </ol>
      )}
      {theirs.length > 0 && (
        <form className="try-keep" onSubmit={keepIt}>
          <label className="field"><span>{theirs.some((turn) => turn.model === STAND_IN)
            ? t("Keep what {name} said to it as a test case, which its suite runs on its model: on the stand-in, what they said alone, since what the stand-in used isn't the agent's choice", { name: named(as) })
            : t("Keep what {name} said to it as a test case, which its suite runs on its model, with the tools it used", { name: named(as) })}</span>
            <input id="case-name" value={caseName} placeholder={theirs[0].said.slice(0, 60)}
                   onChange={(e) => setCaseName(e.target.value)} autoComplete="off" /></label>
          {acts.length > 0 && (
            <fieldset className="wb-field" id="never-uses">
              <legend className="wb-label">{t("Tools it must never use here, whatever it's told")}</legend>
              <div className="choices inline">
                {acts.map((tool) => (
                  <label key={tool} className="choice">
                    <input type="checkbox" checked={neverUses.includes(tool)}
                           onChange={(e) => setNeverUses((all) => (e.target.checked ? [...all, tool] : all.filter((t) => t !== tool)))} />
                    <span className="mono">{tool}</span></label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="field"><span>{t("Words it must never say, apart by commas")}</span>
            <input id="never-says" value={neverSays} placeholder={t("such as: closed, I've reset")}
                   onChange={(e) => setNeverSays(e.target.value)} autoComplete="off" /></label>
          <label className="field"><span>{t("What a right answer is, in your words, where it can be right in more than one way: its judge grades it, beside the checks above")}</span>
            <textarea id="judged" rows={2} value={judged}
                      placeholder={t("such as: it proposes \"EA\" as the base unit, with correct_value, and says the owner decides it")}
                      onChange={(e) => setJudged(e.target.value)} />
            <span className="wb-hint">{t("The stand-in judges by words alone: the words you quote, and the tools you name. The draft's own judge reads what you mean.")}</span></label>
          <button type="submit" id="keep-case">{t("Keep as a test case")}</button>
          {keptCase && ("said" in keptCase ? <p className="note" id="case-kept">{keptCase.said}</p>
                                           : <p className="problem">{keptCase.problem}</p>)}
        </form>
      )}
      <form className="try-say" onSubmit={say}>
        <input id="try-text" value={text} placeholder={ready ? t("Say something to it") : t("Put right what would stop its release first")}
               disabled={!ready} onChange={(e) => setText(e.target.value)} autoComplete="off" />
        <button type="submit" className="primary" disabled={!ready || busy || !text.trim()}>{busy ? t("Running…") : t("Say it")}</button>
      </form>
      <Cases draft={draft} model={model} ready={ready && !busy} revision={revision} models={offered.data?.models ?? []} currency={offered.data?.currency ?? null} />
    </div>
  );
}
