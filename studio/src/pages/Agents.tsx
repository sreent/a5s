// The catalogue: every agent someone may know exists, as cards, each as far as the layers they
// see of it go: what it does and who owns it, what it may do, and where it runs.

import { type AgentKnown, type AgentUses, type Catalogue, type DraftLine, type Drafts, get,
         usesOf } from "../api";
import { Shapes } from "../design";
import { t } from "../i18n";
import { Icon } from "../icons";
import { Link } from "../router";
import { aboutInstance, levels, PageHead, plural, risk, StatusBadge, useLoad, Waiting, when } from "../ui";

function counts(agent: AgentUses): [string, number][] {
  const by = { changes: 0, outside: 0, writes: 0, reads: 0 };
  for (const tool of agent.tools) by[risk(tool)] += 1;
  return (Object.entries(by) as [string, number][]).filter(([, n]) => n > 0);
}

// How many of its tools do each, in words
const SAYS: Record<string, (n: number) => string> = {
  changes: (n) => t("{n} change", { n }), outside: (n) => t("{n} send out", { n }),
  writes: (n) => t("{n} write", { n }), reads: (n) => t("{n} read", { n }),
};

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
      <p className="clamp">{agent.does}</p>
      {agent.why && agent.why.length > 0 && <p className="why faint">{agent.why.join(" · ")}</p>}
      {uses && (
        <div className="chips">
          <span className="chip">{uses.model}</span>
          <span className="chip">{levels(uses.autonomy)}</span>
          {counts(uses).map(([kind, n]) => (
            <span key={kind} className={`badge ${kind}`}>{SAYS[kind](n)}</span>
          ))}
        </div>
      )}
      <div className="card-section">
        <div className="label">{t("Where it runs")}</div>
        {agent.instances.length === 0 && <p className="note">{t("No instance you may watch runs it.")}</p>}
        {agent.instances.map((inst) => (
          <Link key={inst.id} to={{ page: "instance", instance: inst.id }} className="instance-row">
            <span className="instance-id">{inst.id}</span>
            <StatusBadge status={inst.status} />
            <span className="faint">{aboutInstance(inst)}</span>
          </Link>
        ))}
      </div>
      <div className="card-foot faint">
        {t("Owned by {owners}", { owners: agent.owners.join(", ") || t("nobody the directory names") })}
        {uses && <> · {plural(uses.tools.length, "tool")}</>}
      </div>
    </article>
  );
}

function DraftList({ drafts }: { drafts: DraftLine[] }) {
  return (
    <ul className="plain">{drafts.map((d) => (
      <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
        <span className="faint">{d.author && ` · ${t("{author}'s", { author: d.author })}`} · {t("from {release} · kept {when}", { release: d.based_on ?? "", when: when(d.updated_at) })}</span>
        {d.published && <> <a href={d.published} target="_blank" rel="noopener noreferrer" className="badge good">{t("published")}</a></>}</li>
    ))}</ul>
  );
}

function Drafts() {
  const { data } = useLoad(() => get<Drafts>("/studio/api/drafts"), []);
  if (!data || data.drafts.length + data.theirs.length === 0) return null;
  return (
    <section className="card" id="drafts">
      {data.drafts.length > 0 && <><h2>{t("Your drafts")}</h2><DraftList drafts={data.drafts} /></>}
      {data.theirs.length > 0 && (
        <div id="co-drafts">
          <h2>{t("Your co-authors' drafts")}</h2>
          <p className="note">{t("Of the agents you may author too: read them, or copy one into a draft of your own.")}</p>
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
      <PageHead title={t("Agents")}
                about={t("The agents you may know of: those you have a role on, those that serve you, and those their owners list for everyone. Each shows as much as your roles let you see: what it does and who owns it, what it may do, and where it runs. Changes to an instance go through the settings; the changes agents ask for are decided on the decisions page.")}>
        {data?.authoring.new && <div className="actions"><Link to={{ page: "new" }} className="button primary">{t("New agent")}</Link></div>}
        {data && !data.authoring.new && (  /* where the button would be: who may start one */
          <p className="meta" id="who-builds"><span>{t("A new agent is started by an agent's owner or someone in the team that runs a5s.")}</span>
            <Link to={{ page: "home" }}>{t("How to build one")}</Link></p>
        )}
      </PageHead>
      {!data && (
        <Waiting error={error}>
          <div className="agent-grid">  {/* the grid it will be, still (round 13, C11) */}
            {[0, 1, 2, 3, 4, 5].map((n) => <section key={n} className="card"><Shapes lines={3} /></section>)}
          </div>
        </Waiting>
      )}
      {authors && <Drafts />}
      {data && data.agents.length === 0 && (  /* whom to ask, where a newcomer lands (round 17, C4) */
        <p className="note" id="none-yet">{t("There are no agents you may know of yet. An agent's owners list it here, for anyone to ask for; until one does, ask your manager, or whoever runs a5s in your organisation, which agent would serve you.")}</p>
      )}
      {data && <div className="agent-grid">{data.agents.map((a) => <AgentCard key={a.id} agent={a} />)}</div>}
    </>
  );
}
