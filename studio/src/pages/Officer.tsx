// The data protection officer's requests, folded into the studio from their own page
// (core/officer_api.py): to export, or erase, all a5s keeps about someone. They sign in afresh
// for that request alone: the sign-in's nonce commits to exactly this request, so the identity
// provider signs it. Someone from the team that runs a5s then carries it out, once, within ten
// minutes, with the command the page gives them. Friction follows the risk (docs/design.md):
// an export reaches someone else's data, so it's in a zone that says so first; an erasure can't
// be undone, so it's in a zone of its own. The page says whose the id is as it's typed, a name
// and a team, so an id mistyped as someone else's shows as theirs, and the erasure asks for the
// id typed again without showing it, which the server checks too (round 17, B1).

import { useEffect, useState } from "react";
import { get, type OfficerAsked, type OfficerNow, type OfficerWhom, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { ActingAs, ActionZone, Confirm, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, useLoad, Waiting } from "../ui";

type Action = "export" | "erase";

/** What the officer asks to do, in the language spoken: what's sent is the action itself. */
const verb = (action: string) => (action === "export" ? t("export") : action === "erase" ? t("erase") : action);

const NAME_THEM = "Name the person first: by their id in the directory, an archive's name, or, for someone outside the directory, such as a customer who wrote to a shared mailbox, their address.";

/** How the erasure asks for what was named, typed again, without showing it. */
const ASK_AGAIN: Record<string, string> = {
  address: "Type the address again", archive: "Type the archive's name again", person: "Type their id again",
};

/** What an export holds, and what an erasure takes and leaves, for what was named. */
function exported(found: OfficerWhom, whom: string): string {
  return found.kind === "address"
    ? t("An export of {whom} says where a5s keeps the address, and how much: the runs and documents that held it, the texts that hold it, and the changes asked for that name it. Nothing changes for them.", { whom })
    : t("An export holds everything a5s keeps about {whom}: their conversations, what agents did and noted for them, and what they asked for and said, to answer their request with. Nothing changes for them.", { whom });
}

function erased(found: OfficerWhom, whom: string): string {
  if (found.kind === "address") {
    return t("{whom} goes from everything a5s keeps that holds it, a stand-in in its place, and the documents and handles runs held it in go; nobody can bring them back. The changes agents asked for that name it stay, as evidence of what agents did, and the ledger keeps that it was done by the address's digest alone.", { whom });
  }
  return t("What's {whom}'s goes, everywhere a5s keeps it: their conversations, notes and reminders, drafts, asks and connected accounts, and what they said in group chats; nobody can bring it back. What's evidence of what agents did stays while retention keeps it: the ledger, which holds what was said by hash alone, the runs that acted for them, and the changes asked for them, with their decisions and samples; in a group chat, a name no person has takes theirs. A backup holds what went until it ages out, and restoring one erases it again.", { whom });
}

export function OfficerPage() {
  const toast = useToast();
  const [person, setPerson] = useState("");
  const [status, setStatus] = useState<string>();
  const [asked, setAsked] = useState(false);  // asked, its one job done, until they ask another
  const [found, setFound] = useState<OfficerWhom & { for: string }>();  // whose the id typed is
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
  useEffect(() => {  // whose it is, a moment after they stop typing, for the id as it is then
    if (!whom || now.error) return;
    const looking = window.setTimeout(() => {
      get<OfficerWhom>(`/officer/whom?person=${encodeURIComponent(whom)}`)
        .then((said) => setFound({ ...said, for: whom }))
        .catch((e: Error) => setFound({ kind: "unknown", said: t("a5s can't say whose this is just now: {why}", { why: e.message }), for: whom }));
    }, 300);
    return () => window.clearTimeout(looking);
  }, [whom, now.error]);
  const known = found && found.for === whom ? found : undefined;  // as of the id typed now
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
  const named = known?.name ? `${known.name} (${whom})` : whom || t("the person you name");
  const shown = known ?? { kind: "person", said: "" };  // until a5s says whose it is

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
                     aria-describedby="whose" value={person} onChange={(e) => setPerson(e.target.value)} />
            </div>
            <p id="whose" role="status">{whom && (known ? <strong>{known.said}</strong> : t("Looking up whose this is…"))}</p>
            <p className="note">{t("You sign in afresh, for one request alone. Someone from the team that runs a5s then carries it out, once, within ten minutes: your sign-in does nothing else.")}</p>
          </section>
          <ActionZone title={t("Export all a5s keeps about them")} reach={exported(shown, named)}>
            <button type="button" id="export" className="primary" onClick={() => void ask("export")}>{t("Sign in and ask to export it")}</button>
          </ActionZone>
          <ActionZone title={t("Erase all a5s keeps about them")} cantUndo reach={erased(shown, named)}>
            {known && known.kind !== "group"  // a group chat's is nobody's own, which the core refuses too
              ? <Confirm label={t("Erase it")} danger typed={whom} ask={t(ASK_AGAIN[known.kind] ?? "Type the id again")}
                         title={t("Erase all a5s keeps about {person}?", { person: known.name ?? whom })}
                         about={`${known.said} ${t("It goes everywhere a5s keeps it, and nobody can bring it back. You'll sign in again, for this alone.")}`}
                         confirm={t("Sign in and erase it")} onConfirm={(typed) => void ask("erase", typed)} />
              : <button type="button" className="danger" onClick={() => setStatus(
                  known ? known.said : t(whom ? "a5s is still looking up whose this is: a moment, then erase it." : NAME_THEM))}>{t("Erase it")}</button>}
          </ActionZone>
        </>
      )}
    </>
  );
}
