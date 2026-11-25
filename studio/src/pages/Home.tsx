// The studio's home: the roles whoever signed in holds, as a5s has no administrator's mode to
// be in or out of, only roles; what waits for them, each where they do it, on its own page or
// at the command line; their drafts; how an agent comes to work, and whether they may start
// one, or else who may; and where to go next. Everyone the directory knows has one, whether or
// not they hold a role.

import { get, type Home } from "../api";
import { JourneyPath, type Stage } from "../design";
import { t } from "../i18n";
import { Link } from "../router";
import { shellOf } from "../Sidebar";
import { PageHead, useLoad, Waiting, WaitList, when } from "../ui";

/** How an agent comes to work, from its start, as a draft's own path goes on (pages/Draft.tsx). */
const building = (): Stage[] => [
  { name: t("Start it"), state: "now", about: t("From a template, or from a few words about what it should do.") },
  { name: t("Shape and try it"), state: "later",
    about: t("On its map: what starts its runs, the tools it may call and how far it may go, with a5s's checks as you go. Then try it in the sandbox, on made-up records.") },
  { name: t("Publish it"), state: "later", about: t("As a pull request.") },
  { name: t("Have its release signed"), state: "later", about: t("By whoever its release needs, whom a5s names. a5s deploys it once they have.") },
  { name: t("Put it to work"), state: "later",
    about: t("An instance in the settings, for a few people first, reading only or asking first, once the owners of the parts it works in approve it.") },
  { name: t("Watch it"), state: "later", about: t("Its runs and how they end, on its page.") },
];

/** Building an agent: the way, for whoever may start one; for anyone else, who may, and how
 * to become one of them, so nobody is left wondering where the button is. */
function Build({ data }: { data: Home }) {
  return (
    <section className="card" id="build" aria-labelledby="build-title">
      <h2 id="build-title">{t("Build an agent")}</h2>
      {data.authoring ? (
        <JourneyPath stages={building()} label={t("From a new agent to an agent at work")}
                     next={<Link to={{ page: "new" }} className="button primary" id="start-agent">{t("Start a new agent")}</Link>} />
      ) : (
        <>
          <p>{t("A new agent is started by an agent's owner or an engineer, and you're neither. To build one, ask whoever runs a5s in your organisation to make you an agent's owner or an engineer, or ask an agent's owner to make you one of its authors, to change that agent.")}</p>
          {data.changes.length > 0 && (
            <p>{t("You may change the agents you author, each from its page:")}{" "}
              {data.changes.map((agent, i) => (
                <span key={agent}>{i > 0 && ", "}<Link to={{ page: "agent", agent }} className="mono">{agent}</Link></span>
              ))}.</p>
          )}
        </>
      )}
    </section>
  );
}

/** The roles someone holds, said once at the top of their home, with what that means. */
function Roles() {
  const { data } = useLoad(shellOf, []);
  if (!data) return null;
  return (
    <p className="meta" id="your-roles">
      <span>{data.roles.length
        ? t("Your roles: {roles}. What you see in a5s follows from them: there's no administrator's mode.", { roles: data.roles.join(" · ") })
        : t("You hold none of a5s's roles: you work with the agents that serve you.")}</span>
      <Link to={{ page: "you" }}>{t("What you may do")}</Link>
    </p>
  );
}

export function HomePage() {
  const { data, error } = useLoad(() => get<Home>("/studio/api/home"), []);
  return (
    <>
      <PageHead title={data ? t("Welcome, {name}", { name: data.you.split(" ")[0] }) : t("Welcome")}
                about={t("What waits for you in a5s, and where you do it. Nothing here is done for you: each opens where it's done, signed in afresh where it counts.")}>
        <Roles />
      </PageHead>
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card" id="waiting">
            <h2>{t("Waiting on you")}</h2>
            <WaitList waiting={data.waiting} none={t("Nothing waits on you now.")} />
          </section>
          {data.drafts.length > 0 && (
            <section className="card" id="my-drafts">
              <h2>{t("Your drafts")}</h2>
              <ul className="plain">{data.drafts.map((d) => (
                <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
                  <span className="faint"> · {t("from {release} · kept {when}", { release: d.based_on ?? "", when: when(d.updated_at) })}</span></li>
              ))}</ul>
            </section>
          )}
          <Build data={data} />
          <section className="card" id="next">
            <h2>{t("In the studio")}</h2>
            <ul className="plain">
              <li><Link to={{ page: "agents" }}>{t("The agents you may know of")}</Link>{t(": what each does, and how those you watch are doing")}</li>
              <li><Link to={{ page: "you" }}>{t("What you may do in a5s")}</Link>{t(", and which group gave you each role")}</li>
            </ul>
          </section>
        </>
      )}
    </>
  );
}
