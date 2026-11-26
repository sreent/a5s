// The data protection officer's requests, folded into the studio from their own page
// (core/officer_api.py): to export, or erase, all a5s keeps about someone. They sign in afresh
// for that request alone: the sign-in's nonce commits to exactly this request, so the identity
// provider signs it. Someone from the team that runs a5s then carries it out, once, within ten
// minutes, with the command the page gives them. Friction follows the risk (docs/design.md):
// an export reaches someone else's data, so it's in a zone that says so first; an erasure can't
// be undone, so it's in a zone of its own, and asks for the person's id typed, which the server
// checks too.

import { useEffect, useState } from "react";
import { get, type OfficerAsked, type OfficerNow, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { ActingAs, ActionZone, Confirm, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, useLoad, Waiting } from "../ui";

type Action = "export" | "erase";

/** What the officer asks to do, in the language spoken: what's sent is the action itself. */
const verb = (action: string) => (action === "export" ? t("export") : action === "erase" ? t("erase") : action);

const NAME_THEM = "Name the person first: by their id in the directory, an archive's name, or, for someone outside the directory, such as a customer who wrote to a shared mailbox, their address.";

export function OfficerPage() {
  const toast = useToast();
  const [person, setPerson] = useState("");
  const [status, setStatus] = useState<string>();
  const [asked, setAsked] = useState(false);  // asked, its one job done, until they ask another
  const now = useLoad(() => get<OfficerNow>("/officer/api"), []);  // the officer, and nobody else
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "officer") return;
    setAsked(true);
    send<OfficerAsked>("POST", "/officer/requests", { action: act.action, person: act.person, salt: act.salt,
                                                     ...(act.confirm ? { confirm: act.confirm } : {}) })
      .then((made) => {
        const whom = made.name ? `${made.name} (${made.person})` : made.person;
        const done = t("You asked to {action} all a5s keeps about {whom}.", { action: verb(made.asked), whom });
        setStatus(`${done} ${t("Someone from the team that runs a5s carries it out, once, within {lasts}: {command}",
          { lasts: made.lasts, command: made.command })}`);
        toast(done);
      })
      .catch((e: Error) => {  // refused: the form again, as they filled it, to ask again (round 13, C4)
        setPerson(act.person);
        setAsked(false);
        setStatus(t("a5s didn't take your request: {why}", { why: e.message }));
      });
  }, []);
  const another = () => {
    setPerson("");
    setStatus(undefined);
    setAsked(false);
  };

  const whom = person.trim();
  const ask = async (action: Action, confirm?: string) => {
    if (!whom) {
      setStatus(t(NAME_THEM));
      return;
    }
    try {
      // a nonce that commits to this request alone, as core/officer.py's `nonce` makes it
      const salt = salted();
      const nonce = await hashed(`a5s officer ${action} ${whom} ${salt}`);
      await signInFor({ kind: "officer", action, person: whom, salt, ...(confirm ? { confirm } : {}) }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };
  const named = whom || t("the person you name");

  return (
    <>
      <ActingAs acting={now.data?.acting} />
      <PageHead title={t("A request for someone's data")}
                about={t("Ask to export, or erase, all a5s keeps about someone, at their request. You sign in afresh for that request alone, and someone from the team that runs a5s carries it out.")} />
      <p id="status" role="status" className="note">{status}</p>
      {now.error && <Waiting error={now.error} />}
      {asked && <p><button type="button" id="another" onClick={another}>{t("Ask about someone else")}</button></p>}
      {!asked && !now.error && (
        <>
          <section className="card" id="whom" aria-labelledby="whom-title">
            <h2 id="whom-title">{t("Whose data")}</h2>
            <div className="form-field">
              <label htmlFor="person">{t("Their id in the directory, an archive's name, or, for someone outside the directory, their address")}</label>
              <input id="person" autoComplete="off" spellCheck={false} placeholder={t("an id, an archive's name, or an address")}
                     value={person} onChange={(e) => setPerson(e.target.value)} />
            </div>
            <p className="note">{t("You sign in afresh, for one request alone. Someone from the team that runs a5s then carries it out, once, within ten minutes: your sign-in does nothing else.")}</p>
          </section>
          <ActionZone title={t("Export all a5s keeps about them")}
                      reach={t("An export holds everything a5s keeps about {whom}: their conversations, what agents did and noted for them, and what they asked for and said, to answer their request with. Nothing changes for them.", { whom: named })}>
            <button type="button" id="export" className="primary" onClick={() => void ask("export")}>{t("Sign in and ask to export it")}</button>
          </ActionZone>
          <ActionZone title={t("Erase all a5s keeps about them")} cantUndo
                      reach={t("Everything a5s keeps about {whom} goes, everywhere a5s keeps it: their conversations, what agents did and noted for them, their drafts, asks and connected accounts, and what they said of agents' answers. Nobody can bring it back; the ledger keeps that it was done, never what it held.", { whom: named })}>
            {whom
              ? <Confirm label={t("Erase it")} danger typed={whom} ask={t("Type {person} to erase it", { person: whom })}
                         title={t("Erase all a5s keeps about {person}?", { person: whom })}
                         about={t("It goes everywhere a5s keeps it, and nobody can bring it back. You'll sign in again, for this alone.")}
                         confirm={t("Sign in and erase it")} onConfirm={(typed) => void ask("erase", typed)} />
              : <button type="button" className="danger" onClick={() => setStatus(t(NAME_THEM))}>{t("Erase it")}</button>}
          </ActionZone>
        </>
      )}
    </>
  );
}
