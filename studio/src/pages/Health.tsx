// The model health page (core/health_api.py): each model's day, measured: its calls,
// failures, stalls, mean time, whether its SLO gates it, and its canary scores. For the
// engineers and the release approver, whose evidence a model change or a restore is.

import { useEffect, useState } from "react";
import { get, type HealthNow } from "../api";
import { t } from "../i18n";
import { PageHead, To, Waiting } from "../ui";

/** What the page is, said the same as it loads, if it can't, and once it has. */
const ABOUT = "Each model's day, measured: what its calls did, and what its canaries scored.";

export function HealthPage() {
  const [now, setNow] = useState<HealthNow>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    get<HealthNow>("/health/api").then(setNow).catch((e) => setError(String(e)));
  }, []);
  if (error) return <><PageHead title={t("Model health")} about={t(ABOUT)} /><Waiting error={error} /></>;
  if (!now) return <><PageHead title={t("Model health")} about={t(ABOUT)} /><Waiting /></>;
  return (
    <div className="page">
      <PageHead title={t("Model health")}
                 about={t(ABOUT)} />
      <table className="health">
        <thead><tr><th>{t("Model")}</th><th>{t("Calls")}</th><th>{t("Failed")}</th>
          <th>{t("Stalls")}</th><th>{t("Mean time")}</th><th>{t("Canaries")}</th></tr></thead>
        <tbody>{now.models.map((m) => (
          <tr key={m.model} className={m.gated_at ? "gated" : ""}>
            <td><strong>{m.model}</strong>{m.gated_at ?
                <span className="badge">{t("stopped until the release approver puts it back")}</span> : null}
              {m.reaches && <p className="note reaches">{t("Putting it back: {reaches}", { reaches: m.reaches })}</p>}</td>
            <td>{m.calls}</td><td>{m.failed}</td><td>{m.stalls}</td>
            <td>{m.mean_seconds == null ? "—" : m.mean_seconds + "s"}</td>
            <td>{m.canary_passed} {t("passed")} · {m.canary_failed} {t("failed")}</td>
          </tr>
        ))}</tbody>
      </table>
      <p className="note">{t("The release approver puts a stopped model back with a5s health --restore, signed in, and the ledger records who did.")}</p>
      <p className="note">
        <To go="/studio/settings">{t("Which model each instance runs on is a setting its owners approve.")}</To>
      </p>
    </div>
  );
}