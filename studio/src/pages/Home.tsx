// The studio's home: what waits for whoever signed in, each where they do it, on its own page
// or at the command line; their drafts; and where to go next. Everyone the directory knows
// has one, whether or not they hold a role.

import { get, type Home } from "../api";
import { t } from "../i18n";
import { Link } from "../router";
import { PageHead, useLoad, Waiting, WaitList, when } from "../ui";

export function HomePage() {
  const { data, error } = useLoad(() => get<Home>("/studio/api/home"), []);
  return (
    <>
      <PageHead title={data ? t("Welcome, {name}", { name: data.you.split(" ")[0] }) : t("Welcome")}
                about={t("What waits for you in a5s, and where you do it. Nothing here is done for you: each opens where it's done, signed in afresh where it counts.")} />
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
          <section className="card" id="next">
            <h2>{t("In the studio")}</h2>
            <ul className="plain">
              <li><Link to={{ page: "agents" }}>{t("The agents you may know of")}</Link>{t(": what each does, and how those you watch are doing")}</li>
              {data.authoring && <li><Link to={{ page: "new" }}>{t("A new agent")}</Link>{t(", from a template")}</li>}
              <li><Link to={{ page: "you" }}>{t("What you may do in a5s")}</Link>{t(", and which group gave you each role")}</li>
            </ul>
          </section>
        </>
      )}
    </>
  );
}
