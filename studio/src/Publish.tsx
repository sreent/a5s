// Publishing a draft: a pull request to the agents' repository. Its author opens it, on any git
// host, with its folder and the pull request's words, which say who must sign its release; or,
// where a5s's GitHub App is set up, a5s opens it on GitHub as them, once they let it at GitHub's
// own sign-in. a5s holds no token for it: the channels app uses the one GitHub gives for that
// publish alone.

import { useEffect, useState } from "react";
import { download, get, send } from "./api";
import { useLoad } from "./ui";

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

type PullRequest = { folder: string; title: string; body: string; ready: boolean };

/** Where publishing isn't set up: its folder, where it goes, and the pull request's words, for
 * its author to open it with themselves, on whichever git host the agents' repository is on. */
function ByHand({ draft, name, revision }: { draft: string; name: string; revision: number }) {
  const pull = useLoad(() => get<PullRequest>(`/studio/api/drafts/${encodeURIComponent(draft)}/pull-request`),
                       [draft, revision]);
  const [said, setSaid] = useState<string | null>(null);
  const save = async () => {
    try {
      await download(`/studio/api/drafts/${encodeURIComponent(draft)}/folder`, `${name}.zip`);
    } catch (e) {
      setSaid((e as Error).message);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(pull.data?.body ?? "");
      setSaid("The description is copied.");
    } catch {
      setSaid("Select the description and copy it.");
    }
  };
  if (!pull.data) return <p className="note">{pull.error ?? "…"}</p>;
  return (
    <div className="publish">
      <p className="note">You open its pull request: download its folder, put it in the agents' repository as <span className="mono" id="pull-folder">{pull.data.folder}/</span> on a branch of your own, and open a pull request from it, titled as below, with this description, which tells its reviewers who must sign its release.</p>
      {!pull.data.ready && <p className="problem">Put right what would stop its release first: its description says what, as it stands.</p>}
      <label className="field"><span>Its title</span>
        <input id="pull-title" readOnly value={pull.data.title} /></label>
      <label className="field"><span>Its description</span>
        <textarea id="pull-body" readOnly rows={9} value={pull.data.body} /></label>
      {said && <p className="note">{said}</p>}
      <div className="meta">
        <button type="button" className="primary" id="download" onClick={save}>Download its folder</button>
        <button type="button" className="quiet" id="copy-body" onClick={copy}>Copy the description</button>
      </div>
    </div>
  );
}

export function Publish({ draft, name, ready, published, publishing, revision }: {
  draft: string; name: string; ready: boolean; published: string | null; publishing: boolean; revision: number;
}) {
  if (!publishing) return <ByHand draft={draft} name={name} revision={revision} />;
  return <OnGitHub draft={draft} name={name} ready={ready} published={published} />;
}

function OnGitHub({ draft, name, ready, published }: {
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
