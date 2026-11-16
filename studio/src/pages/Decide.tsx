// Deciding the changes agents asked for, folded into the studio from its own page
// (core/decide_api.py): the page a decider's card opens. They see what waits for them, signed in
// to the studio, and decide signed in again, afresh: that sign-in's nonce commits to approving or
// rejecting exactly the changes they chose, and to a rejection's reason as they wrote it, so the
// identity provider signs the decision, which the core checks again, seals and acts on.

import { useEffect, useState } from "react";
import { type DecideNow, type Decided, type HeldChange, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { Icon } from "../icons";
import { PageHead, useLoad, Waiting } from "../ui";

type Decision = "approve" | "reject";

const day = (at: string) => new Date(at).toLocaleDateString([], { day: "numeric", month: "short" });

/** A held change on the approval card (docs/design.md), made for a phone: who asks and for whom,
 * what it does in the words code worked out when it was asked for, never the agent's own, what to
 * know, and the decider's yes or no. */
function Card({ change, decide, ticked, tick }: {
  change: HeldChange; decide: (digests: string[], decision: Decision, reason: string) => void;
  ticked: boolean; tick: (on: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const [what, ...rest] = change.said.split("\n");
  const about = [change.key, change.for.length ? `for ${change.for.join(" and ")}` : "", `asked ${day(change.proposed_at)}`]
    .filter(Boolean).join(" · ");
  const know = change.sensitive || change.changed.length > 0 || change.flags.length > 0;
  return (
    <section className="approval" data-proposal={change.key} aria-labelledby={`title-${change.key}`}>
      <div className="approval-stripe" />
      <div className="approval-body">
        <div className="who">
          <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
          <span><span className="who-name">The {change.agent} asks</span><span className="who-about">{about}</span></span>
        </div>
        <h2 className="approval-title" id={`title-${change.key}`}>{what}</h2>
        {rest.length > 0 && <p className="said">{rest.join("\n")}</p>}
        {know && (
          <div className="approval-know">
            <p className="label">What to know</p>
            {change.sensitive && <ul className="flags sensitive"><li>It's decided on its own, never with others.</li></ul>}
            {change.changed.length > 0 && <ul className="flags changed">{change.changed.map((c) => <li key={c}>{c}</li>)}</ul>}
            {change.flags.length > 0 && <ul className="flags">{change.flags.map((f) => <li key={f}>{f}</li>)}</ul>}
          </div>
        )}
        {change.records.filter((r) => /^https?:\/\//i.test(r.link)).map((record) => (  // a web page, and nothing else
          <p key={record.key}><a href={record.link} rel="noopener noreferrer" target="_blank">Open {record.key}</a></p>
        ))}
        <p className="note">It lapses on {new Date(change.lapses_at).toLocaleDateString([], { dateStyle: "medium" })} unless someone decides it.</p>
        {!change.may_decide
          ? <p className="note">You can see it, as you were told it waits, but only its deciders decide it.</p>
          : (
            <>
              <input type="text" maxLength={300} placeholder="Why, if you reject it (optional)" value={reason}
                     aria-label={`Why you reject ${change.key}, if you do`} onChange={(e) => setReason(e.target.value)} />
              <div className="approval-actions">
                <button type="button" className="primary" onClick={() => decide([change.digest], "approve", "")}>Approve</button>
                <button type="button" onClick={() => decide([change.digest], "reject", reason.trim())}>Reject</button>
              </div>
              {!change.sensitive && (
                <label className="tick-label">
                  <input type="checkbox" className="tick" checked={ticked} onChange={(e) => tick(e.target.checked)} />
                  <span>Decide it with the others ticked</span>
                </label>
              )}
              <p className="approval-signed"><Icon name="audit" /><span>Deciding signs you in again, for this decision alone, and the ledger keeps it.</span></p>
            </>
          )}
      </div>
    </section>
  );
}

export function DecidePage() {
  const [named] = useState(() => new URLSearchParams(location.search).get("proposal") || "");
  const [again, setAgain] = useState(0);
  const [status, setStatus] = useState<string>();
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [acted, setActed] = useState(false);  // back from signing in to decide: carried out first
  useEffect(() => {
    if (location.search) history.replaceState(null, "", "/studio/decide");  // the card's, used once
    const act = takeAct();
    if (act?.kind !== "decide") {
      setActed(true);
      return;
    }
    send<Decided>("POST", "/decide/proposals", { proposals: act.proposals, decision: act.decision, salt: act.salt,
                                                ...(act.reason ? { reason: act.reason } : {}) })
      .then((made) => setStatus(made.decision === "approve"
        ? `You approved ${made.decided.join(", ")}. a5s makes each change within a minute, once every part it touches has approved it, if its records haven't changed.`
        : `You rejected ${made.decided.join(", ")}. a5s tells whoever asked for it.`))
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setActed(true));
  }, []);
  const now = useLoad(() => (acted ? send<DecideNow>("POST", "/decide/review") : new Promise<DecideNow>(() => {})),
                      [acted, again]);

  const decide = async (digests: string[], decision: Decision, reason: string) => {
    try {
      // a nonce that commits to this decision on exactly these changes, and to a rejection's
      // reason as it's written here, as core/proposals.py's `nonce` makes it
      const said = decision === "reject" && reason ? reason : null;
      const proposals = [...digests].sort();
      const salt = salted();
      const words = said ? ` said ${await hashed(said)}` : "";
      const nonce = await hashed(`a5s ${decision}s proposals ${proposals.join(",")} ${salt}${words}`);
      setStatus(`Signing you in again, to ${decision} ${digests.length === 1 ? "this change" : "these changes"} alone…`);
      await signInFor({ kind: "decide", proposals, decision, salt, reason: said }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const found = now.data;
  const waiting = (found?.proposals ?? []).filter((p) => p.status === "waiting" && !p.yours)
    .sort((a, b) => Number(b.digest === named) - Number(a.digest === named));
  const decided = (found?.proposals ?? []).filter((p) => p.status !== "waiting" || p.yours);
  const together = waiting.filter((p) => p.may_decide && !p.sensitive).length >= 2;
  return (
    <>
      <PageHead title="Changes to decide"
                about="An agent asked for each of these, and it waits for you. Decide only what you mean: deciding signs you in again, and your sign-in decides once." />
      <p id="status" role="status" className="note">{status ?? (found && waiting.length === 0 ? "Nothing waits for your decision." : "")}</p>
      {!found && <Waiting error={now.error} />}
      {waiting.length > 0 && (
        <section id="waiting" className="bare">
          <div id="list">{waiting.map((change) => (
            <Card key={change.digest} change={change} decide={decide} ticked={ticked.has(change.digest)}
                  tick={(on) => setTicked((was) => {
                    const next = new Set(was);
                    if (on) next.add(change.digest);
                    else next.delete(change.digest);
                    return next;
                  })} />
          ))}</div>
          {together && (
            <div className="actions" id="together">
              <button id="approve-ticked" type="button" onClick={() => ticked.size && decide([...ticked], "approve", "")}>Approve the ticked ones</button>
              <button id="reject-ticked" type="button" onClick={() => ticked.size && decide([...ticked], "reject", "")}>Reject the ticked ones</button>
            </div>
          )}
        </section>
      )}
      {decided.length > 0 && (
        <section className="card" id="earlier">
          <h2>Decided lately</h2>
          <ul id="decided" className="plain">{decided.map((change) => (
            <li key={change.digest}>{change.outcome || `${change.key}: you've decided it, and a5s acts on it within a minute.`}</li>
          ))}</ul>
          <button type="button" className="ghost" onClick={() => setAgain((n) => n + 1)}>Look again</button>
        </section>
      )}
    </>
  );
}
