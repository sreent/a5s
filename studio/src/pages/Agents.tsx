// All the agents someone may watch, as cards: what each does, what it may do, and where it runs.

import { type Agent, type Catalogue, type DraftLine, get } from "../api";
import { Icon } from "../icons";
import { Link } from "../router";
import { aboutInstance, levels, PageHead, plural, risk, StatusBadge, useLoad, Waiting, when } from "../ui";

function counts(agent: Agent): [string, number][] {
  const by = { changes: 0, outside: 0, writes: 0, reads: 0 };
  for (const tool of agent.tools) by[risk(tool)] += 1;
  return (Object.entries(by) as [string, number][]).filter(([, n]) => n > 0);
}

const SAYS: Record<string, string> = { changes: "change", outside: "send out", writes: "write", reads: "read" };

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <article className="agent-card">
      <div className="agent-card-head">
        <span className="agent-glyph"><Icon name="agent" /></span>
        <div>
          <Link to={{ page: "agent", agent: agent.id }} className="agent-name">{agent.id}</Link>
          <div className="mono faint">{agent.release}</div>
        </div>
      </div>
      <p className="clamp">{agent.works_for}</p>
      <div className="chips">
        <span className="chip">{agent.model}</span>
        <span className="chip">{levels(agent.autonomy)}</span>
        {counts(agent).map(([kind, n]) => (
          <span key={kind} className={`badge ${kind}`}>{n} {SAYS[kind]}</span>
        ))}
      </div>
      <div className="card-section">
        <div className="label">Where it runs</div>
        {agent.instances.length === 0 && <p className="note">No instance you may watch runs it.</p>}
        {agent.instances.map((inst) => (
          <Link key={inst.id} to={{ page: "instance", instance: inst.id }} className="instance-row">
            <span className="instance-id">{inst.id}</span>
            <StatusBadge status={inst.status} />
            <span className="faint">{aboutInstance(inst)}</span>
          </Link>
        ))}
      </div>
      <div className="card-foot faint">
        Owned by {agent.owners.join(", ") || "nobody the directory names"} · {plural(agent.tools.length, "tool")}
      </div>
    </article>
  );
}

function Drafts() {
  const { data } = useLoad(() => get<{ drafts: DraftLine[] }>("/studio/api/drafts"), []);
  if (!data || data.drafts.length === 0) return null;
  return (
    <section className="card" id="drafts">
      <h3>Your drafts</h3>
      <ul className="plain">{data.drafts.map((d) => (
        <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
          <span className="faint"> · from {d.based_on} · kept {when(d.updated_at)}</span></li>
      ))}</ul>
    </section>
  );
}

export function AgentsPage() {
  const { data, error } = useLoad(() => get<Catalogue>("/studio/api"), []);
  const authors = data && (data.authoring.new || data.authoring.agents.length > 0);
  return (
    <>
      <PageHead title="Agents"
                about="The agents you may watch: what each does and may do, where it runs, and how each instance is doing. Changes to an instance go through the settings app; the changes agents ask for are decided on the decisions page.">
        {data?.authoring.new && <div className="actions"><Link to={{ page: "new" }} className="button primary">New agent</Link></div>}
      </PageHead>
      {!data && <Waiting error={error} />}
      {authors && <Drafts />}
      {data && data.agents.length === 0 && <p className="note">There are no agents you may watch.</p>}
      {data && <div className="agent-grid">{data.agents.map((a) => <AgentCard key={a.id} agent={a} />)}</div>}
    </>
  );
}
