// Grading samples of agents' changes, folded into the studio from its own page
// (core/grade_api.py): for people outside the team that built an agent, whose grades raise or
// lower a5s's cap on its level (core/samples.py). They see what they may grade, signed in to the
// studio, choose a grade for each they grade, and send them together, signed in again, afresh:
// that sign-in's nonce commits to exactly those grades of exactly those samples, so the identity
// provider signs them, which the core checks again and seals.

import { useEffect, useState } from "react";
import { type GradeNow, type Graded, type SampleLine, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { Icon } from "../icons";
import { PageHead, useLoad, Waiting } from "../ui";

type Grade = "right" | "wrong" | "critical";

const GRADES: Grade[] = ["right", "wrong", "critical"];
const day = (at: string) => new Date(at).toLocaleDateString([], { day: "numeric", month: "short" });

// How it went, in the colour that means it: a person's yes or no, or the agent's own change
const OUTCOMES: Record<string, [string, string]> = { approve: ["approved", "good"], reject: ["rejected", "bad"] };

/** A record's link, where its system gives it an address on the web, and nothing else. */
function linkOf(record: unknown): string | null {
  const link = record && typeof record === "object" ? (record as { link?: unknown }).link : null;
  return typeof link === "string" && /^https?:\/\//i.test(link) ? link : null;
}

/** A sample on the card decisions are made on (docs/design.md): who did it, what it did in the
 * words code worked out, never the agent's own, how it went, what code flagged, and the grade
 * chosen, which choosing again takes back. */
function Card({ sample, chosen, choose }: {
  sample: SampleLine; chosen: Grade | undefined; choose: (grade: Grade | undefined) => void;
}) {
  const [what, ...rest] = sample.said.split("\n");
  const asked = sample.kind === "proposal";
  const [outcome, tone] = asked ? (OUTCOMES[sample.decided ?? ""] ?? [sample.decided ?? "", "idle"])
    : ["made at level 2", "changes"];
  const links = Object.entries(sample.records).flatMap(([key, record]) => {
    const link = linkOf(record);
    return link ? [{ key, link }] : [];
  });
  return (
    <section className="approval sample" data-sample={sample.id} aria-labelledby={`title-${sample.id}`}>
      <div className="approval-stripe" />
      <div className="approval-body">
        <div className="who">
          <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
          <span>
            <span className="who-name">{asked ? `The ${sample.agent} asked` : `The ${sample.agent} acted on its own`}</span>
            <span className="who-about">{`${sample.action} in ${sample.part} · sampled ${day(sample.drawn_at)}`}</span>
          </span>
        </div>
        <h2 className="approval-title" id={`title-${sample.id}`}>{what}</h2>
        {rest.length > 0 && <p className="said">{rest.join("\n")}</p>}
        <p><span className={`badge ${tone}`}>{outcome}</span></p>
        {sample.flags.length > 0 && (
          <div className="approval-know">
            <p className="label">What code flagged</p>
            <ul>{sample.flags.map((flag) => <li key={flag}>{flag}</li>)}</ul>
          </div>
        )}
        {links.map(({ key, link }) => (
          <p key={key}><a href={link} rel="noopener noreferrer" target="_blank">Open {key}</a></p>
        ))}
        <div className="grades" role="group" aria-label={`Your grade for: ${what}`}>
          {GRADES.map((grade) => (
            <button key={grade} type="button" className={grade} aria-pressed={chosen === grade}
                    onClick={() => choose(chosen === grade ? undefined : grade)}>
              {grade[0].toUpperCase() + grade.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

export function GradePage() {
  const [status, setStatus] = useState<string>();
  const [chosen, setChosen] = useState<Map<number, Grade>>(new Map());
  const [acted, setActed] = useState(false);  // back from signing in to grade: sent first
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "grade") {
      setActed(true);
      return;
    }
    send<Graded>("POST", "/grade/samples", { grades: act.grades, salt: act.salt })
      .then((made) => {
        const given = Object.values(made.grades);
        setStatus(given.length === 1 ? `Graded ${given[0]}.` : `Graded ${given.length} samples.`);
      })
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setActed(true));
  }, []);
  const now = useLoad(() => (acted ? send<GradeNow>("POST", "/grade/review") : new Promise<GradeNow>(() => {})),
                      [acted]);

  const choose = (sample: number, grade: Grade | undefined) => {
    const next = new Map(chosen);
    if (grade) next.set(sample, grade);
    else next.delete(sample);
    setChosen(next);
    setStatus(next.size ? `${next.size} chosen: send them when you're ready.` : "");
  };

  const sendThem = async () => {
    try {
      // a nonce that commits to exactly these grades of exactly these samples, as
      // core/samples.py's `nonce` makes it
      const grades = [...chosen.entries()].sort((a, b) => a[0] - b[0]);
      if (!grades.length) {
        setStatus("Choose a grade for a sample first.");
        return;
      }
      const salt = salted();
      const nonce = await hashed(`a5s grades samples ${grades.map(([s, g]) => `${s}:${g}`).join(",")} ${salt}`);
      setStatus(`Signing you in again, to give ${grades.length === 1 ? "this grade" : "these grades"} alone…`);
      await signInFor({ kind: "grade", grades: Object.fromEntries(grades.map(([s, g]) => [String(s), g])), salt }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const found = now.data;
  const samples = found?.samples ?? [];
  const none = found && samples.length === 0 ? `Nothing ${status ? "else " : ""}waits for you to grade.` : "";
  return (
    <>
      <PageHead title="Agents' work to grade"
                about="Each is a change an agent asked for or made. Grade it right if it's what a careful colleague would have done with what they knew, wrong if not, and critical if it could have done real harm. Your grades decide whether agents may act on their own." />
      <p id="status" role="status" className="note">{[status, none].filter(Boolean).join(" ")}</p>
      {!found && <Waiting error={now.error} />}
      {samples.length > 0 && (
        <section id="waiting" className="bare">
          <div id="list">{samples.map((sample) => (
            <Card key={sample.id} sample={sample} chosen={chosen.get(sample.id)}
                  choose={(grade) => choose(sample.id, grade)} />
          ))}</div>
          <div className="send-bar">
            <button id="send" className="primary" type="button" onClick={sendThem}>Send the grades you chose</button>
            <p className="note">You sign in again to send them, so your sign-in covers exactly these grades.</p>
          </div>
        </section>
      )}
    </>
  );
}
