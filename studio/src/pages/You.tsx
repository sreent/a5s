// What someone may do in a5s: each role they hold, what gave it them, the directory or a group
// of the identity provider's, and what it lets them do. Roles change where people are managed,
// in the identity provider, and in the signed settings that give its groups roles: not here.
// And the language they read, theirs to choose, which a5s's pages speak to them and its agents
// answer them in (core/languages.py); and the accounts they connect in other systems, so agents
// act there as them, with their own permissions (core/delegation.py), with the page each
// system sends them back to.

import { useEffect, useRef, useState } from "react";
import { get, send, type You } from "../api";
import type * as gen from "../api.gen";
import { takeConnecting } from "../auth";
import { Badge, Confirm, useToast } from "../design";
import { setLanguage, t } from "../i18n";
import { go, Link } from "../router";
import { shellOf } from "../Sidebar";
import { PageHead, useLoad, Waiting, when, Wide } from "../ui";

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

function Connections() {
  const toast = useToast();
  const { data, error, reload } = useLoad(() => get<gen.Connections>("/studio/api/you/connections"), []);
  const [problem, setProblem] = useState<string>();
  if (error) return <Waiting error={error} />;
  if (!data || data.connections.length === 0) return null;  // the deployment connects none
  const connect = (system: string) => {
    setProblem(undefined);
    send<gen.ConnectionStarted>("POST", `/studio/api/you/connections/${encodeURIComponent(system)}/start`)
      .then((started) => location.assign(started.go))  // the system asks them, as itself
      .catch((e: Error) => setProblem(e.message));
  };
  const disconnect = (c: gen.Connection) => {
    setProblem(undefined);
    send<gen.Disconnected>("DELETE", `/studio/api/you/connections/${encodeURIComponent(c.system)}`)
      .then(() => {
        toast(t("a5s has forgotten your {system} account: agents no longer act there as you.", { system: c.title }));
        return reload();
      })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <section className="card" id="connections" aria-labelledby="connections-title">
      <h2 id="connections-title">{t("Your accounts in other systems")}</h2>
      <p className="note">{t("Connect one, and agents act there as you, with your own permissions: what the system lets you see and change, and no more. a5s keeps its key sealed, and forgets it when you disconnect, or after 90 days unused.")}</p>
      <Wide label={t("The systems you may connect")}><table className="grid-table">
        <thead><tr><th>{t("System")}</th><th>{t("Now")}</th><th>{t("What a5s may do there as you")}</th><th>{t("Connect or disconnect")}</th></tr></thead>
        <tbody>{data.connections.map((c) => (
          <tr key={c.system} data-system={c.system}>
            <td><strong>{c.title}</strong></td>
            <td>
              {c.connected
                ? <Badge tone="good" dot>{t("Connected")}</Badge>
                : c.connecting ? <Badge tone="warn" dot>{t("Connecting")}</Badge> : <Badge tone="idle">{t("Not connected")}</Badge>}
              {c.connected && c.connected_at && <span className="note"> {t("since {at}", { at: when(c.connected_at) })}</span>}
              {c.connected && <span className="note">, {c.used_at ? t("last used {at}", { at: when(c.used_at) }) : t("not used yet")}</span>}
            </td>
            <td>{c.scopes.length === 0 ? t("what the system gives a5s")
              : c.scopes.map((scope, i) => <span key={scope}>{i > 0 && ", "}<span className="mono">{scope}</span></span>)}</td>
            <td>{c.connected
              ? <Confirm label={t("Disconnect")} title={t("Disconnect your {system} account?", { system: c.title })}
                         about={t("Agents won't act there as you until you connect it again. The system may keep its own record of a5s's access, which you can end there too.")}
                         confirm={t("Disconnect")} danger onConfirm={() => disconnect(c)} />
              : <button type="button" className="primary" onClick={() => connect(c.system)}>
                  {t("Connect {system}", { system: c.title })}
                </button>}</td>
          </tr>
        ))}</tbody>
      </table></Wide>
      {problem && <p className="problem" role="alert">{problem}</p>}
    </section>
  );
}

/** Where each system sends someone back to, once they've said whether a5s may act for them
 * there: its code, passed on to the core, which takes it within a minute. */
export function ConnectedPage() {
  const toast = useToast();
  const [said, setSaid] = useState<{ problem?: string; title?: string; no?: boolean }>({});
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;  // once, though the page draws twice in development
    started.current = true;
    const back = takeConnecting();
    if (!back) {
      setSaid({ problem: t("There's nothing here to connect. Connect an account on your own page.") });
      return;
    }
    let stop = false;
    send<gen.ConnectionBack>("POST", "/studio/api/you/connections/back", back)
      .then(async (found) => {
        if (!found.connecting) {
          setSaid({ title: found.title, no: true });
          return;
        }
        setSaid({ title: found.title });
        for (let tries = 0; tries < 90 && !stop; tries++) {  // the core takes it within a minute
          const now = await get<gen.Connections>("/studio/api/you/connections");
          const it = now.connections.find((c) => c.system === found.system);
          if (it?.connected) {
            toast(t("Your {system} account is connected: agents act there as you, with your permissions.", { system: found.title }));
            go({ page: "you" });
            return;
          }
          if (it && !it.connecting) break;  // the core couldn't take it
          await new Promise((then) => setTimeout(then, 1000));
        }
        if (!stop) setSaid({ problem: t("a5s couldn't connect your {system} account. Try again on your own page.", { system: found.title }) });
      })
      .catch((e: Error) => setSaid({ problem: e.message }));
    return () => { stop = true; };
  }, [toast]);
  return (
    <>
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }, { label: t("What you may do"), to: { page: "you" } }]}
                title={said.title ? t("Connecting your {system} account", { system: said.title }) : t("Connecting your account")} />
      <section className="card">
        {said.problem
          ? <p className="problem" role="alert">{said.problem}</p>
          : said.no
            ? <p role="status">{t("You didn't let a5s act for you in {system}, so nothing's connected.", { system: said.title ?? "" })}</p>
            : <p className="note" role="status">{t("a5s is taking what the system gave it. This takes a moment.")}</p>}
        <p><Link to={{ page: "you" }}>{t("Back to your accounts")}</Link></p>
      </section>
    </>
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
          <Connections />
        </>
      )}
    </>
  );
}
