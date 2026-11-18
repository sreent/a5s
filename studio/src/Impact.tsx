// What a version of the settings would have done differently (core/impact.py): the agents' tool
// calls of the last weeks, decided again as the version in force decides them and as this one
// would, beside what it says in words, so whoever reviews or approves it sees how far a change
// to one part reaches in what agents really did.

import type { Impact } from "./api";
import { Badge, type Tone } from "./design";
import { t } from "./i18n";
import { plural, Wide } from "./ui";

const DECIDED: Record<string, [string, Tone]> = {  // each in the language spoken whenever it's read
  get allow(): [string, Tone] { return [t("made alone"), "good"]; },
  get hold(): [string, Tone] { return [t("held for a person"), "warn"]; },
  get deny(): [string, Tone] { return [t("refused"), "bad"]; },
};

function Decided({ label }: { label: string }) {
  const [words, tone] = DECIDED[label] ?? [label, "idle"];
  return <Badge tone={tone}>{words}</Badge>;
}

export function ImpactPreview({ impact, id = "impact" }: { impact: Impact; id?: string }) {
  const calls = plural(impact.calls, "tool call");
  const looked = impact.limited ? t("{calls} agents made in the last {days} days, the latest of them,", { calls, days: impact.days })
    : t("{calls} agents made in the last {days} days", { calls, days: impact.days });
  return (
    <div id={id} className="impact">
      <h3>{t("What it would have done differently")}</h3>
      {impact.shifts.length === 0 ? (
        <p className="note">{impact.calls
          ? t("It would have decided each of the {looked} as the version in force did.", { looked })
          : t("Agents made no tool calls in the last {days} days that it could decide again.", { days: impact.days })}</p>
      ) : (
        <>
          <p className="note">{t("Of the {looked} decided again as this version would decide them:", { looked })}</p>
          <Wide label={t("Calls this version would decide differently")}>
            <table>
              <thead><tr><th>{t("Calls")}</th><th>{t("Tool")}</th><th>{t("Instance")}</th><th>{t("Parts")}</th><th>{t("In force")}</th><th>{t("This version")}</th><th>{t("Why")}</th></tr></thead>
              <tbody>{impact.shifts.map((shift) => (
                <tr key={`${shift.instance}/${shift.tool}/${shift.parts.join(",")}/${shift.was}/${shift.would}`}>
                  <td>{shift.calls}</td><td className="mono">{shift.tool}</td><td>{shift.instance}</td>
                  <td>{shift.parts.join(", ") || t("none")}</td>
                  <td><Decided label={shift.was} /></td><td><Decided label={shift.would} /></td>
                  <td>{shift.why}</td>
                </tr>
              ))}</tbody>
            </table>
          </Wide>
        </>
      )}
      {impact.hidden > 0 && <p className="note" id={`${id}-hidden`}>{t("It counts {calls} of instances you may not watch as they were decided, and shows nothing of them here.", { calls: plural(impact.hidden, "tool call") })}</p>}
      {impact.capped.length > 0 && <ul className="plain notes">{impact.capped.map((c) => <li key={c}>{c}</li>)}</ul>}
      {(impact.beyond ?? []).length > 0 && <ul id={`${id}-beyond`} className="plain notes">{(impact.beyond ?? []).map((b) => <li key={b}>{b}</li>)}</ul>}
      <p className="note">{impact.about}</p>
    </div>
  );
}
