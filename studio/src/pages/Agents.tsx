// The catalogue: every agent someone may know exists, as cards, each as far as the layers they
// see of it go: what it does and who owns it, what it may do, and where it runs.

import { type AgentKnown, type AgentUses, type Catalogue, type DraftLine, type Drafts, get,
         usesOf } from "../api";
import { Icon } from "../icons";
import { Link } from "../router";
import { aboutInstance, levels, PageHead, plural, risk, StatusBadge, useLoad, Waiting, when } from "../ui";

function counts(agent: AgentUses): [string, number][] {
  const by = { changes: 0, outside: 0, writes: 0, reads: 0 };
  for (const tool of agent.tools) by[risk(tool)] += 1;
  return (Object.entries(by) as [string, number][]).filter(([, n]) => n > 0);
}

const SAYS: Record<string, string> = { changes: "change", outside: "send out", writes: "write", reads: "read" };

function AgentCard({ agent }: { agent: AgentKnown }) {
  const uses = usesOf(agent) ? agent : undefined;
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
      {agent.why && agent.why.length > 0 && <p className="why faint">{agent.why.join(" · ")}</p>}
      {uses && (
        <div className="chips">
          <span className="chip">{uses.model}</span>
          <span className="chip">{levels(uses.autonomy)}</span>
          {counts(uses).map(([kind, n]) => (
            <span key={kind} className={`badge ${kind}`}>{n} {SAYS[kind]}</span>
          ))}
        </div>
      )}
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
        Owned by {agent.owners.join(", ") || "nobody the directory names"}
        {uses && <> · {plural(uses.tools.length, "tool")}</>}
      </div>
    </article>
  );
}

function DraftList({ drafts }: { drafts: DraftLine[] }) {
  return (
    <ul className="plain">{drafts.map((d) => (
      <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
        <span className="faint">{d.author && ` · ${d.author}'s`} · from {d.based_on} · kept {when(d.updated_at)}</span>
        {d.published && <> <a href={d.published} target="_blank" rel="noopener noreferrer" className="badge good">published</a></>}</li>
    ))}</ul>
  );
}

function Drafts() {
  const { data } = useLoad(() => get<Drafts>("/studio/api/drafts"), []);
  if (!data || data.drafts.length + data.theirs.length === 0) return null;
  return (
    <section className="card" id="drafts">
      {data.drafts.length > 0 && <><h3>Your drafts</h3><DraftList drafts={data.drafts} /></>}
      {data.theirs.length > 0 && (
        <div id="co-drafts">
          <h3>Your co-authors' drafts</h3>
          <p className="note">Of the agents you may author too: read them, or copy one into a draft of your own.</p>
          <DraftList drafts={data.theirs} />
        </div>
      )}
    </section>
  );
}

export function AgentsPage() {
  const { data, error } = useLoad(() => get<Catalogue>("/studio/api"), []);
  const authors = data && (data.authoring.new || data.authoring.agents.length > 0);
  return (
    <>
      <PageHead title="Agents"
                about="The agents you may know of: those you have a role on, those that serve you, and those their owners list for everyone. Each shows as much as your roles let you see: what it does and who owns it, what it may do, and where it runs. Changes to an instance go through the settings app; the changes agents ask for are decided on the decisions page.">
        {data?.authoring.new && <div className="actions"><Link to={{ page: "new" }} className="button primary">New agent</Link></div>}
      </PageHead>
      {!data && <Waiting error={error} />}
      {authors && <Drafts />}
      {data && data.agents.length === 0 && <p className="note">There are no agents you may know of yet.</p>}
      {data && <div className="agent-grid">{data.agents.map((a) => <AgentCard key={a.id} agent={a} />)}</div>}
    </>
  );
}
