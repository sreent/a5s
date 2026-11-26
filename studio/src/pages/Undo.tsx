// A change an agent made, which its tool says how to undo (core/undoing.py): what it did, and,
// for whoever it was for and whoever decides changes like it in its record's part, undoing it
// until its time runs out, signed in afresh for that alone, as deciding is. a5s undoes it within
// a minute, once it has checked the sign-in again, while the record is as the change left it.

import { useEffect, useState } from "react";
import { get, send } from "../api";
import type * as gen from "../api.gen";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { ActingAs, ActionZone, Badge, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, useLoad, Waiting, when } from "../ui";

function Standing({ change }: { change: gen.ChangeMade }) {
  if (change.state === "undone") {
    return <p role="status"><Badge tone="good" dot>{t("Undone")}</Badge> {change.by && t("by {person}", { person: change.by })}</p>;
  }
  if (change.state === "asked" || change.state === "undoing") {
    return <p className="note" role="status">{t("a5s is undoing it, as {person} asked: within a minute, once it has checked that sign-in again.", { person: change.by ?? "" })}</p>;
  }
  if ((change.state === "refused" || change.state === "failed") && change.outcome) {
    return <p className="problem" role="alert">{t("a5s didn't undo it: {why}", { why: change.outcome })}</p>;
  }
  return null;
}

export function UndoPage({ change }: { change: string }) {
  const toast = useToast();
  const [again, setAgain] = useState(0);  // to read how it stands again, once something's asked
  const [problem, setProblem] = useState<string>();
  const found = useLoad(() => get<gen.ChangeMade>(`/studio/api/changes/${encodeURIComponent(change)}`),
                        [change, again]);
  useEffect(() => {  // back from signing in to undo it: ask a5s to, once
    const act = takeAct();
    if (act?.kind !== "undo" || act.change !== change) return;
    send<gen.UndoAsked>("POST", `/studio/api/changes/${encodeURIComponent(change)}/undo`, { salt: act.salt })
      .then(() => {
        setAgain((n) => n + 1);
        toast(t("You asked to undo it: a5s does it within a minute."));
      })
      .catch((e: Error) => setProblem(e.message));
  }, [change, toast]);
  const state = found.data?.state;
  useEffect(() => {  // while a5s undoes it, look again every few seconds
    if (state !== "asked" && state !== "undoing") return;
    const timer = setTimeout(() => setAgain((n) => n + 1), 3000);
    return () => clearTimeout(timer);
  }, [state, again]);
  const undo = () => {
    setProblem(undefined);
    const salt = salted();  // the act's nonce, as core/undoing.py's `nonce` makes it
    hashed(`a5s undo change ${change} ${salt}`)
      .then((nonce) => signInFor({ kind: "undo", change, salt }, nonce))
      .catch((e: Error) => setProblem(e.message));
  };
  const c = found.data;
  return (
    <>
      <ActingAs acting={c?.acting} />
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }]}
                title={c ? t("A change the {agent} made", { agent: c.agent }) : t("A change an agent made")}
                about={t("Whoever it was for, and whoever decides changes like it in its record's part, may undo it for a while after it's made. Undoing it counts against the agent's accuracy, as a wrong grade of its work.")} />
      {!c && <Waiting error={found.error} />}
      {c && (
        <section className="card" id="change" aria-labelledby="change-title">
          <h2 id="change-title" className="mono">{c.record}</h2>
          <p id="said">{c.said}</p>
          <dl className="facts-sm">
            <dt>{t("For")}</dt><dd>{c.whom.join(", ") || t("nobody")}</dd>
            <dt>{t("Made")}</dt><dd>{when(c.made_at)}</dd>
            <dt>{t("Can be undone until")}</dt><dd>{when(c.until)}</dd>
          </dl>
          <Standing change={c} />
          {problem && <p className="problem" role="alert">{problem}</p>}
          {c.may  /* it reaches the record, for everyone who reads it: a zone, saying so first (docs/design.md) */
            ? <ActionZone title={t("Undo it")} level={3}
                          reach={t("Undoing it puts {record} back as it was before the {agent} changed it, for everyone who reads it, within a minute, so long as nobody has changed it since. a5s tells {whom} and those who run the {agent}, in their digests, and it counts against the {agent}'s accuracy, as a wrong grade of its work. You sign in again, for this alone.",
                                   { record: c.record, agent: c.agent, whom: c.whom.join(` ${t("and")} `) || t("whoever it was for") })}>
                <button type="button" id="undo" className="primary" onClick={undo}>{t("Sign in and undo it")}</button>
              </ActionZone>
            : c.why_not && c.state === "kept" && <p className="note" id="why-not">{t("You can't undo it: {why}.", { why: c.why_not })}</p>}
        </section>
      )}
    </>
  );
}
