// Publishing a draft: a pull request to the agents' repository, opened as its author, once they
// let a5s's GitHub App act as them at GitHub's own sign-in. a5s holds no token for it: the
// channels app uses the one GitHub gives for that publish alone. Or its folder, to download.

import { useEffect, useState } from "react";
import { download, get, send } from "./api";

type Publishing = {
  id: string;
  status: "signing in" | "opened" | "refused" | "lapsed";
  user_code: string | null;
  verify_at: string | null;
  interval: number;
  expires_in: number;
  pull: string | null;
  problem: string | null;
};

export function Publish({ draft, name, ready, published }: {
  draft: string; name: string; ready: boolean; published: string | null;
}) {
  const [now, setNow] = useState<Publishing | null>(null);
  const [pull, setPull] = useState(published);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {  // ask after it as often as GitHub lets a5s ask, until it's done
    if (!now || now.status !== "signing in") return;
    const timer = window.setTimeout(async () => {
      try {
        const found = await get<Publishing>(`/studio/api/publishes/${encodeURIComponent(now.id)}`);
        setNow(found);
        if (found.pull) setPull(found.pull);
      } catch (e) {
        setProblem((e as Error).message);
      }
    }, Math.max(1, now.interval) * 1000);
    return () => window.clearTimeout(timer);
  }, [now]);
  const start = async () => {
    setProblem(null);
    try {
      setNow(await send<Publishing>("POST", `/studio/api/drafts/${encodeURIComponent(draft)}/publish`));
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  const save = async () => {
    try {
      await download(`/studio/api/drafts/${encodeURIComponent(draft)}/folder`, `${name}.zip`);
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  const waiting = now?.status === "signing in";
  return (
    <div className="publish">
      {pull && (
        <p id="published"><span className="badge good">published</span> As <a href={pull} target="_blank" rel="noopener noreferrer">its pull request</a>.
          CI runs its checks and test cases there, and the people above sign its release. Publishing it again adds a commit to it.</p>
      )}
      {!pull && !waiting && (
        <p className="note">A pull request to the agents' repository, opened as you: a5s asks GitHub to let it act as you, for this alone, and keeps no token of yours.</p>
      )}
      {waiting && now && (
        <div className="sign-in-code">
          <p>Let a5s publish it as you: at <a href={now.verify_at ?? "#"} target="_blank" rel="noopener noreferrer">GitHub's sign-in</a>, enter</p>
          <p className="user-code mono" id="user-code">{now.user_code}</p>
          <p className="note">a5s waits for GitHub for {Math.max(1, Math.round(now.expires_in / 60))} minutes at most.</p>
        </div>
      )}
      {now && (now.status === "refused" || now.status === "lapsed") && <p className="problem">{now.problem}</p>}
      {problem && <p className="problem">{problem}</p>}
      <div className="meta">
        <button type="button" className="primary" id="publish" disabled={!ready || waiting} onClick={start}>
          {waiting ? "Waiting for GitHub…" : pull ? "Publish again" : "Publish as a pull request"}</button>
        <button type="button" className="quiet" id="download" onClick={save}>Download its folder</button>
      </div>
    </div>
  );
}
