// Deciding the changes agents asked for, folded into the studio from its own page
// (core/decide_api.py): the page a decider's card opens. They see what waits for them, signed in
// to the studio, and decide signed in again, afresh: that sign-in's nonce commits to approving or
// rejecting exactly the changes they chose, and to a rejection's reason as they wrote it, so the
// identity provider signs the decision, which the core checks again, seals and acts on.

import { useEffect, useState } from "react";
import { type DecideNow, type Decided, type HeldChange, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { locale, t } from "../i18n";
import { Icon } from "../icons";
import { ActingAs, ActionZone, useToast } from "../design";
import { PageHead, useLoad, Waiting } from "../ui";

type Decision = "approve" | "reject";

const day = (at: string) => new Date(at).toLocaleDateString(locale(), { day: "numeric", month: "short" });

/** What a change its tool says no way to reverse adds to its zone, which is marked so: deciding
 * it is as hard to undo as erasing, so the page says it first (docs/design.md; round 17, B4). */
const LASTS = "a5s can't undo it once it's made.";

/** A held change on the approval card (docs/design.md), made for a phone: who asks and for whom,
 * what it does in the words code worked out when it was asked for, never the agent's own, what to
 * know, and the decider's yes or no. */
function Card({ change, decide, ticked, tick, together }: {
  change: HeldChange; decide: (digests: string[], decision: Decision, reason: string) => void;
  ticked: boolean; tick: (on: boolean) => void; together: boolean;  // others it may go with
}) {
  const [reason, setReason] = useState("");
  const [what, ...rest] = change.said.split("\n");
  const about = [change.key, change.for.length ? t("for {whom}", { whom: change.for.join(` ${t("and")} `) }) : "",
                 t("asked {day}", { day: day(change.proposed_at) })]
    .filter(Boolean).join(" · ");
  const know = change.sensitive || change.changed.length > 0 || change.flags.length > 0;
  return (
    <section className="approval" data-proposal={change.key} aria-labelledby={`title-${change.key}`}>
      <div className="approval-stripe" />
      <div className="approval-body">
        <div className="who">
          <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
          <span><span className="who-name">{t("The {agent} asks", { agent: change.agent })}</span><span className="who-about">{about}</span></span>
        </div>
        <h2 className="approval-title" id={`title-${change.key}`}>{what}</h2>
        {rest.length > 0 && <p className="said">{rest.join("\n")}</p>}
        {know && (
          <div className="approval-know">
            <p className="label">{t("What to know")}</p>
            {change.sensitive && <ul className="flags sensitive"><li>{t("It's decided on its own, never with others.")}</li></ul>}
            {change.changed.length > 0 && <ul className="flags changed">{change.changed.map((c) => <li key={c}>{c}</li>)}</ul>}
            {change.flags.length > 0 && <ul className="flags">{change.flags.map((f) => <li key={f}>{f}</li>)}</ul>}
          </div>
        )}
        {change.records.filter((r) => /^https?:\/\//i.test(r.link)).map((record) => (  // a web page, and nothing else
          <p key={record.key}><a href={record.link} rel="noopener noreferrer" target="_blank">{t("Open {record}", { record: record.key })}</a></p>
        ))}
        <p className="note">{t("It lapses on {day} unless someone decides it.",
          { day: new Date(change.lapses_at).toLocaleDateString(locale(), { dateStyle: "medium" }) })}</p>
        {!change.may_decide
          ? <p className="note">{t("You can see it, as you were told it waits, but only its deciders decide it.")}</p>
          : (
            <>
              <ActionZone title={t("Decide {key}", { key: change.key })} level={3} stacked cantUndo={!change.undoable} reach={`${change.for.length
                ? t("Approving it, the {agent} makes this change for {whom} within a minute, once every part it touches has approved it, if its records haven't changed. Rejecting it, a5s tells whoever asked, with your reason if you give one.",
                    { agent: change.agent, whom: change.for.join(` ${t("and")} `) })
                : t("Approving it, the {agent} makes this change within a minute, once every part it touches has approved it, if its records haven't changed. Rejecting it, a5s tells whoever asked, with your reason if you give one.",
                    { agent: change.agent })}${change.undoable ? "" : ` ${t(LASTS)}`}`}>
                <input type="text" maxLength={300} placeholder={t("Why, if you reject it (optional)")} value={reason}
                       aria-label={t("Why you reject {key}, if you do", { key: change.key })} onChange={(e) => setReason(e.target.value)} />
                <div className="approval-actions">
                  <button type="button" className="primary" onClick={() => decide([change.digest], "approve", "")}>{t("Approve")}</button>
                  <button type="button" onClick={() => decide([change.digest], "reject", reason.trim())}>{t("Reject")}</button>
                </div>
              </ActionZone>
              {!change.sensitive && together && (  /* only where there are others to go with (round 13, C14) */
                <label className="tick-label">
                  <input type="checkbox" className="tick" checked={ticked} onChange={(e) => tick(e.target.checked)} />
                  <span>{t("Decide it with the others ticked")}</span>
                </label>
              )}
              <p className="approval-signed"><Icon name="audit" /><span>{t("Deciding signs you in again, for this decision alone, and the ledger keeps it.")}</span></p>
            </>
          )}
      </div>
    </section>
  );
}

export function DecidePage() {
  const toast = useToast();
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
      .then((made) => {
        const which = made.decided.join(", ");
        const done = made.decision === "approve" ? t("You approved {which}.", { which }) : t("You rejected {which}.", { which });
        const waits = made.waits ?? [];  /* one approval alone doesn't make it, such as above an amount */
        setStatus(`${done} ${made.decision !== "approve" ? t("a5s tells whoever asked for it.")
          : waits.length ? t("{which} waits for another of its deciders: a5s makes it once they've approved it too.",
                             { which: waits.join(", ") })
          : t("a5s makes each change within a minute, once every part it touches has approved it, if its records haven't changed.")}`);
        toast(done);
      })
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
      const one = digests.length === 1;
      setStatus(decision === "approve"
        ? (one ? t("Signing you in again, to approve this change alone…") : t("Signing you in again, to approve these changes alone…"))
        : (one ? t("Signing you in again, to reject this change alone…") : t("Signing you in again, to reject these changes alone…")));
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
  const lasting = waiting.some((p) => ticked.has(p.digest) && !p.undoable);  // one ticked can't be undone
  return (
    <>
      <ActingAs acting={found?.acting} />
      <PageHead title={t("Changes to decide")}
                about={t("An agent asked for each of these, and it waits for you. Decide only what you mean: deciding signs you in again, and your sign-in decides once.")} />
      <p id="status" role="status" className="note">{status ?? (found && waiting.length === 0 ? t("Nothing waits for your decision.") : "")}</p>
      {!found && <Waiting error={now.error} />}
      {waiting.length > 0 && (
        <section id="waiting" className="bare">
          <div id="list">{waiting.map((change) => (
            <Card key={change.digest} change={change} decide={decide} ticked={ticked.has(change.digest)} together={together}
                  tick={(on) => setTicked((was) => {
                    const next = new Set(was);
                    if (on) next.add(change.digest);
                    else next.delete(change.digest);
                    return next;
                  })} />
          ))}</div>
          {together && (
            <div id="together">
              <ActionZone title={t("Decide the ticked ones together")} cantUndo={lasting}
                          reach={`${t("Each change you ticked is decided as you choose here, as if one at a time: approved, each agent makes its change within a minute, once every part it touches has approved it; rejected, a5s tells whoever asked. You sign in again, for exactly these.")}${lasting ? ` ${t("Some you ticked a5s can't undo once they're made, as their cards say.")}` : ""}`}>
                <button id="approve-ticked" type="button" onClick={() => ticked.size && decide([...ticked], "approve", "")}>{t("Approve the ticked ones")}</button>
                <button id="reject-ticked" type="button" onClick={() => ticked.size && decide([...ticked], "reject", "")}>{t("Reject the ticked ones")}</button>
              </ActionZone>
            </div>
          )}
        </section>
      )}
      {decided.length > 0 && (
        <section className="card" id="earlier">
          <h2>{t("Decided lately")}</h2>
          <ul id="decided" className="plain">{decided.map((change) => (
            <li key={change.digest}>{change.outcome || t("{key}: you've decided it, and a5s acts on it within a minute.", { key: change.key })}</li>
          ))}</ul>
          <button type="button" className="ghost" onClick={() => setAgain((n) => n + 1)}>{t("Look again")}</button>
        </section>
      )}
    </>
  );
}
