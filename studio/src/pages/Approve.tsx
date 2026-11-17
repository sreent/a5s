// Approving a version of a5s's settings, folded into the studio from its own page
// (core/approve_api.py): the page an approver's card opens. They read what the version
// changes, as code works it out, and all of it, signed in to the studio; and approve it signed
// in again, afresh, for that version alone: the sign-in's nonce commits to approving exactly
// this version, so the identity provider signs the approval, which the core checks again, seals
// and counts.

import { useEffect, useState } from "react";
import { type Approved, get, send, type VersionReview } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { useToast } from "../design";
import { language, locale, t } from "../i18n";
import { ImpactPreview } from "../Impact";
import { PageHead, useLoad, Waiting } from "../ui";

const VERSION = /^[0-9a-f]{64}$/;

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

const missing = (needs: string[]) => (needs.length
  ? t("It goes in force once nothing more is missing: {needs}.", { needs: needs.join("; ") })
  : t("a5s puts it in force within a minute, as it needs nothing more."));

/** Where the version stands, on its card: a word, in the colour that means it, and what it means. */
function standing(seen: VersionReview): [string, string, string] {
  if (seen.status === "applied") return [t("in force"), "good", t("It's been approved and applied already.")];
  if (seen.status === "superseded") {
    return [t("superseded"), "idle", t("A newer version is in force, so this one can't be approved any more.")];
  }
  if (seen.status !== "waiting") {
    return [t("refused"), "bad", t("a5s couldn't apply it: {why}", { why: seen.status.replace(/^refused: /, "") })];
  }
  if (seen.you_approved) return [t("you approved it"), "good", `${t("You've approved it.")} ${missing(seen.needs)}`];
  return [t("waiting for you"), "warn", ""];
}

export function ApprovePage({ version }: { version: string }) {
  const toast = useToast();
  const named = VERSION.test(version);
  const [status, setStatus] = useState<string>();
  const [acted, setActed] = useState(false);  // back from signing in to approve: approved first
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "approve" || act.version !== version) {
      setActed(true);
      return;
    }
    send<Approved>("POST", `/approve/settings/${version}`, { salt: act.salt })
      .then((done) => {
        const approved = t("You approved version {serial}.", { serial: done.serial });
        setStatus(`${approved} ${missing(done.needs)}`);
        toast(approved);
      })
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setActed(true));
  }, [version]);
  const seen = useLoad(() => (named && acted ? get<VersionReview>(`/approve/settings/${version}`)
    : new Promise<VersionReview>(() => {})), [acted]);

  const approve = async () => {
    try {
      // a nonce that commits to approving this version alone, as core/approvals.py's `nonce`
      // makes it
      const salt = salted();
      const nonce = await hashed(`a5s approves settings ${version} ${salt}`);
      setStatus(t("Signing you in again, to approve this version alone…"));
      await signInFor({ kind: "approve", version, salt }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const found = seen.data;
  const [word, tone, means] = found ? standing(found) : ["", "", ""];
  const proposed = found ? new Date(found.proposed_at).toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" }) : "";
  return (
    <>
      <PageHead title={t("Settings to approve")}
                about={t("A version of the settings waits for your approval. Read what it changes, and all of it; approving signs you in again, for this version alone.")} />
      <p id="status" role="status" className="note">
        {!named ? t("This link doesn't name a version of the settings. Open the one on your card.") : status ?? means}
      </p>
      {named && !found && <Waiting error={seen.error} />}
      {found && (
        <section id="version" className="approval version" aria-labelledby="title">
          <div className="approval-stripe own" />
          <div className="approval-body">
            <div id="asker" className="who">
              {found.asked_by
                ? (
                  <>
                    <span className="avatar" aria-hidden="true">{initials(found.asked_by)}</span>
                    <span><span className="who-name">{t("{who} asked for it", { who: found.asked_by })}</span>
                      <span className="who-about">{t("proposed {when}", { when: proposed })}</span></span>
                  </>
                )
                : <span><span className="who-about">{t("Proposed {when}", { when: proposed })}</span></span>}
            </div>
            <div className="title-row">
              <h2 id="title" className="approval-title">{t("Version {serial} of the settings", { serial: found.serial })}</h2>
              <span id="standing" className={`badge ${tone}`}>{word}</span>
            </div>
            {language() !== "en" && <p id="in-english" className="note">{t("What a version changes, and the whole of it, are in English, as a5s works them out from the settings: read them before you approve.")}</p>}
            <div>
              <p id="summary" className="label">{found.in_force === null
                ? t("What it sets, with nothing in force yet")
                : t("What it changes from version {serial}, the one in force", { serial: found.in_force })}</p>
              <ul id="changes" className="changes">{found.changes.map((change) => (
                <li key={change.text}>{change.text}{change.widens && <> <span className="badge changes">{t("widens what agents do")}</span></>}</li>
              ))}</ul>
            </div>
            <dl className="approval-changes">
              <div className="pair"><dt>{t("Approved so far by")}</dt>
                <dd id="approvals">{found.approved_by.length ? found.approved_by.join(", ") : t("nobody yet")}</dd></div>
              {found.needs.length > 0 && <div id="needs-row" className="pair"><dt>{t("What's missing")}</dt><dd id="needs">{found.needs.join("; ")}</dd></div>}
            </dl>
            <div>
              <p className="label">{t("The whole version, as it would be")}</p>
              <ul id="whole" className="plain well">{found.whole.map((line) => <li key={line}>{line}</li>)}</ul>
            </div>
            {found.impact && <ImpactPreview impact={found.impact} />}
            {found.status === "waiting" && !found.you_approved && (
              <div id="decision" className="decision">
                <div className="approval-actions">
                  <button id="approve" className="primary" type="button" onClick={approve}>{t("Approve version {serial}", { serial: found.serial })}</button>
                </div>
                <p className="approval-signed">{t("Approve only if you mean these changes. Approving signs you in again, for this version alone, and only once.")}</p>
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}
