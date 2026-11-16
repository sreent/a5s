// Answers people said were wrong (core/feedback.py), for the agent's owners to check, on its page:
// each on the card decisions are made on, with why, in the words of whoever said so, and the run
// behind it, and right, wrong or critical, which grades it at once, and can be changed. Only the
// agent's owners are given them, and of those, only answers whose runs they may see.

import { ApiError, get, send } from "./api";
import type * as gen from "./api.gen";
import { useToast } from "./design";
import { Icon } from "./icons";
import { Link } from "./router";
import { plural, useLoad, when } from "./ui";

const GRADES = ["right", "wrong", "critical"] as const;
const CHATS: Record<string, string> = { local: "the web chat", teams: "Teams", slack: "Slack", matrix: "Matrix" };

function Answer({ answer, grade }: { answer: gen.SaidWrong; grade: (answer: gen.SaidWrong, given: string) => void }) {
  const title = `title-said-wrong-${answer.id}`;
  return (
    <section className="approval sample" data-said-wrong={answer.id} aria-labelledby={title}>
      <div className="approval-stripe" />
      <div className="approval-body">
        <div className="who">
          <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
          <span>
            <span className="who-name">{answer.by ? `${answer.by} said this was wrong` : "Someone it served said this was wrong"}</span>
            <span className="who-about">{`in ${CHATS[answer.channel] ?? answer.channel}, ${when(answer.at)}${answer.instance ? ` · ${answer.instance}` : ""}`}</span>
          </span>
        </div>
        <h3 className="approval-title" id={title}>Its answer</h3>
        <p className="said">{answer.answer}</p>
        {answer.said && (
          <div className="approval-know">
            <p className="label">Why, in their words</p>
            <p>{answer.said}</p>
          </div>
        )}
        <p><Link to={{ page: "run", run: answer.run }}>The run behind it</Link></p>
        <div className="grades" role="group" aria-label="Your grade for its answer">
          {GRADES.map((given) => (
            <button key={given} type="button" className={given} aria-pressed={answer.grade === given}
                    onClick={() => grade(answer, given)}>
              {given[0].toUpperCase() + given.slice(1)}
            </button>
          ))}
        </div>
        {answer.grade && answer.graded_by && answer.graded_at && (
          <p className="note">Graded {answer.grade} by {answer.graded_by}, {when(answer.graded_at)}.</p>
        )}
      </div>
    </section>
  );
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
      .then(() => toast(`Graded its answer ${given}.`))
      .catch((e: Error) => toast(e.message));
  };
  const graded = GRADES.filter((g) => data.graded[g]).map((g) => `${data.graded[g]} ${g}`);
  return (
    <section className="card" id="feedback" aria-labelledby="feedback-title">
      <h2 id="feedback-title">Answers people said were wrong</h2>
      <p className="note" id="feedback-status">
        {data.answers.length === 0 && !data.hidden
          ? "Nobody has said any of its answers was wrong. People say so with a 👎 in Slack or Matrix, Teams' buttons on an answer, or the web chat's."
          : `${plural(data.waiting, "answer")} ${data.waiting === 1 ? "waits" : "wait"} for you to check${graded.length ? `; graded: ${graded.join(", ")}` : ""}.`}
      </p>
      {data.answers.map((answer) => <Answer key={answer.id} answer={answer} grade={grade} />)}
      {data.hidden > 0 && (
        <p className="note">And {plural(data.hidden, "more")} from runs you may not see, which someone who may see their records can check.</p>
      )}
    </section>
  );
}
