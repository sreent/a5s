// One agent, as its release defines it: its map, what it's for, its facts and its ladder of
// autonomy, its tools by what they do, when it works, what it knows, its budget, and where it runs.

import { useEffect, useState } from "react";
import { type AgentKnown, type AgentUses, ApiError, builtOf, type Catalogue, type Draft,
         type Drafts, get, send, usesOf } from "../api";
import { AgentMap } from "../AgentMap";
import { SaidWrong } from "../SaidWrong";
import { AgentFacts, AutonomyLadder, useToast } from "../design";
import { locale, t } from "../i18n";
import { go, Link } from "../router";
import { mayUse, shellOf } from "../Sidebar";
import { aboutInstance, levels, PageHead, people, type Risk, risk, RISK_NAMES, runners, StatusBadge,
         sentence, together, ToolBadges, triggers, useLoad, Waiting, when, Wide } from "../ui";

const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];

/** Its label: what it may do, from its release alone, and what it may spend. */
function Facts({ agent, uses }: { agent: AgentKnown; uses: AgentUses }) {
  const named = (keep: (tool: AgentUses["tools"][number]) => boolean) =>
    uses.tools.filter(keep).map((tool) => tool.name).join(", ") || t("none");
  return (
    <section className="card" aria-label={t("Agent facts")}>
      <AgentFacts name={agent.id} version={agent.release}
        facts={[[t("Model"), uses.model], [t("Autonomy"), levels(uses.autonomy)],
          [t("Only reads"), named((tool) => !!tool.reads && !tool.writes && !tool.changes && !tool.destructive)],
          [t("Writes"), named((tool) => !!tool.writes && !tool.changes)],
          [t("Changes"), named((tool) => !!tool.changes || !!tool.destructive)],
          [t("Sends outside"), named((tool) => !!tool.sends_outside)],
          [t("Reads outside content"), named((tool) => tool.outside.length > 0 || tool.marks)]]}
        more={{ title: t("It may spend"), aside: t("tokens"), rows: [
          [t("In a run"), uses.budget.per_run.toLocaleString(locale())],
          [t("For each person, each day"), uses.budget.per_person_per_day.toLocaleString(locale())]] }}
        foot={t("Owned by {owners}.", { owners: together(agent.owners) || t("nobody yet") })} />
    </section>
  );
}

/** Its ladder of autonomy, where every instance of it works at one level: which that is, and
 * how far its release lets it go. */
function Ladder({ agent, uses }: { agent: AgentKnown; uses: AgentUses }) {
  const at = [...new Set(agent.instances.map((instance) => instance.level))];
  if (at.length !== 1) return null;  // none, or at different levels: each is in Where it runs
  return (
    <section className="card">
      <h2>{t("Autonomy")}</h2>
      <AutonomyLadder level={at[0]} max={uses.autonomy.max} />
    </section>
  );
}

function Tools({ agent }: { agent: AgentUses }) {
  return (
    <section className="card">
      <h2>{t("Tools")}</h2>
      {ORDER.map((kind) => {
        const these = agent.tools.filter((tool) => risk(tool) === kind);
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
          <div className="label tone-own">{t("a5s's own")}</div>
          <p className="note">{t("Tasks, reminders, notes and asking other agents, each held to a5s's own rules.")}</p>
          <div className="chips">{agent.a5s_tools.map((name) => <span key={name} className="chip mono">{name}</span>)}</div>
        </div>
      )}
    </section>
  );
}

function When({ agent }: { agent: AgentUses }) {
  return (
    <section className="card">
      <h2>{t("When it works")}</h2>
      <dl className="facts">
        <dt>{t("Starts on")}</dt><dd>{triggers(agent).map((trigger) => `${trigger.kind}, ${trigger.about}`).join("; ") || t("nothing")}</dd>
        <dt>{t("Channels")}</dt><dd>{agent.channels.join(", ") || t("none")}</dd>
        {agent.schedules.map((s) => (
          <div key={s.name} className="fact-pair">
            <dt>{s.name}</dt>
            <dd>{t("{at} on {days}", { at: s.at.join(", "), days: s.days.length === 7 ? t("every day") : s.days.join(", ") })}<div className="faint">{s.task}</div></dd>
          </div>
        ))}
        <dt>{t("Reports")}</dt><dd>{agent.reports.join(", ") || t("none")}</dd>
        <dt>{t("Chases")}</dt><dd>{agent.obligations.join(", ") || t("nothing people owe")}</dd>
        <dt>{t("Reminders")}</dt><dd>{agent.reminders ? t("keeps the reminders people ask for") : t("none")}</dd>
      </dl>
    </section>
  );
}

// What each run may do beside its tools, as the release's context says (definitions.Context)
type Ability = Exclude<keyof AgentUses["context"], "budget_tokens">;
const ABILITIES: Record<Ability, string> = {  // each in the language spoken whenever it's read
  get recall() { return t("search its conversations"); },
  get documents() { return t("ask about documents from outside"); },
  get agents() { return t("ask other agents"); },
  get notebook() { return t("keep a notebook"); },
  get handover() { return t("hand a conversation over to people"); },
};

function Knows({ agent }: { agent: AgentUses }) {
  const { budget_tokens: conversation, ...rest } = agent.context;
  const abilities = Object.keys(ABILITIES) as Ability[];
  const may = abilities.filter((key) => rest[key] === true).map((key) => ABILITIES[key]);
  const not = abilities.filter((key) => rest[key] === false).map((key) => ABILITIES[key]);
  const other = Object.entries(rest).filter(([key]) => !(key in ABILITIES));
  return (
    <section className="card">
      <h2>{t("What it knows, and may spend")}</h2>
      <dl className="facts">
        {builtOf(agent) && <div className="fact-pair"><dt>{t("Skills")}</dt><dd>{agent.skills.join(", ") || t("none")}</dd></div>}
        {typeof conversation === "number" && (
          <div className="fact-pair"><dt>{t("Its conversation")}</dt><dd>{t("up to {tokens} tokens of it each run", { tokens: conversation.toLocaleString(locale()) })}</dd></div>
        )}
        {may.length > 0 && <div className="fact-pair"><dt>{t("It may")}</dt><dd>{may.join(", ")}</dd></div>}
        {not.length > 0 && <div className="fact-pair"><dt>{t("It may not")}</dt><dd>{not.join(", ")}</dd></div>}
        {other.map(([key, value]) => (
          <div key={key} className="fact-pair">
            <dt>{key.replace(/_/g, " ")}</dt>
            <dd>{typeof value === "boolean" ? (value ? t("yes") : t("no")) : String(value)}</dd>
          </div>
        ))}
        <dt>{t("Each run")}</dt><dd>{t("up to {tokens} tokens", { tokens: agent.budget.per_run.toLocaleString(locale()) })}</dd>
        <dt>{t("Each person, each day")}</dt><dd>{t("up to {tokens} tokens", { tokens: agent.budget.per_person_per_day.toLocaleString(locale()) })}</dd>
      </dl>
    </section>
  );
}

function Where({ agent }: { agent: AgentKnown }) {
  return (
    <section className="card wide">
      <h2>{t("Where it runs")}</h2>
      {agent.instances.length === 0 && <p className="note">{t("No instance you may watch runs it.")}</p>}
      {agent.instances.length > 0 && (
        <Wide label={t("Where it runs")}><table className="grid-table">
          <thead><tr><th>{t("Instance")}</th><th>{t("Status")}</th><th>{t("Level")}</th><th>{t("Parts")}</th><th>{t("Serves")}</th><th>{t("Run by")}</th><th>{t("Release")}</th></tr></thead>
          <tbody>
            {agent.instances.map((inst) => (
              <tr key={inst.id}>
                <td><Link to={{ page: "instance", instance: inst.id }}>{inst.id}</Link></td>
                <td><StatusBadge status={inst.status} /></td>
                <td>{inst.level}</td>
                <td>{Object.keys(inst.parts).join(", ") || t("none")}</td>
                <td>{people(inst.people)}</td>
                <td>{runners(inst)}</td>
                <td>{inst.current ? t("this one") : <span className="badge warn">{t("still {release}", { release: inst.release })}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table></Wide>
      )}
    </section>
  );
}

/** Drafting a change to it: the page's one thing to do, unless putting it to work comes first. */
function DraftAChange({ id, second = false }: { id: string; second?: boolean }) {
  const [problem, setProblem] = useState<string>();
  const start = async () => {
    try {
      const draft = await send<Draft>("POST", "/studio/api/drafts", { agent: id });
      go({ page: "draft", draft: draft.id });
    } catch (e) {
      const mine = e instanceof ApiError && e.status === 409  // theirs already: carry on with it
        && (await get<Drafts>("/studio/api/drafts")).drafts.find((d) => d.agent === id);
      if (mine) go({ page: "draft", draft: mine.id });
      else setProblem((e as Error).message);
    }
  };
  return (
    <div className="actions">
      <button type="button" className={second ? undefined : "primary"} id="draft-change" onClick={start}>{t("Draft a change")}</button>
      {problem && <span className="problem">{problem}</span>}
    </div>
  );
}

// Why someone sees each layer of an agent, in a line: the roles that give it them
function Seen({ agent }: { agent: AgentKnown }) {
  const layers = agent.layers;
  if (!layers) return null;
  const lines: [string, string[] | undefined][] = [
    [t("You know of it"), layers.exists], [t("You see what it may do"), layers.uses],
    [t("You see how it's built"), layers.built], [t("You see how it's doing"), layers.doing],
    [t("You may change it"), layers.changing]];
  return (
    <section className="card" id="seen">
      <h2>{t("What you see of it, and why")}</h2>
      <dl className="facts">
        {lines.filter(([, why]) => why).map(([what, why]) => (
          <div key={what} className="fact-pair"><dt>{what}</dt><dd>{why!.join("; ")}</dd></div>
        ))}
      </dl>
      {!layers.built && (
        <p className="note">{layers.uses ? t("Its instructions are for those who make it, own it, approve its releases or audit it.")
          : t("What it may do is for the people it serves and those who run it: to have it serve you, ask for it.")}</p>
      )}
    </section>
  );
}

// Putting an agent to work, for its owners and authors, once it's released and no instance runs
// it: a first instance in the settings, for a few people, at level 0 or 1. Those who approve
// versions of the settings go there with the agent chosen; others are told who can.

// Released, and no instance runs it, to its owners and authors, who see every one that does
const idle = (agent: AgentKnown) => Boolean(agent.layers?.changing) && agent.instances.length === 0;

function PutToWork({ agent }: { agent: AgentKnown }) {
  const shell = useLoad(shellOf, []);
  const may = mayUse(shell.data, "settings");
  return (
    <section className="card" id="put-to-work">
      <h2>{t("Put it to work")}</h2>
      <p>{t("No instance runs it yet. Its first is an instance in the settings, for a few people first, at level 0 or 1, so it suggests, or asks before each change. Its part's owner approves it, as any change there.")}</p>
      {may
        ? <div className="actions"><Link className="button primary" id="put-it-to-work"
            to={{ page: "settings", search: `?add=${encodeURIComponent(agent.id)}` }}>{t("Put it to work in the settings")}</Link></div>
        : shell.data && <p className="note">{t("Those who approve versions of the settings put it to work there: a part's owner, or someone who approves instances. To have it serve you, ask for it.")}</p>}
    </section>
  );
}

// Asking for an agent, on its page: for someone it doesn't serve, ask for it or withdraw their
// ask; for those an ask waits on, serve its asker through one of the agent's instances, as a
// version of the settings for its approvers to sign, or decline it.

function AskFor({ agent, reload }: { agent: AgentKnown; reload: () => void }) {
  const [problem, setProblem] = useState<string>();
  const act = async (method: "POST" | "DELETE") => {
    try {
      await send(method, `/studio/api/agents/${encodeURIComponent(agent.id)}/ask`);
      reload();
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  return (
    <section className="card" id="ask">
      <h2>{t("Asking for it")}</h2>
      {agent.ask
        ? <p>{t("You asked for it {when}. It waits on its owners and those who approve its instances, who answer it with a version of the settings that serves you.", { when: when(agent.ask.asked_at) })}</p>
        : <p>{t("To have it serve you, ask for it: its owners and those who approve its instances see what you asked.")}</p>}
      <div className="actions">
        {agent.ask
          ? <button type="button" id="unask" onClick={() => act("DELETE")}>{t("Withdraw it")}</button>
          : <button type="button" className="primary" id="ask-for" onClick={() => act("POST")}>{t("Ask for it")}</button>}
        {problem && <span className="problem">{problem}</span>}
      </div>
    </section>
  );
}

function AsksWaiting({ agent, reload }: { agent: AgentKnown; reload: () => void }) {
  const toast = useToast();
  const [said, setSaid] = useState<string>();
  const instances = agent.instances;
  const asks = agent.asks?.length ?? 0;
  useEffect(() => {  // what became of it takes the focus, the button that did it gone (round 13, C8)
    if (said) document.getElementById("asks-said")?.focus();
  }, [said, asks]);
  const answer = async (ask: string, how: "serve" | "decline", instance?: string, person?: string) => {
    try {
      const done = await send<{ serial?: number }>("POST", `/studio/api/asks/${ask}/${how}`,
                                                 how === "serve" ? { instance } : undefined);
      const words = how === "serve"
        ? t("You asked for version {serial} of the settings, to serve {person} through {instance}: a5s asks its approvers within a minute.",
            { serial: String(done.serial), person: String(person), instance: String(instance) })
        : t("You declined {person}'s ask for the {agent}.", { person: String(person), agent: agent.id });
      setSaid(words);
      toast(words);
      reload();
    } catch (e) {
      setSaid(sentence((e as Error).message));
    }
  };
  const line = said && <p className="note" role="status" id="asks-said" tabIndex={-1}>{said}</p>;
  if (!agent.asks?.length) return line || null;  // said outside what went
  return (
    <section className="card" id="asks">
      <h2>{t("Asked for")}</h2>
      <ul className="plain">{agent.asks.map((a) => (
        <li key={a.id}>{t("{person} asked for it {when}", { person: a.person, when: when(a.asked_at) })} <span className="faint">· {a.why.join("; ")}</span>
          <div className="actions">
            {instances.map((i) => (
              <button key={i.id} type="button" onClick={() => answer(a.id, "serve", i.id, a.person)}>{t("Serve them through {instance}", { instance: i.id })}</button>
            ))}
            <button type="button" onClick={() => answer(a.id, "decline", undefined, a.person)}>{t("Decline")}</button>
          </div>
        </li>
      ))}</ul>
      {line}
    </section>
  );
}

export function AgentPage({ id }: { id: string }) {
  const [version, setVersion] = useState(0);  // asked again after an ask, or its answer
  const reload = () => setVersion((v) => v + 1);
  const { data: agent, error } = useLoad(() => get<AgentKnown>(`/studio/api/agents/${encodeURIComponent(id)}`), [id, version]);
  const uses = agent && usesOf(agent) ? agent : undefined;
  const catalogue = useLoad(() => get<Catalogue>("/studio/api"), []);
  const changes = catalogue.data?.authoring.agents.includes(id) ?? false;
  return (
    <>
      <PageHead crumbs={[{ label: t("Agents"), to: { page: "agents" } }]} title={agent?.id ?? t("An agent")}
                about={agent?.works_for}
                badges={agent && <span className="chip mono">{agent.release}</span>}>
        {agent && (
          <div className="meta">
            {uses && <><span>{uses.model}</span><span>{levels(uses.autonomy)}</span></>}
            <span>{t("Owned by {owners}", { owners: agent.owners.join(", ") || t("nobody the directory names") })}</span>
            {agent.instances.map((i) => <span key={i.id}>{i.id}: {aboutInstance(i)}</span>)}
            <Link to={{ page: "map", at: `agent:${agent.id}` }} id="on-the-map">{t("What depends on it")}</Link>
          </div>
        )}
        {agent && changes && <DraftAChange id={id} second={idle(agent)} />}
      </PageHead>
      {!agent && <Waiting error={error} />}
      {agent && (
        <>
          {idle(agent) && <PutToWork agent={agent} />}
          {uses && (
            <section className="card map-card">
              <h2>{t("How it's wired")}</h2>
              <p className="note">{t("What starts its runs, and the tools it may call, each through a5s's checks. Changes to records wait for a person to decide at level 1.")}</p>
              <AgentMap agent={uses} />
            </section>
          )}
          <div className="agent-body">
            <div>
              <section className="card">
                <h2>{t("What it does")}</h2>
                <p>{agent.does}</p>
                {builtOf(agent) && agent.instructions && (
                  <details>
                    <summary>{t("Its instructions")}</summary>
                    <pre className="instructions">{agent.instructions}</pre>
                  </details>
                )}
              </section>
              {uses && <Tools agent={uses} />}
            </div>
            <div className="side">
              {uses && <Facts agent={agent} uses={uses} />}
              {uses && <Ladder agent={agent} uses={uses} />}
              <Seen agent={agent} />
              {agent.ask !== undefined && <AskFor agent={agent} reload={reload} />}
              <AsksWaiting agent={agent} reload={reload} />
              {uses && <When agent={uses} />}
              {uses && <Knows agent={uses} />}
            </div>
          </div>
          {(!agent.layers || agent.layers.doing) && <Where agent={agent} />}
          <SaidWrong agent={agent.id} />
        </>
      )}
    </>
  );
}
