// What a version of the settings would have done differently (core/impact.py): the agents' tool
// calls of the last weeks, decided again as the version in force decides them and as this one
// would, beside what it says in words, so whoever reviews or approves it sees how far a change
// to one part reaches in what agents really did.

import type { Impact } from "./api";
import { Badge, type Tone } from "./design";
import { plural, Wide } from "./ui";

const DECIDED: Record<string, [string, Tone]> = {
  allow: ["made alone", "good"], hold: ["held for a person", "warn"], deny: ["refused", "bad"],
};

function Decided({ label }: { label: string }) {
  const [words, tone] = DECIDED[label] ?? [label, "idle"];
  return <Badge tone={tone}>{words}</Badge>;
}

export function ImpactPreview({ impact, id = "impact" }: { impact: Impact; id?: string }) {
  const looked = `${plural(impact.calls, "tool call")} agents made in the last ${impact.days} days${
    impact.limited ? ", the latest of them," : ""}`;
  return (
    <div id={id} className="impact">
      <h3>What it would have done differently</h3>
      {impact.shifts.length === 0 ? (
        <p className="note">{impact.calls
          ? `It would have decided each of the ${looked} as the version in force did.`
          : `Agents made no tool calls in the last ${impact.days} days that it could decide again.`}</p>
      ) : (
        <>
          <p className="note">Of the {looked} decided again as this version would decide them:</p>
          <Wide label="Calls this version would decide differently">
            <table>
              <thead><tr><th>Calls</th><th>Tool</th><th>Instance</th><th>Parts</th><th>In force</th><th>This version</th><th>Why</th></tr></thead>
              <tbody>{impact.shifts.map((shift) => (
                <tr key={`${shift.instance}/${shift.tool}/${shift.parts.join(",")}/${shift.was}/${shift.would}`}>
                  <td>{shift.calls}</td><td className="mono">{shift.tool}</td><td>{shift.instance}</td>
                  <td>{shift.parts.join(", ") || "none"}</td>
                  <td><Decided label={shift.was} /></td><td><Decided label={shift.would} /></td>
                  <td>{shift.why}</td>
                </tr>
              ))}</tbody>
            </table>
          </Wide>
        </>
      )}
      {impact.capped.length > 0 && <ul className="plain notes">{impact.capped.map((c) => <li key={c}>{c}</li>)}</ul>}
      <p className="note">{impact.about}</p>
    </div>
  );
}
