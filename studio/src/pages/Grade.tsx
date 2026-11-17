// Grading samples of agents' changes, folded into the studio from its own page
// (core/grade_api.py): for people outside the team that built an agent, whose grades raise or
// lower a5s's cap on its level (core/samples.py). They see what they may grade, signed in to the
// studio, choose a grade for each they grade, and send them together, signed in again, afresh:
// that sign-in's nonce commits to exactly those grades of exactly those samples, so the identity
// provider signs them, which the core checks again and seals.

import { useEffect, useState } from "react";
import { type GradeNow, type Graded, type SampleLine, send } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { locale, t } from "../i18n";
import { Icon } from "../icons";
import { useToast } from "../design";
import { PageHead, plural, useLoad, Waiting } from "../ui";
import { keepUnkept, keptNow, unkept } from "../unkept";

const CHOSEN = "grades";

type Grade = "right" | "wrong" | "critical";

const GRADES: Grade[] = ["right", "wrong", "critical"];
const day = (at: string) => new Date(at).toLocaleDateString(locale(), { day: "numeric", month: "short" });

/** A grade's name on its button, in the language spoken: what's sent is the grade itself. */
const named = (grade: Grade) => (grade === "right" ? t("Right") : grade === "wrong" ? t("Wrong") : t("Critical"));

/** That a grade was given, in words. */
const graded = (grade: string) => (grade === "right" ? t("Graded right.") : grade === "wrong" ? t("Graded wrong.")
  : grade === "critical" ? t("Graded critical.") : t("Graded {grade}.", { grade }));

// How it went, in the colour that means it: a person's yes or no, or the agent's own change
const outcomes = (): Record<string, [string, string]> => ({ approve: [t("approved"), "good"], reject: [t("rejected"), "bad"] });

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
  const [outcome, tone] = asked ? (outcomes()[sample.decided ?? ""] ?? [sample.decided ?? "", "idle"])
    : [t("made at level 2"), "changes"];
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
            <span className="who-name">{asked ? t("The {agent} asked", { agent: sample.agent })
              : t("The {agent} acted on its own", { agent: sample.agent })}</span>
            <span className="who-about">{t("{action} in {part} · sampled {day}",
              { action: sample.action, part: sample.part, day: day(sample.drawn_at) })}</span>
          </span>
        </div>
        <h2 className="approval-title" id={`title-${sample.id}`}>{what}</h2>
        {rest.length > 0 && <p className="said">{rest.join("\n")}</p>}
        {sample.asked && (
          <div className="approval-know">
            <p className="label">{t("What they asked")}</p>
            <p className="said">{sample.asked}</p>
          </div>
        )}
        <p><span className={`badge ${tone}`}>{outcome}</span></p>
        {sample.flags.length > 0 && (
          <div className="approval-know">
            <p className="label">{t("What code flagged")}</p>
            <ul>{sample.flags.map((flag) => <li key={flag}>{flag}</li>)}</ul>
          </div>
        )}
        {links.map(({ key, link }) => (
          <p key={key}><a href={link} rel="noopener noreferrer" target="_blank">{t("Open {record}", { record: key })}</a></p>
        ))}
        <div className="grades" role="group" aria-label={t("Your grade for: {what}", { what })}>
          {GRADES.map((grade) => (
            <button key={grade} type="button" className={grade} aria-pressed={chosen === grade}
                    onClick={() => choose(chosen === grade ? undefined : grade)}>
              {named(grade)}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

export function GradePage() {
  const toast = useToast();
  const [status, setStatus] = useState<string>();
  // the grades chosen, kept in the tab until they're sent, so signing in again gives them back
  const [chosen, setChosen] = useState<Map<number, Grade>>(() => new Map(unkept<[number, Grade][]>(CHOSEN) ?? []));
  const [acted, setActed] = useState(false);  // back from signing in to grade: sent first
  useEffect(() => {
    const act = takeAct();
    if (act?.kind !== "grade") {
      setActed(true);
      return;
    }
    send<Graded>("POST", "/grade/samples", { grades: act.grades, salt: act.salt })
      .then((made) => {
        keptNow(CHOSEN);
        setChosen(new Map());
        const given = Object.values(made.grades);
        const said = given.length === 1 ? graded(given[0]) : t("Graded {samples}.", { samples: plural(given.length, "sample") });
        setStatus(said);
        toast(said);
      })
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setActed(true));
  }, []);
  const now = useLoad(() => (acted ? send<GradeNow>("POST", "/grade/review") : new Promise<GradeNow>(() => {})),
                      [acted]);
  // A grade chosen for a sample no longer offered, which lapsed or someone else graded, goes,
  // or every grade sent with it would be refused for it, with no card left to take it back by
  useEffect(() => {
    if (!now.data) return;
    const offered = new Set(now.data.samples.map((sample) => sample.id));
    const gone = [...chosen.keys()].filter((id) => !offered.has(id));
    if (!gone.length) return;
    const next = new Map([...chosen].filter(([id]) => offered.has(id)));
    setChosen(next);
    if (next.size) keepUnkept(CHOSEN, [...next.entries()]);
    else keptNow(CHOSEN);
    setStatus(gone.length === 1
      ? t("A sample you chose no longer waits for a grade: it lapsed, or someone else graded it, so it's out of your grades.")
      : t("{samples} you chose no longer wait for a grade: they lapsed, or someone else graded them, so they're out of your grades.",
          { samples: plural(gone.length, "sample") }));
  }, [now.data]);

  const choose = (sample: number, grade: Grade | undefined) => {
    const next = new Map(chosen);
    if (grade) next.set(sample, grade);
    else next.delete(sample);
    setChosen(next);
    if (next.size) keepUnkept(CHOSEN, [...next.entries()]);
    else keptNow(CHOSEN);
    setStatus(next.size ? t("{n} chosen: send them when you're ready.", { n: next.size }) : "");
  };

  const sendThem = async () => {
    try {
      // a nonce that commits to exactly these grades of exactly these samples, as
      // core/samples.py's `nonce` makes it
      const grades = [...chosen.entries()].sort((a, b) => a[0] - b[0]);
      if (!grades.length) {
        setStatus(t("Choose a grade for a sample first."));
        return;
      }
      const salt = salted();
      const nonce = await hashed(`a5s grades samples ${grades.map(([s, g]) => `${s}:${g}`).join(",")} ${salt}`);
      setStatus(grades.length === 1 ? t("Signing you in again, to give this grade alone…")
        : t("Signing you in again, to give these grades alone…"));
      await signInFor({ kind: "grade", grades: Object.fromEntries(grades.map(([s, g]) => [String(s), g])), salt }, nonce);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const found = now.data;
  const samples = found?.samples ?? [];
  const none = found && samples.length === 0
    ? (status ? t("Nothing else waits for you to grade.") : t("Nothing waits for you to grade.")) : "";
  return (
    <>
      <PageHead title={t("Agents' work to grade")}
                about={t("Each is a change an agent asked for or made. Grade it right if it's what a careful colleague would have done with what they knew, wrong if not, and critical if it could have done real harm. Your grades decide whether agents may act on their own.")} />
      <p id="status" role="status" className="note">{[status, none].filter(Boolean).join(" ")}</p>
      {!found && <Waiting error={now.error} />}
      {samples.length > 0 && (
        <section id="waiting" className="bare">
          <div id="list">{samples.map((sample) => (
            <Card key={sample.id} sample={sample} chosen={chosen.get(sample.id)}
                  choose={(grade) => choose(sample.id, grade)} />
          ))}</div>
          <div className="send-bar">
            <button id="send" className="primary" type="button" onClick={sendThem}>{t("Send the grades you chose")}</button>
            <p className="note">{t("You sign in again to send them, so your sign-in covers exactly these grades.")}</p>
          </div>
        </section>
      )}
    </>
  );
}
