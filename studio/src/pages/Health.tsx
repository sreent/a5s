// The model health page (core/health_api.py): each model's day, measured: its calls,
// failures, stalls, mean time, whether its SLO gates it, and its canary scores. For the
// engineers and the release approver, whose evidence a model change or a restore is.

import { useEffect, useState } from "react";
import { get, type HealthNow } from "../api";
import { t } from "../i18n";
import { PageHead, To, Waiting } from "../ui";

export function HealthPage() {
  const [now, setNow] = useState<HealthNow>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    get<HealthNow>("/health/api").then(setNow).catch((e) => setError(String(e)));
  }, []);
  if (error) return <><PageHead title={t("Model health")} /><Waiting error={error} /></>;
  if (!now) return <><PageHead title={t("Model health")} /><Waiting /></>;
  return (
    <div className="page">
      <PageHead title={t("Model health")}
                 about={t("Each model's day, measured: what its calls did, and what its canaries scored.")} />
      <table className="health">
        <thead><tr><th>{t("Model")}</th><th>{t("Calls")}</th><th>{t("Failed")}</th>
          <th>{t("Stalls")}</th><th>{t("Mean time")}</th><th>{t("Canaries")}</th></tr></thead>
        <tbody>{now.models.map((m) => (
          <tr key={m.model} className={m.gated_at ? "gated" : ""}>
            <td><strong>{m.model}</strong>{m.gated_at ?
                <span className="badge">{t("stopped: a person restores it")}</span> : null}</td>
            <td>{m.calls}</td><td>{m.failed}</td><td>{m.stalls}</td>
            <td>{m.mean_seconds == null ? "—" : m.mean_seconds + "s"}</td>
            <td>{m.canary_passed} {t("passed")} · {m.canary_failed} {t("failed")}</td>
          </tr>
        ))}</tbody>
      </table>
      <p className="note">
        <To go="/studio/settings">{t("Which model each instance runs on is a setting its owners approve.")}</To>
      </p>
    </div>
  );
}