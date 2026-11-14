// One agent, as its release defines it: its map, what it's for, its tools by what they do, when
// it works, what it knows, its budget, and where it runs.

import { useState } from "react";
import { type Agent, ApiError, type Catalogue, type Draft, type DraftLine, get, send } from "../api";
import { AgentMap } from "../AgentMap";
import { go, Link } from "../router";
import { aboutInstance, levels, PageHead, people, type Risk, risk, RISK_NAMES, runners, StatusBadge,
         ToolBadges, triggers, useLoad, Waiting } from "../ui";

const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];

function Tools({ agent }: { agent: Agent }) {
  return (
    <section className="card">
      <h3>Tools</h3>
      {ORDER.map((kind) => {
        const these = agent.tools.filter((t) => risk(t) === kind);
        if (!these.length) return null;
        return (
          <div key={kind} className="tool-group">
            <div className={`label tone-${kind}`}>{RISK_NAMES[kind]}</div>
            {these.map((tool) => (
              <div key={tool.name} className="tool-row">
                <div className="tool-name"><span className="mono">{tool.name}</span><span className="faint"> · {tool.group}</span></div>
                {tool.description && <div className="tool-about">{tool.description}</div>}
                <ToolBadges tool={tool} />
              </div>
            ))}
          </div>
        );
      })}
      {agent.a5s_tools.length > 0 && (
        <div className="tool-group">
          <div className="label tone-own">a5s's own</div>
          <p className="note">Tasks, reminders, notes and asking other agents, each held to a5s's own rules.</p>
          <div className="chips">{agent.a5s_tools.map((t) => <span key={t} className="chip mono">{t}</span>)}</div>
        </div>
      )}
    </section>
  );
}

function When({ agent }: { agent: Agent }) {
  return (
    <section className="card">
      <h3>When it works</h3>
      <dl className="facts">
        <dt>Starts on</dt><dd>{triggers(agent).map((t) => `${t.kind}, ${t.about}`).join("; ") || "nothing"}</dd>
        <dt>Channels</dt><dd>{agent.channels.join(", ") || "none"}</dd>
        {agent.schedules.map((s) => (
          <div key={s.name} className="fact-pair">
            <dt>{s.name}</dt>
            <dd>{s.at.join(", ")} on {s.days.length === 7 ? "every day" : s.days.join(", ")}<div className="faint">{s.task}</div></dd>
          </div>
        ))}
        <dt>Reports</dt><dd>{agent.reports.join(", ") || "none"}</dd>
        <dt>Chases</dt><dd>{agent.obligations.join(", ") || "nothing people owe"}</dd>
        <dt>Reminders</dt><dd>{agent.reminders ? "keeps the reminders people ask for" : "none"}</dd>
      </dl>
    </section>
  );
}

// What each run may do beside its tools, as the release's context says (definitions.Context)
const ABILITIES: Record<string, string> = {
  recall: "search its conversations",
  documents: "ask about documents from outside",
  agents: "ask other agents",
  notebook: "keep a notebook",
};

function Knows({ agent }: { agent: Agent }) {
  const { budget_tokens: conversation, ...rest } = agent.context;
  const may = Object.keys(ABILITIES).filter((key) => rest[key] === true).map((key) => ABILITIES[key]);
  const not = Object.keys(ABILITIES).filter((key) => rest[key] === false).map((key) => ABILITIES[key]);
  const other = Object.entries(rest).filter(([key]) => !(key in ABILITIES));
  return (
    <section className="card">
      <h3>What it knows, and may spend</h3>
      <dl className="facts">
        <dt>Skills</dt><dd>{agent.skills.join(", ") || "none"}</dd>
        {typeof conversation === "number" && (
          <div className="fact-pair"><dt>Its conversation</dt><dd>up to {conversation.toLocaleString()} tokens of it each run</dd></div>
        )}
        {may.length > 0 && <div className="fact-pair"><dt>It may</dt><dd>{may.join(", ")}</dd></div>}
        {not.length > 0 && <div className="fact-pair"><dt>It may not</dt><dd>{not.join(", ")}</dd></div>}
        {other.map(([key, value]) => (
          <div key={key} className="fact-pair">
            <dt>{key.replace(/_/g, " ")}</dt>
            <dd>{typeof value === "boolean" ? (value ? "yes" : "no") : String(value)}</dd>
          </div>
        ))}
        <dt>Each run</dt><dd>up to {agent.budget.per_run.toLocaleString()} tokens</dd>
        <dt>Each person, each day</dt><dd>up to {agent.budget.per_person_per_day.toLocaleString()} tokens</dd>
      </dl>
    </section>
  );
}

function Where({ agent }: { agent: Agent }) {
  return (
    <section className="card wide">
      <h3>Where it runs</h3>
      {agent.instances.length === 0 && <p className="note">No instance you may watch runs it.</p>}
      {agent.instances.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Instance</th><th>Status</th><th>Level</th><th>Parts</th><th>Serves</th><th>Run by</th><th>Release</th></tr></thead>
          <tbody>
            {agent.instances.map((inst) => (
              <tr key={inst.id}>
                <td><Link to={{ page: "instance", instance: inst.id }}>{inst.id}</Link></td>
                <td><StatusBadge status={inst.status} /></td>
                <td>{inst.level}</td>
                <td>{Object.keys(inst.parts).join(", ") || "none"}</td>
                <td>{people(inst.people)}</td>
                <td>{runners(inst)}</td>
                <td>{inst.current ? "this one" : <span className="badge warn">still {inst.release}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DraftAChange({ id }: { id: string }) {
  const [problem, setProblem] = useState<string>();
  const start = async () => {
    try {
      const draft = await send<Draft>("POST", "/studio/api/drafts", { agent: id });
      go({ page: "draft", draft: draft.id });
    } catch (e) {
      const mine = e instanceof ApiError && e.status === 409  // theirs already: carry on with it
        && (await get<{ drafts: DraftLine[] }>("/studio/api/drafts")).drafts.find((d) => d.agent === id);
      if (mine) go({ page: "draft", draft: mine.id });
      else setProblem((e as Error).message);
    }
  };
  return (
    <div className="actions">
      <button type="button" className="primary" id="draft-change" onClick={start}>Draft a change</button>
      {problem && <span className="problem">{problem}</span>}
    </div>
  );
}

export function AgentPage({ id }: { id: string }) {
  const { data: agent, error } = useLoad(() => get<Agent>(`/studio/api/agents/${encodeURIComponent(id)}`), [id]);
  const catalogue = useLoad(() => get<Catalogue>("/studio/api"), []);
  const changes = catalogue.data?.authoring.agents.includes(id) ?? false;
  return (
    <>
      <PageHead crumbs={[{ label: "Agents", to: { page: "agents" } }]} title={id}
                about={agent?.works_for}
                badges={agent && <span className="chip mono">{agent.release}</span>}>
        {agent && (
          <div className="meta">
            <span>{agent.model}</span><span>{levels(agent.autonomy)}</span>
            <span>Owned by {agent.owners.join(", ") || "nobody the directory names"}</span>
            {agent.instances.map((i) => <span key={i.id}>{i.id}: {aboutInstance(i)}</span>)}
          </div>
        )}
        {agent && changes && <DraftAChange id={id} />}
      </PageHead>
      {!agent && <Waiting error={error} />}
      {agent && (
        <>
          <section className="card map-card">
            <h3>How it's wired</h3>
            <p className="note">What starts its runs, and the tools it may call, each through a5s's checks. Changes to records wait for a person to decide at level 1.</p>
            <AgentMap agent={agent} />
          </section>
          <div className="agent-body">
            <div>
              <section className="card">
                <h3>What it does</h3>
                <p>{agent.does}</p>
                {agent.instructions && (
                  <details>
                    <summary>Its instructions</summary>
                    <pre className="instructions">{agent.instructions}</pre>
                  </details>
                )}
              </section>
              <Tools agent={agent} />
            </div>
            <div className="side">
              <When agent={agent} />
              <Knows agent={agent} />
            </div>
          </div>
          <Where agent={agent} />
        </>
      )}
    </>
  );
}
