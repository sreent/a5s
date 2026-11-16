// What someone may do in a5s: each role they hold, what gave it them, the directory or a group
// of the identity provider's, and what it lets them do. Roles change where people are managed,
// in the identity provider, and in the signed settings that give its groups roles: not here.
// And the language they read, theirs to choose, which a5s's pages speak to them and its agents
// answer them in (core/languages.py).

import { useState } from "react";
import { get, send, type You } from "../api";
import type * as gen from "../api.gen";
import { useToast } from "../design";
import { setLanguage, t } from "../i18n";
import { shellOf } from "../Sidebar";
import { PageHead, useLoad, Waiting, Wide } from "../ui";

function Language({ found }: { found: You }) {
  const toast = useToast();
  const [problem, setProblem] = useState<string>();
  const [chosen, setChosen] = useState(found.language);  // at once, while a5s keeps it
  const choose = (code: string) => {
    setProblem(undefined);
    setChosen(code);
    send<gen.LanguageChosen>("POST", "/studio/api/you/language", { language: code })
      .then((kept) => {
        shellOf(true).catch(() => null);  // the sidebar's names, afresh in it
        setLanguage(kept.language);  // which draws the studio again in it
        toast(t("a5s speaks to you in {language} from now on.", {
          language: found.languages.find((l) => l.code === kept.language)?.name ?? kept.language }));
      })
      .catch((e: Error) => {
        setChosen(found.language);
        setProblem(e.message);
      });
  };
  return (
    <section className="card" id="language" aria-labelledby="language-title">
      <h2 id="language-title">{t("The language you read")}</h2>
      <p className="note">{t("a5s's pages speak it to you, and its agents answer you in it, unless you write to them in another. Your organisation's directory sets it first; it's yours to change.")}</p>
      <div className="choices" role="radiogroup" aria-labelledby="language-title">
        {found.languages.map((l) => (
          <label key={l.code} className="check" lang={l.code}>
            <input type="radio" name="language" value={l.code} checked={chosen === l.code}
                   onChange={() => choose(l.code)} />
            {l.name}
          </label>
        ))}
      </div>
      {problem && <p className="problem" role="alert">{problem}</p>}
    </section>
  );
}

export function YouPage() {
  const { data, error } = useLoad(() => get<You>("/studio/api/you"), []);
  return (
    <>
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }]} title={t("What you may do")}
                about={t("Each of your roles in a5s, what gave it you, and what it lets you do. Your organisation manages its groups in its identity provider, and a5s's signed settings say what each group may do: a role you lose there stops working at your next sign-in.")} />
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card" id="roles">
            <h2>{data.you}</h2>
            {data.roles.length === 0
              ? <p className="note">{t("You hold none of a5s's roles: you use the agents that serve you, and see your own tasks and notebook. Whoever approves the agent you'd use can add you.")}</p>
              : (
                <Wide label={t("What you may do")}><table className="grid-table">
                  <thead><tr><th>{t("Role")}</th><th>{t("Lets you")}</th><th>{t("Given by")}</th></tr></thead>
                  <tbody>{data.roles.map((r) => (
                    <tr key={r.role}>
                      <td><strong>{r.name}</strong>{r.name !== r.role && <span className="role-id mono">{r.role}</span>}</td>
                      <td>{r.may}</td><td>{r.by.join(", ")}</td>
                    </tr>
                  ))}</tbody>
                </table></Wide>
              )}
          </section>
          <section className="card" id="groups">
            <h2>{t("Your groups")}</h2>
            {data.groups.length === 0
              ? <p className="note">{t("Your latest sign-in showed none of the groups a5s's settings give roles.")}</p>
              : <p>{t("Your latest sign-in showed")} {data.groups.map((g, i) => <span key={g}>{i > 0 && ", "}<span className="mono">{g}</span></span>)}.</p>}
          </section>
          <Language found={data} />
        </>
      )}
    </>
  );
}
