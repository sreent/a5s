// Keeping a run as one of its agent's test cases (core/run_cases.py), on the run's page, for those
// who author the agent, once the data protection officer agrees: what was said to it, masked by
// code, which its author reads and puts right, whom it's said as, one of the sandbox's made-up
// people, what a right answer is, in their words, and that it says nothing about anyone. It goes
// in their draft of the agent, which it opens.

import { type FormEvent, useState } from "react";
import { ApiError, get, send } from "./api";
import type * as gen from "./api.gen";
import { useToast } from "./design";
import { Link } from "./router";
import { useLoad } from "./ui";

const KINDS: Record<string, [string, string]> = {
  names: ["name", "names"], emails: ["email", "emails"], links: ["link", "links"], numbers: ["number", "numbers"],
};

function masked(counts: Record<string, number>): string {
  const said = Object.entries(counts).map(([kind, n]) => `${n} ${(KINDS[kind] ?? [kind, kind])[n === 1 ? 0 : 1]}`);
  return said.length ? `Code masked ${said.join(", ")}.` : "Code found nothing to mask.";
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
  const [name, setName] = useState(`From run ${run.slice(0, 8)}`);
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
        <h2>Keep it as a test case</h2>
        <p className="note">{found.refused[0].toUpperCase() + found.refused.slice(1)}.</p>
      </section>
    );
  }
  const keep = (event: FormEvent) => {
    event.preventDefault();
    setProblem(undefined);
    send<gen.RunCaseKept>("POST", `/studio/api/runs/${encodeURIComponent(run)}/case`,
                          { name, speaker, say: say ?? found.say, judged: judged || null, checked })
      .then((made) => { setKept(made); toast(`Kept it as ${made.case.name} in your draft of the ${found.agent}.`); })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <section className="card" id="keep-case">
      <h2>Keep it as a test case</h2>
      <p className="note">So drafts of the {found.agent} are judged against real work. {masked(found.masked)} Code can't know every name someone might write: read what's left, and put the sandbox's made-up records in place of the real ones it names.</p>
      {kept ? (
        <p role="status">Kept as {kept.case.name}, in {kept.file} of <Link to={{ page: "draft", draft: kept.draft }}>your draft of the {found.agent}</Link>.</p>
      ) : (
        <form className="form" onSubmit={keep}>
          <label className="field"><span>What was said to it, as you'll keep it</span>
            <textarea id="case-say" rows={4} value={say ?? found.say} onChange={(e) => setSay(e.target.value)} required /></label>
          <details>
            <summary>What it answered, masked</summary>
            <p className="said">{found.answer || "(nothing)"}</p>
            {found.uses.length > 0 && <p className="note">It used {found.uses.join(", ")}, which the case will say it must use.</p>}
          </details>
          <label className="field"><span>The case's name</span>
            <input id="case-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} /></label>
          <label className="field"><span>Said as, one of the sandbox's made-up people</span>
            {people.data?.people.length ? (
              <select id="case-speaker" value={speaker} onChange={(e) => setSpeaker(e.target.value)} required>
                <option value="">Choose someone</option>
                {people.data.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : <input id="case-speaker" value={speaker} onChange={(e) => setSpeaker(e.target.value)} required />}
          </label>
          <label className="field"><span>What a right answer is, in your words, if you'd have its judge grade it</span>
            <textarea id="case-judged" rows={2} value={judged} onChange={(e) => setJudged(e.target.value)} /></label>
          <label className="check"><input type="checkbox" id="case-checked" checked={checked}
                                           onChange={(e) => setChecked(e.target.checked)} required />
            I've read it, and it says nothing about anyone</label>
          {problem && <p className="problem" role="alert">{problem}</p>}
          <button type="submit" className="primary" id="keep-case-button">Keep it in my draft</button>
        </form>
      )}
    </section>
  );
}
