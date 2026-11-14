// All the agents someone may watch, as cards: what each does, what it may do, and where it runs.

import { type Agent, type Catalogue, get } from "../api";
import { Icon } from "../icons";
import { Link } from "../router";
import { aboutInstance, levels, PageHead, plural, risk, StatusBadge, useLoad, Waiting } from "../ui";

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

export function AgentsPage() {
  const { data, error } = useLoad(() => get<Catalogue>("/studio/api"), []);
  return (
    <>
      <PageHead title="Agents"
                about="The agents you may watch: what each does and may do, where it runs, and how each instance is doing. Changes to an instance go through the settings app; the changes agents ask for are decided on the decisions page." />
      {!data && <Waiting error={error} />}
      {data && data.agents.length === 0 && <p className="note">There are no agents you may watch.</p>}
      {data && <div className="agent-grid">{data.agents.map((a) => <AgentCard key={a.id} agent={a} />)}</div>}
    </>
  );
}
