// Starting a new agent: from one of the agents a5s ships, the reference agents and each
// scenario's, as `a5s agent new` makes one, or from what it's for, in its author's own words,
// for the sandbox's model to propose what it needs, and code to give it the least of that. It's a
// draft, kept for the person who started it, until they publish it as a pull request, which the
// people its first release needs sign.

import { type FormEvent, useState } from "react";
import { type Draft, send, get, type Sandbox, type Templates } from "../api";
import { go } from "../router";
import { PageHead, useLoad, Waiting } from "../ui";

const NAME = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

export function NewPage() {
  const { data, error } = useLoad(() => get<Templates>("/studio/api/templates"), []);
  const sandbox = useLoad(() => get<Sandbox>("/studio/api/sandbox"), []);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState("");
  const [words, setWords] = useState("");
  const [model, setModel] = useState("stand-in");
  const [problem, setProblem] = useState<string>();
  const [making, setMaking] = useState(false);
  const start = async (how: { template: string } | { describe: string; model: string }) => {
    setMaking(true);
    setProblem(undefined);
    try {
      const draft = await send<Draft>("POST", "/studio/api/drafts", { name, ...how });
      go({ page: "draft", draft: draft.id });
    } catch (e) {
      setProblem((e as Error).message);
      setMaking(false);
    }
  };
  const make = (event: FormEvent) => {
    event.preventDefault();
    void start({ template: chosen });
  };
  const named = NAME.test(name) && name.length <= 40;
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } }]} title="A new agent"
                about="Start from one of the agents a5s ships. It's a draft, yours alone, until you publish it as a pull request: nothing runs it, and its first release needs the release approver." />
      {!data && <Waiting error={error} />}
      {data && (
        <form className="new-agent" onSubmit={make}>
          <section className="card">
            <h2>Its name</h2>
            <label className="field">
              <span>Lower case letters and digits, with single hyphens between</span>
              <input id="agent-name" value={name} placeholder="finance-helper" autoComplete="off"
                     onChange={(e) => setName(e.target.value.trim())} />
            </label>
          </section>
          <section className="card">
            <h2>Start from</h2>
            <div className="template-grid" role="radiogroup" aria-label="Start from">
              {data.templates.map((t) => (
                <label key={t.name} className={`template${t.lacks.length ? " lacking" : ""}${chosen === t.name ? " chosen" : ""}`}>
                  <input type="radio" name="template" value={t.name} disabled={t.lacks.length > 0}
                         checked={chosen === t.name} onChange={() => setChosen(t.name)} />
                  <span className="template-name mono">{t.name}</span>
                  <span className="template-for">{t.works_for}</span>
                  <span className="faint">{t.tools.length} tools · {t.model}</span>
                  {t.lacks.length > 0 && <span className="faint">needs {t.lacks.join(", ")}, which this scenario hasn't got</span>}
                </label>
              ))}
            </div>
          </section>
          {problem && <p className="problem" role="alert">{problem}</p>}
          <button type="submit" id="make" disabled={!named || !chosen || making}>
            {making ? "Making it…" : "Make the draft"}
          </button>
          <section className="card" aria-labelledby="describe-title">
            <h2 id="describe-title">Or describe it</h2>
            {sandbox.error && <p className="note" id="no-describing">Describing it needs the sandbox, which drafts it there: {sandbox.error}</p>}
            {sandbox.data && (
              <>
                <p className="note">Say what it's for, in your own words. The sandbox's model proposes what it needs of what this
                  scenario offers, and a5s gives it the least of that, never level 2, each with the reason, for you to check and
                  change by hand. What you write goes to the model you choose, as what's said in the sandbox does.</p>
                <label className="field"><span>What it's for, and for whom</span>
                  <textarea id="describe" rows={4} value={words} maxLength={2000}
                            placeholder="Tracks each new joiner's equipment and access requests in the ITSM against their start date, and answers their questions before day one."
                            onChange={(e) => setWords(e.target.value)} /></label>
                <label className="field"><span>On the model</span>
                  <select id="describe-model" value={model} onChange={(e) => setModel(e.target.value)}>
                    {sandbox.data.models.map((m) => <option key={m} value={m}>{m === "stand-in" ? "the stand-in, which thinks nothing" : m}</option>)}
                  </select></label>
                <button type="button" id="describe-it" disabled={!named || !words.trim() || making}
                        onClick={() => void start({ describe: words.trim(), model })}>
                  {making ? "Drafting it…" : "Draft it from my words"}</button>
              </>
            )}
          </section>
        </form>
      )}
    </>
  );
}
