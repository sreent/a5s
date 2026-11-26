// The data protection officer's requests, folded into the studio from their own page
// (core/officer_api.py): to export, or erase, all a5s keeps about someone. They sign in afresh
// for that request alone: the sign-in's nonce commits to exactly this request, so the identity
// provider signs it. Someone from the team that runs a5s then carries it out, once, within ten
// minutes, with the command the page gives them.

import { type FormEvent, useEffect, useState } from "react";
import { get, type OfficerAsked, type OfficerNow, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { ActingAs, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, useLoad, Waiting } from "../ui";

type Action = "export" | "erase";

/** What the officer asks to do, in the language spoken: what's sent is the action itself. */
const verb = (action: string) => (action === "export" ? t("export") : action === "erase" ? t("erase") : action);

export function OfficerPage() {
  const toast = useToast();
  const [action, setAction] = useState<Action>("export");
  const [person, setPerson] = useState("");
  const [again, setAgain] = useState("");
  const [status, setStatus] = useState<string>();
  const [asked, setAsked] = useState(false);  // asked, its one job done, until they ask another
  const now = useLoad(() => get<OfficerNow>("/officer/api"), []);  // the officer, and nobody else
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "officer") return;
    setAsked(true);
    send<OfficerAsked>("POST", "/officer/requests", { action: act.action, person: act.person, salt: act.salt })
      .then((made) => {
        const whom = made.name ? `${made.name} (${made.person})` : made.person;
        const done = t("You asked to {action} all a5s keeps about {whom}.", { action: verb(made.asked), whom });
        setStatus(`${done} ${t("Someone from the team that runs a5s carries it out, once, within {lasts}: {command}",
          { lasts: made.lasts, command: made.command })}`);
        toast(done);
      })
      .catch((e: Error) => {  // refused: the form again, as they filled it, to ask again (round 13, C4)
        setAction(act.action);
        setPerson(act.person);
        if (act.action === "erase") setAgain(act.person);
        setAsked(false);
        setStatus(t("a5s didn't take your request: {why}", { why: e.message }));
      });
  }, []);
  const another = () => {
    setPerson("");
    setAgain("");
    setStatus(undefined);
    setAsked(false);
  };

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    const whom = person.trim();
    if (!whom) {
      setStatus(t("Name the person: by their id in the directory, an archive's name, or, for someone outside the directory, such as a customer who wrote to a shared mailbox, their address."));
      return;
    }
    if (action === "erase" && again.trim() !== whom) {
      setStatus(t("Type their id again, the same, to confirm it: an erasure can't be undone."));
      return;
    }
    try {
      // a nonce that commits to this request alone, as core/officer.py's `nonce` makes it
      const salt = salted();
      const nonce = await hashed(`a5s officer ${action} ${whom} ${salt}`);
      await signInFor({ kind: "officer", action, person: whom, salt }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  return (
    <>
      <ActingAs acting={now.data?.acting} />
      <PageHead title={t("A request for someone's data")}
                about={t("Ask to export, or erase, all a5s keeps about someone, at their request. You sign in afresh for that request alone, and someone from the team that runs a5s carries it out.")} />
      <p id="status" role="status" className="note">{status}</p>
      {now.error && <Waiting error={now.error} />}
      {asked && <p><button type="button" id="another" onClick={another}>{t("Ask about someone else")}</button></p>}
      {!asked && !now.error && (
        <form id="ask" className="card" onSubmit={ask}>
          <p>
            <label htmlFor="action">{t("Ask to")}</label>{" "}
            <select id="action" value={action} onChange={(e) => setAction(e.target.value as Action)}>
              <option value="export">{t("export")}</option>
              <option value="erase">{t("erase")}</option>
            </select>{" "}
            <label htmlFor="person">{t("all a5s keeps about")}</label>{" "}
            <input id="person" autoComplete="off" spellCheck={false} placeholder={t("an id, an archive's name, or an address")}
                   value={person} onChange={(e) => setPerson(e.target.value)} />
          </p>
          {action === "erase" && (
            <p id="again">
              <label htmlFor="confirm">{t("Their id again, since an erasure can't be undone:")}</label>{" "}
              <input id="confirm" autoComplete="off" spellCheck={false} value={again}
                     onChange={(e) => setAgain(e.target.value)} />
            </p>
          )}
          <p className="note">{t("You sign in afresh, for this request alone. Someone from the team that runs a5s then carries it out, once, within ten minutes: your sign-in does nothing else.")}</p>
          <button className="primary" type="submit">{t("Sign in and ask")}</button>
        </form>
      )}
    </>
  );
}
