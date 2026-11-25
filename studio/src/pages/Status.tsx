// The Status page (core/status_api.py): how a5s is doing, as the core last said, for the team
// that runs it. What needs someone comes first, now, out of hours too, or in working hours,
// each with its runbook's section; then the release a5s is, and the last day's lines, as
// `a5s status` says them. A record gone stale is itself what needs someone.

import { useEffect, useState } from "react";
import { get, type StatusNow } from "../api";
import { t } from "../i18n";
import { PageHead, Waiting } from "../ui";

const ABOUT = "How a5s is doing, as the core last said: what needs someone, now or in working hours, then the last day.";

/** How long ago the core said it, in words. */
function ago(seconds: number): string {
  if (seconds < 90) return t("a moment ago");
  const minutes = Math.round(seconds / 60);
  return minutes < 90 ? t("{n} minutes ago", { n: minutes })
    : t("{n} hours ago", { n: Math.round(minutes / 60) });
}

export function StatusPage() {
  const [now, setNow] = useState<StatusNow>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    get<StatusNow>("/status/api").then(setNow).catch((e) => setError(String(e)));
  }, []);
  if (error) return <><PageHead title={t("Status")} about={t(ABOUT)} /><Waiting error={error} /></>;
  if (!now) return <><PageHead title={t("Status")} about={t(ABOUT)} /><Waiting /></>;
  return (
    <div className="page">
      <PageHead title={t("Status")} about={t(ABOUT)}>
        <p className="meta" id="seen">{now.seen_seconds_ago == null ? t("The core hasn't said yet.")
          : t("As the core said it {when}.", { when: ago(now.seen_seconds_ago) })}</p>
      </PageHead>
      <section className="card wide" id="verdict" aria-labelledby="verdict-title">
        <h2 id="verdict-title">{now.verdict}</h2>
        {now.needs.length > 0 && (
          <ul className="needs">{now.needs.map((need) => (
            <li key={need.said} className={need.when === "now" ? "now" : "later"}>
              <span className={need.when === "now" ? "badge bad" : "badge warn"}>
                {need.when === "now" ? t("Now") : t("In working hours")}</span>{" "}
              {need.said}. <span className="runbook">{t("What to do:")} <code>{need.runbook}</code></span>
            </li>
          ))}</ul>
        )}
        {now.release && <p className="note" id="release">{now.release}</p>}
      </section>
      {now.day.length > 0 && (
        <section className="card wide" id="day" aria-labelledby="day-title">
          <h2 id="day-title">{t("The last day")}</h2>
          <ul className="day">{now.day.map((line) => <li key={line}>{line}</li>)}</ul>
        </section>
      )}
    </div>
  );
}
