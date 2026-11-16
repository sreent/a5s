// Answers people said were wrong (core/feedback.py), for the agent's owners to check, on its page:
// each on the card decisions are made on, with why, in the words of whoever said so, and the run
// behind it, and right, wrong or critical, which grades it at once, and can be changed. Only the
// agent's owners are given them, and of those, only answers whose runs they may see.

import { ApiError, get, send } from "./api";
import type * as gen from "./api.gen";
import { useToast } from "./design";
import { t } from "./i18n";
import { Icon } from "./icons";
import { Link } from "./router";
import { plural, sentence, useLoad, when } from "./ui";

const GRADES = ["right", "wrong", "critical"] as const;
// Each grade in words, and how many were given it, in the language spoken whenever they're read
const GRADED: Record<string, string> = {
  get right() { return t("right"); }, get wrong() { return t("wrong"); }, get critical() { return t("critical"); },
};
const COUNTED: Record<(typeof GRADES)[number], (n: number) => string> = {
  right: (n) => t("{n} right", { n }), wrong: (n) => t("{n} wrong", { n }), critical: (n) => t("{n} critical", { n }),
};
const CHATS: Record<string, string> = { get local() { return t("the web chat"); }, teams: "Teams", slack: "Slack", matrix: "Matrix" };

function Answer({ answer, grade }: { answer: gen.SaidWrong; grade: (answer: gen.SaidWrong, given: string) => void }) {
  const title = `title-said-wrong-${answer.id}`;
  return (
    <section className="approval sample" data-said-wrong={answer.id} aria-labelledby={title}>
      <div className="approval-stripe" />
      <div className="approval-body">
        <div className="who">
          <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
          <span>
            <span className="who-name">{answer.by ? t("{person} said this was wrong", { person: answer.by }) : t("Someone it served said this was wrong")}</span>
            <span className="who-about">{`${t("in {chat}, {when}", { chat: CHATS[answer.channel] ?? answer.channel, when: when(answer.at) })}${answer.instance ? ` · ${answer.instance}` : ""}`}</span>
          </span>
        </div>
        <h3 className="approval-title" id={title}>{t("Its answer")}</h3>
        <p className="said">{answer.answer}</p>
        {answer.said && (
          <div className="approval-know">
            <p className="label">{t("Why, in their words")}</p>
            <p>{answer.said}</p>
          </div>
        )}
        <p><Link to={{ page: "run", run: answer.run }}>{t("The run behind it")}</Link></p>
        <div className="grades" role="group" aria-label={t("Your grade for its answer")}>
          {GRADES.map((given) => (
            <button key={given} type="button" className={given} aria-pressed={answer.grade === given}
                    onClick={() => grade(answer, given)}>
              {sentence(GRADED[given])}
            </button>
          ))}
        </div>
        {answer.grade && answer.graded_by && answer.graded_at && (
          <p className="note">{t("Graded {grade} by {person}, {when}.", { grade: GRADED[answer.grade] ?? answer.grade, person: answer.graded_by, when: when(answer.graded_at) })}</p>
        )}
      </div>
    </section>
  );
}

/** How many of them wait for the owner to check, and how those checked were graded. */
function waits(waiting: number, graded: string[]): string {
  const answers = plural(waiting, "answer");
  if (graded.length) {
    return waiting === 1 ? t("{answers} waits for you to check; graded: {graded}.", { answers, graded: graded.join(", ") })
      : t("{answers} wait for you to check; graded: {graded}.", { answers, graded: graded.join(", ") });
  }
  return waiting === 1 ? t("{answers} waits for you to check.", { answers }) : t("{answers} wait for you to check.", { answers });
}

export function SaidWrong({ agent }: { agent: string }) {
  const toast = useToast();
  const path = `/studio/api/agents/${encodeURIComponent(agent)}/feedback`;
  const { data, reload } = useLoad<gen.AnswersSaidWrong | null>(() => get<gen.AnswersSaidWrong>(path).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;  // not theirs to check
    throw e;
  }), [agent]);
  if (!data) return null;
  const grade = (answer: gen.SaidWrong, given: string) => {
    send<gen.AnswerGraded>("POST", `/studio/api/feedback/${answer.id}/grade`, { grade: given })
      .then(() => reload())
      .then(() => toast(t("Graded its answer {grade}.", { grade: GRADED[given] ?? given })))
      .catch((e: Error) => toast(e.message));
  };
  const graded = GRADES.filter((g) => data.graded[g]).map((g) => COUNTED[g](data.graded[g]));
  return (
    <section className="card" id="feedback" aria-labelledby="feedback-title">
      <h2 id="feedback-title">{t("Answers people said were wrong")}</h2>
      <p className="note" id="feedback-status">
        {data.answers.length === 0 && !data.hidden
          ? t("Nobody has said any of its answers was wrong. People say so with a 👎 in Slack or Matrix, Teams' buttons on an answer, or the web chat's.")
          : waits(data.waiting, graded)}
      </p>
      {data.answers.map((answer) => <Answer key={answer.id} answer={answer} grade={grade} />)}
      {data.hidden > 0 && (
        <p className="note">{t("And {more} from runs you may not see, which someone who may see their records can check.", { more: plural(data.hidden, "more") })}</p>
      )}
    </section>
  );
}
