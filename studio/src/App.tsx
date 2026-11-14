// The studio: signed in once, through the organisation's identity provider, then each of its
// pages in turn, beside the sidebar every page of a5s has.

import { useEffect, useState } from "react";
import { signedIn } from "./api";
import { signIn } from "./auth";
import { AgentPage } from "./pages/Agent";
import { AgentsPage } from "./pages/Agents";
import { InstancePage } from "./pages/Instance";
import { RunPage } from "./pages/Run";
import { reread, useRoute } from "./router";
import { Sidebar } from "./Sidebar";

type State = "signing-in" | "ready" | { problem: string };

export function App() {
  const [state, setState] = useState<State>("signing-in");
  const route = useRoute();
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
  if (state === "signing-in") content = <p className="note" role="status">Signing you in…</p>;
  else if (typeof state === "object") content = <p className="problem" role="status">{state.problem}</p>;
  else if (route.page === "agent") content = <AgentPage key={route.agent} id={route.agent} />;
  else if (route.page === "instance") content = <InstancePage key={route.instance} id={route.instance} />;
  else if (route.page === "run") content = <RunPage key={route.run} id={route.run} />;
  else content = <AgentsPage />;
  return (
    <>
      <Sidebar signedIn={state === "ready"} />
      <div className="page studio">
        <main>{content}</main>
      </div>
    </>
  );
}
