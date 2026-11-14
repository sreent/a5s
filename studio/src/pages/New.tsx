// Starting a new agent: from one of the agents a5s ships, the reference agents and each
// scenario's, as `a5s agent new` makes one. It's a draft, kept for the person who started it,
// until they publish it as a pull request, which the people its first release needs sign.

import { type FormEvent, useState } from "react";
import { type Draft, send, get, type Template } from "../api";
import { go } from "../router";
import { PageHead, useLoad, Waiting } from "../ui";

const NAME = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

export function NewPage() {
  const { data, error } = useLoad(() => get<{ templates: Template[] }>("/studio/api/templates"), []);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState("");
  const [problem, setProblem] = useState<string>();
  const [making, setMaking] = useState(false);
  const make = async (event: FormEvent) => {
    event.preventDefault();
    setMaking(true);
    setProblem(undefined);
    try {
      const draft = await send<Draft>("POST", "/studio/api/drafts", { name, template: chosen });
      go({ page: "draft", draft: draft.id });
    } catch (e) {
      setProblem((e as Error).message);
      setMaking(false);
    }
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
            <h3>Its name</h3>
            <label className="field">
              <span>Lower case letters and digits, with single hyphens between</span>
              <input id="agent-name" value={name} placeholder="finance-helper" autoComplete="off"
                     onChange={(e) => setName(e.target.value.trim())} />
            </label>
          </section>
          <section className="card">
            <h3>Start from</h3>
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
        </form>
      )}
    </>
  );
}
