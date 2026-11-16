// The studio: signed in once, through the organisation's identity provider, then each of its
// pages in turn, beside the sidebar every page of a5s has.

import { useEffect, useRef, useState } from "react";
import { onRunOut, runOut, runsOutAt, signedIn } from "./api";
import { signIn, signInAgain } from "./auth";
import { Toasts } from "./design/feedback";
import { language, onLanguage, t } from "./i18n";
import { Find } from "./Find";
import { AdminPage } from "./pages/Admin";
import { AgentPage } from "./pages/Agent";
import { AgentsPage } from "./pages/Agents";
import { ApprovePage } from "./pages/Approve";
import { AuditPage } from "./pages/Audit";
import { DecidePage } from "./pages/Decide";
import { DesignPage } from "./pages/Design";
import { DraftPage } from "./pages/Draft";
import { GradePage } from "./pages/Grade";
import { HomePage } from "./pages/Home";
import { InstancePage } from "./pages/Instance";
import { NewPage } from "./pages/New";
import { MapPage } from "./pages/Map";
import { NotebookPage } from "./pages/Notebook";
import { OfficerPage } from "./pages/Officer";
import { RunPage } from "./pages/Run";
import { SettingsPage } from "./pages/Settings";
import { SpendingPage } from "./pages/Spending";
import { TasksPage } from "./pages/Tasks";
import { YouPage } from "./pages/You";
import { reread, useRoute } from "./router";
import { Sidebar } from "./Sidebar";

type State = "signing-in" | "ready" | { problem: string };

/** Once the sign-in has run out, a5s can neither keep nor show anything more: the studio says
 * so over the page, and signs them in again, back to it, where what they'd changed and a5s
 * hadn't kept comes back (round 13, C1). */
function SignInAgain({ ready }: { ready: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [problem, setProblem] = useState<string>();
  useEffect(() => {
    if (!ready) return;
    const out = () => { if (!dialog.current?.open) dialog.current?.showModal(); };
    const stop = onRunOut(out);
    const at = runsOutAt();
    const timer = at ? window.setTimeout(out, Math.max(0, at - Date.now()) + 1000) : undefined;
    if (runOut()) out();
    return () => { stop(); window.clearTimeout(timer); };
  }, [ready]);
  return (
    <dialog ref={dialog} className="dialog" id="sign-in-again" aria-labelledby="sign-in-again-title"
            aria-describedby="sign-in-again-about">
      <h2 id="sign-in-again-title">{t("Sign in again to carry on")}</h2>
      <p id="sign-in-again-about">{t("Your sign-in has run out, so a5s can't keep or show anything more until you sign in again. You come back to this page, and what you've changed here that a5s hasn't kept yet comes back with you.")}</p>
      {problem && <p className="problem" role="alert">{problem}</p>}
      <div className="dialog-actions">
        <button type="button" className="primary" autoFocus
                onClick={() => signInAgain().catch((e: Error) => setProblem(e.message))}>{t("Sign in again")}</button>
      </div>
    </dialog>
  );
}

/** A sign-in that didn't work, such as one for an act cancelled at the identity provider: what
 * went wrong, that nothing was done, and the way back (round 13, C3). */
function SignInFailed({ problem }: { problem: string }) {
  const [again, setAgain] = useState<string>();
  return (
    <section className="card" id="sign-in-failed">
      <h1>{t("Signing in didn't work")}</h1>
      <p className="problem" role="alert">{problem}</p>
      <p>{t("Nothing was done with it. Sign in again to go back to where you were, and try again from there.")}</p>
      {again && <p className="problem" role="alert">{again}</p>}
      <button type="button" className="primary"
              onClick={() => signInAgain().catch((e: Error) => setAgain(e.message))}>{t("Sign in again")}</button>
    </section>
  );
}

export function App() {
  const [state, setState] = useState<State>("signing-in");
  const route = useRoute();
  const [spoken, setSpoken] = useState(language());  // its pages are drawn again in a new one
  useEffect(() => onLanguage(() => setSpoken(language())), []);
  useEffect(() => {
    signIn()
      .then((token) => {
        if (token) {  // else gone to the provider, which sends them back
          signedIn(token);
          setState("ready");
          reread();  // where they were going, which signing in has put back in the address
        }
      })
      .catch((error: Error) => setState({ problem: error.message }));
  }, []);
  let content;
  if (state === "signing-in") content = <p className="note" role="status">{t("Signing you in…")}</p>;
  else if (typeof state === "object") content = <SignInFailed problem={state.problem} />;
  else if (route.page === "agent") content = <AgentPage key={route.agent} id={route.agent} />;
  else if (route.page === "instance") content = <InstancePage key={route.instance} id={route.instance} />;
  else if (route.page === "run") content = <RunPage key={route.run} id={route.run} />;
  else if (route.page === "new") content = <NewPage />;
  else if (route.page === "draft") content = <DraftPage key={route.draft} id={route.draft} />;
  else if (route.page === "agents") content = <AgentsPage />;
  else if (route.page === "you") content = <YouPage />;
  else if (route.page === "design") content = <DesignPage />;
  else if (route.page === "settings") content = <SettingsPage />;
  else if (route.page === "notebook") content = <NotebookPage />;
  else if (route.page === "tasks") content = <TasksPage />;
  else if (route.page === "admin") content = <AdminPage />;
  else if (route.page === "audit") content = <AuditPage />;
  else if (route.page === "decide") content = <DecidePage />;
  else if (route.page === "grade") content = <GradePage />;
  else if (route.page === "officer") content = <OfficerPage />;
  else if (route.page === "map") content = <MapPage at={route.at} />;
  else if (route.page === "spending") content = <SpendingPage key={route.month ?? ""} month={route.month} />;
  else if (route.page === "approve") content = <ApprovePage key={route.settings} version={route.settings} />;
  else content = <HomePage />;
  const workbench = route.page === "draft" && state === "ready";  // a draft fills the window, as Ocean's workbench
  useEffect(() => {
    document.body.classList.toggle("workbench", workbench);
  }, [workbench]);
  const ready = state === "ready";
  if (workbench) {
    return (
      <Toasts>
        <Find key={spoken} ready={ready}>
          <div className="wb window">
            <Sidebar signedIn rail />
            <main className="wb-main">{content}</main>
          </div>
          <SignInAgain ready={ready} />
        </Find>
      </Toasts>
    );
  }
  return (
    <Toasts>
      <Find key={spoken} ready={ready}>
        <Sidebar signedIn={ready} />
        <div className="page studio">
          <main>{content}</main>
        </div>
        <SignInAgain ready={ready} />
      </Find>
    </Toasts>
  );
}
