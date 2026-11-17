// Keeping a run as one of its agent's test cases (core/run_cases.py), on the run's page, for those
// who author the agent, once the data protection officer agrees: what was said to it, masked by
// code, which its author reads and puts right, whom it's said as, one of the sandbox's made-up
// people, what a right answer is, in their words, and that it says nothing about anyone. It goes
// in their draft of the agent, which it opens.

import { type FormEvent, useState } from "react";
import { ApiError, get, send } from "./api";
import type * as gen from "./api.gen";
import { useToast } from "./design";
import { t } from "./i18n";
import { Link } from "./router";
import { useLoad } from "./ui";

// How many of each kind code masked, in words: one of them, and many
const KINDS: Record<string, [(n: number) => string, (n: number) => string]> = {
  names: [(n) => t("{n} name", { n }), (n) => t("{n} names", { n })],
  emails: [(n) => t("{n} email", { n }), (n) => t("{n} emails", { n })],
  links: [(n) => t("{n} link", { n }), (n) => t("{n} links", { n })],
  numbers: [(n) => t("{n} number", { n }), (n) => t("{n} numbers", { n })],
  records: [(n) => t("{n} record's key", { n }), (n) => t("{n} records' keys", { n })],
};

function masked(counts: Record<string, number>): string {
  const said = Object.entries(counts).map(([kind, n]) => KINDS[kind]?.[n === 1 ? 0 : 1](n) ?? `${n} ${kind}`);
  return said.length ? t("Code masked {masked}.", { masked: said.join(", ") }) : t("Code found nothing to mask.");
}

type Offer = gen.RunCaseOffered | { refused: string } | null;

export function KeepAsCase({ run }: { run: string }) {
  const toast = useToast();
  const offer = useLoad<Offer>(() => get<gen.RunCaseOffered>(`/studio/api/runs/${encodeURIComponent(run)}/case`)
    .catch((e) => {
      if (e instanceof ApiError && e.status === 403 && /officer|message|no longer/.test(e.message)) return { refused: e.message };
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) return null;  // not theirs to keep
      throw e;
    }), [run]);
  const people = useLoad(() => get<gen.Sandbox>("/studio/api/sandbox").catch(() => null), []);
  const [name, setName] = useState(t("From run {run}", { run: run.slice(0, 8) }));
  const [speaker, setSpeaker] = useState("");
  const [say, setSay] = useState<string>();
  const [judged, setJudged] = useState("");
  const [checked, setChecked] = useState(false);
  const [kept, setKept] = useState<gen.RunCaseKept>();
  const [problem, setProblem] = useState<string>();
  const found = offer.data;
  if (!found) return null;
  if ("refused" in found) {
    return (
      <section className="card" id="keep-case">
        <h2>{t("Keep it as a test case")}</h2>
        <p className="note">{found.refused[0].toUpperCase() + found.refused.slice(1)}.</p>
      </section>
    );
  }
  const keep = (event: FormEvent) => {
    event.preventDefault();
    setProblem(undefined);
    send<gen.RunCaseKept>("POST", `/studio/api/runs/${encodeURIComponent(run)}/case`,
                          { name, speaker, say: say ?? found.say, judged: judged || null, checked })
      .then((made) => { setKept(made); toast(t("Kept it as {name} in your draft of the {agent}.", { name: made.case.name, agent: found.agent })); })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <section className="card" id="keep-case">
      <h2>{t("Keep it as a test case")}</h2>
      <p className="note">{t("So drafts of the {agent} are judged against real work. {masked} Code can't know every name someone might write: read what's left, and put the sandbox's made-up records where it says [record 1] and so on.",
        { agent: found.agent, masked: masked(found.masked) })}</p>
      {found.read_outside && <p className="note" id="case-outside">{t("Its run read content from outside, which the case can't keep: the sandbox and the suite send each step with a file in its place, which marks its run as the real one was.")}</p>}
      {kept ? (
        <p role="status">{t("Kept as {name}, in {file} of", { name: kept.case.name, file: kept.file })} <Link to={{ page: "draft", draft: kept.draft }}>{t("your draft of the {agent}", { agent: found.agent })}</Link>.</p>
      ) : (
        <form className="form" onSubmit={keep}>
          <label className="field"><span>{t("What was said to it, as you'll keep it")}</span>
            <textarea id="case-say" rows={4} value={say ?? found.say} onChange={(e) => setSay(e.target.value)} required /></label>
          <details>
            <summary>{t("What it answered, masked")}</summary>
            <p className="said">{found.answer || t("(nothing)")}</p>
            {found.uses.length > 0 && <p className="note">{t("It used {tools}, which the case will say it must use.", { tools: found.uses.join(", ") })}</p>}
          </details>
          <label className="field"><span>{t("The case's name")}</span>
            <input id="case-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} /></label>
          <label className="field"><span>{t("Said as, one of the sandbox's made-up people")}</span>
            {people.data?.people.length ? (
              <select id="case-speaker" value={speaker} onChange={(e) => setSpeaker(e.target.value)} required>
                <option value="">{t("Choose someone")}</option>
                {people.data.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : <input id="case-speaker" value={speaker} onChange={(e) => setSpeaker(e.target.value)} required />}
          </label>
          <label className="field"><span>{t("What a right answer is, in your words, if you'd have its judge grade it")}</span>
            <textarea id="case-judged" rows={2} value={judged} onChange={(e) => setJudged(e.target.value)} /></label>
          <label className="check"><input type="checkbox" id="case-checked" checked={checked}
                                           onChange={(e) => setChecked(e.target.checked)} required />
            {t("I've read it, and it says nothing about anyone")}</label>
          {problem && <p className="problem" role="alert">{problem}</p>}
          <button type="submit" className="primary" id="keep-case-button">{t("Keep it in my draft")}</button>
        </form>
      )}
    </section>
  );
}
