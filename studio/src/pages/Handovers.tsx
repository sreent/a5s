// Conversations handed over to people (core/handover.py): for those in a team an instance may
// hand one to, such as the service desk, each conversation handed to their team, its brief, and
// what the person said, their own words alone; taking one, answering the person, whom the core
// tells in their chat, as the agent's bot, with the answerer's name, and handing it back, so the
// agent answers again. A record's key they may not see reads as such.

import { useState } from "react";
import { get, send } from "../api";
import type * as gen from "../api.gen";
import { Badge, Confirm, useToast } from "../design";
import { t } from "../i18n";
import { Link } from "../router";
import { PageHead, plural, useLoad, Waiting, when } from "../ui";

export function HandoversPage() {
  const { data, error } = useLoad(() => get<gen.Handovers>("/studio/api/handovers"), []);
  return (
    <>
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }]} title={t("Handed over")} about={t("Conversations an agent handed to one of your teams, at the person's word. You read its brief and what the person said, their own words alone, not the agent's answers. Take one, and answer them here: a5s puts your answer in their chat, with your name, and the agent answers again once it's handed back.")} />
      {!data && <Waiting error={error} />}
      {data && data.handovers.length === 0 && <p className="note">{t("Nothing's handed to your teams now.")}</p>}
      {data && data.handovers.length > 0 && (
        <ul className="plain card" id="handovers">
          {data.handovers.map((h) => (
            <li key={h.id}>
              <Link to={{ page: "handover", id: String(h.id) }}><strong>{t("{person}, with the {agent}", { person: h.person, agent: h.agent })}</strong></Link>{" "}
              {h.taken_by ? <Badge tone={h.mine ? "good" : "idle"}>{h.mine ? t("Yours") : t("Taken by {person}", { person: h.taken_by })}</Badge>
                : <Badge tone="warn" dot>{t("Waits for one of you")}</Badge>}
              {h.unanswered > 0 && <Badge tone="warn">{t("{n} to answer", { n: plural(h.unanswered, "message") })}</Badge>}
              <p className="note">{t("For the {team} team, {when}", { team: h.team, when: when(h.started_at) })}</p>
              <p>{h.brief}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function HandoverPage({ id }: { id: string }) {
  const toast = useToast();
  const [again, setAgain] = useState(0);
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string>();
  const { data, error } = useLoad(() => get<gen.Handover>(`/studio/api/handovers/${encodeURIComponent(id)}`), [id, again]);
  const act = (what: "take" | "answer" | "back", body?: unknown, said?: string) => {
    setProblem(undefined);
    send<gen.HandoverDone>("POST", `/studio/api/handovers/${encodeURIComponent(id)}/${what}`, body)
      .then(() => {
        if (said) toast(said);
        if (what === "answer") setText("");
        setAgain((n) => n + 1);
      })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <>
      <PageHead crumbs={[{ label: t("Home"), to: { page: "home" } }, { label: t("Handed over"), to: { page: "handovers" } }]}
                title={data ? t("{person}, with the {agent}", { person: data.person, agent: data.agent }) : t("A conversation handed over")} />
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card" id="brief" aria-labelledby="brief-title">
            <h2 id="brief-title">{t("What the {agent} says they need", { agent: data.agent })}</h2>
            <p>{data.brief}</p>
            <p className="note">{t("Handed to the {team} team, {when}", { team: data.team, when: when(data.started_at) })}
              {data.taken_by && <>{"; "}{data.mine ? t("you've taken it") : t("taken by {person}", { person: data.taken_by })}</>}</p>
          </section>
          <section className="card" id="said" aria-labelledby="said-title">
            <h2 id="said-title">{t("What they said")}</h2>
            <ol className="try-turns">
              {data.said.map((s, i) => <li key={`b${i}`} className="try-said"><span className="note">{when(s.at)}</span><p>{s.text}</p></li>)}
              {data.since.map((s, i) => (
                <li key={`s${i}`} className="try-said"><span className="note">{when(s.at)}</span>{!s.answered && <> <Badge tone="warn">{t("to answer")}</Badge></>}<p>{s.text}</p></li>
              ))}
              {data.answers.map((a, i) => (
                <li key={`a${i}`} className="try-answer"><span className="note">{when(a.at)}, {a.by}</span>{!a.sent && <> <Badge tone="idle">{t("on its way")}</Badge></>}<p className="try-reply">{a.text}</p></li>
              ))}
            </ol>
          </section>
          {!data.ended && (
            <section className="card" id="answer" aria-labelledby="answer-title">
              <h2 id="answer-title">{t("Answer them")}</h2>
              {problem && <p className="problem" role="alert">{problem}</p>}
              {!data.mine && !data.taken_by && (
                <button type="button" className="primary" onClick={() => act("take", undefined, t("It's yours: answer them here."))}>
                  {t("Take it")}
                </button>
              )}
              {data.mine && (
                <>
                  <label className="field"><span>{t("Your answer, in their chat, with your name")}</span>
                    <textarea id="answer-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} />
                  </label>
                  <div className="actions">
                    <button type="button" className="primary" disabled={!text.trim()}
                            onClick={() => act("answer", { text }, t("a5s puts it in their chat within a minute."))}>{t("Send")}</button>
                    <Confirm label={t("Hand it back to the {agent}", { agent: data.agent })}
                             title={t("Hand it back to the {agent}?", { agent: data.agent })}
                             about={t("The {agent} answers them again from here, and reads what you said to them.", { agent: data.agent })}
                             confirm={t("Hand it back")} onConfirm={() => act("back", undefined, t("Handed back: the {agent} answers them again.", { agent: data.agent }))} />
                  </div>
                </>
              )}
            </section>
          )}
          {data.ended && <p className="note" role="status">{t("It's been handed back to the {agent}.", { agent: data.agent })}</p>}
        </>
      )}
    </>
  );
}
