// Shadows' answers, for graders (core/shadows.py): a new version of an agent answers what
// people ask an instance, beside it, sending and changing nothing. A grader from outside the team
// that built it reads what was asked, the answer sent and the new version's, never whose they
// were, and says whether the new version's is better, as good, worse, or wrong. How each shadow
// did, in counts, is for its graders and its owners, beside its judge's verdicts, kept apart.

import { useState } from "react";
import { get, send } from "../api";
import type * as gen from "../api.gen";
import { Badge, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, plural, StatusBadge, useLoad, Waiting, when } from "../ui";

type Grade = "better" | "same" | "worse" | "wrong";
const GRADES: Grade[] = ["better", "same", "worse", "wrong"];

/** A grade's name on its button, in the language spoken: what's sent is the grade itself. */
const named = (grade: Grade) => (grade === "better" ? t("Better") : grade === "same" ? t("As good")
  : grade === "worse" ? t("Worse") : t("Wrong"));

function Pair({ pair, graded }: { pair: gen.ShadowPair; graded: () => void }) {
  const toast = useToast();
  const [problem, setProblem] = useState<string>();
  const grade = (given: Grade) => {
    setProblem(undefined);
    send<gen.ShadowGraded>("POST", `/studio/api/shadows/${pair.id}/grade`, { grade: given })
      .then(() => { toast(t("Graded: thank you.")); graded(); })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <section className="card" data-pair={pair.id} aria-labelledby={`pair-${pair.id}`}>
      <h2 id={`pair-${pair.id}`}>{t("The {agent}, and the {shadow} beside it", { agent: pair.agent, shadow: pair.shadow })}</h2>
      <p className="note">{when(pair.at)}</p>
      <ol className="try-turns">
        <li className="try-said"><span className="note">{t("What they said")}</span><p>{pair.asked}</p></li>
        <li className="try-answer"><span className="note">{t("The answer sent")}</span><p className="try-reply">{pair.sent}</p></li>
        <li className="try-answer"><span className="note">{t("The new version's answer, which went nowhere")}</span><p className="try-reply">{pair.answer}</p></li>
      </ol>
      {problem && <p className="problem" role="alert">{problem}</p>}
      <div className="actions" role="group" aria-label={t("Grade the new version's answer")}>
        {GRADES.map((g) => (
          <button key={g} type="button" className={g === "wrong" ? "danger" : g === "better" ? "primary" : ""}
                  onClick={() => grade(g)}>{named(g)}</button>
        ))}
      </div>
    </section>
  );
}

function Figures({ shadows }: { shadows: gen.ShadowFigures[] }) {
  return (
    <section className="card" id="figures" aria-labelledby="figures-title">
      <h2 id="figures-title">{t("How each new version does")}</h2>
      <p className="note">{t("Counts of graders' grades, and its judge's apart, never what was said.")}</p>
      <ul className="plain">
        {shadows.map((s) => (
          <li key={s.instance} data-shadow={s.instance}>
            <strong>{s.instance}</strong>{" "}
            {s.status === "shadow" ? <Badge tone="good" dot>{t("Answering beside {instance}", { instance: s.shadows })}</Badge>
              : <StatusBadge status={s.status} />}
            <p className="note">{t("{n} so far", { n: plural(s.answered, "answer") })}</p>
            <p>{t("Graded: {better} better, {same} as good, {worse} worse, {wrong} wrong", s.graded)}</p>
            <p className="note">{t("Its judge: {better} better, {same} as good, {worse} worse, {wrong} wrong", s.judged)}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ShadowsPage() {
  const [again, setAgain] = useState(0);
  const { data, error } = useLoad(() => get<gen.Shadows>("/studio/api/shadows"), [again]);
  return (
    <>
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }]} title={t("New versions, answering beside")}
                about={t("A new version of an agent answers what people ask an instance, beside it, sending and changing nothing. Compare its answer with the one sent, never knowing whose it was, and say which is better: its owners decide from your grades whether to put it to work.")} />
      {!data && <Waiting error={error} />}
      {data && data.pairs.length === 0 && <p className="note" id="nothing">{t("Nothing waits for you to compare now.")}</p>}
      {data && data.pairs.length > 0 && (
        <div id="pairs">{data.pairs.map((p) => <Pair key={p.id} pair={p} graded={() => setAgain((n) => n + 1)} />)}</div>
      )}
      {data && data.shadows.length > 0 && <Figures shadows={data.shadows} />}
    </>
  );
}
