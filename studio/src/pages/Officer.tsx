// The data protection officer's requests, folded into the studio from their own page
// (core/officer_api.py): to export, or erase, all a5s keeps about someone. They sign in afresh
// for that request alone: the sign-in's nonce commits to exactly this request, so the identity
// provider signs it. Someone from the team that runs a5s then carries it out, once, within ten
// minutes, with the command the page gives them.

import { type FormEvent, useEffect, useState } from "react";
import { type OfficerAsked, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { useToast } from "../design";
import { PageHead } from "../ui";

type Action = "export" | "erase";

export function OfficerPage() {
  const toast = useToast();
  const [action, setAction] = useState<Action>("export");
  const [person, setPerson] = useState("");
  const [again, setAgain] = useState("");
  const [status, setStatus] = useState<string>();
  const [asked, setAsked] = useState(false);  // asked, its one job done, until they ask another
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "officer") return;
    setAsked(true);
    send<OfficerAsked>("POST", "/officer/requests", { action: act.action, person: act.person, salt: act.salt })
      .then((made) => {
        const whom = made.name ? `${made.name} (${made.person})` : made.person;
        setStatus(`You asked to ${made.asked} all a5s keeps about ${whom}. Someone from the team that runs a5s carries it out, once, within ${made.lasts}: ${made.command}`);
        toast(`You asked to ${made.asked} all a5s keeps about ${whom}.`);
      })
      .catch((e: Error) => {  // refused: the form again, as they filled it, to ask again (round 13, C4)
        setAction(act.action);
        setPerson(act.person);
        if (act.action === "erase") setAgain(act.person);
        setAsked(false);
        setStatus(`a5s didn't take your request: ${e.message}`);
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
      setStatus("Name the person, by their id in the directory, or an archive's name.");
      return;
    }
    if (action === "erase" && again.trim() !== whom) {
      setStatus("Type their id again, the same, to confirm it: an erasure can't be undone.");
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
      <PageHead title="A request for someone's data"
                about="Ask to export, or erase, all a5s keeps about someone, at their request. You sign in afresh for that request alone, and someone from the team that runs a5s carries it out." />
      <p id="status" role="status" className="note">{status}</p>
      {asked && <p><button type="button" id="another" onClick={another}>Ask about someone else</button></p>}
      {!asked && (
        <form id="ask" className="card" onSubmit={ask}>
          <p>
            <label htmlFor="action">Ask to</label>{" "}
            <select id="action" value={action} onChange={(e) => setAction(e.target.value as Action)}>
              <option value="export">export</option>
              <option value="erase">erase</option>
            </select>{" "}
            <label htmlFor="person">all a5s keeps about</label>{" "}
            <input id="person" autoComplete="off" spellCheck={false} placeholder="an id, or an archive's name"
                   value={person} onChange={(e) => setPerson(e.target.value)} />
          </p>
          {action === "erase" && (
            <p id="again">
              <label htmlFor="confirm">Their id again, since an erasure can't be undone:</label>{" "}
              <input id="confirm" autoComplete="off" spellCheck={false} value={again}
                     onChange={(e) => setAgain(e.target.value)} />
            </p>
          )}
          <p className="note">You sign in afresh, for this request alone. Someone from the team that runs a5s then carries it out, once, within ten minutes: your sign-in does nothing else.</p>
          <button className="primary" type="submit">Sign in and ask</button>
        </form>
      )}
    </>
  );
}
