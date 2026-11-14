// The studio's home: what waits for whoever signed in, each where they do it, on its own page
// or at the command line; their drafts; and where to go next. Everyone the directory knows
// has one, whether or not they hold a role.

import { get, type DraftLine } from "../api";
import { Link } from "../router";
import { PageHead, useLoad, Waiting, when } from "../ui";

type Waits = { kind: string; what: string; why: string[]; go: string | null; how?: string };
type Home = { you: string; waiting: Waits[]; drafts: DraftLine[]; catalogue: boolean; authoring: boolean };

export function HomePage() {
  const { data, error } = useLoad(() => get<Home>("/studio/api/home"), []);
  return (
    <>
      <PageHead title={data ? `Welcome, ${data.you.split(" ")[0]}` : "Welcome"}
                about="What waits for you in a5s, and where you do it. Nothing here is done for you: each opens where it's done, signed in afresh where it counts." />
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card" id="waiting">
            <h3>Waiting on you</h3>
            {data.waiting.length === 0
              ? <p className="note">Nothing waits on you now.</p>
              : (
                <ul className="waits">{data.waiting.map((w) => (
                  <li key={`${w.kind}:${w.what}`} className={`wait wait-${w.kind}`}>
                    {w.go ? <a href={w.go}>{w.what}</a> : <span>{w.what}</span>}
                    {w.how && <span className="faint"> · <span className="mono">{w.how}</span></span>}
                    {w.why.length > 0 && <ul className="plain faint">{w.why.map((why) => <li key={why}>{why}</li>)}</ul>}
                  </li>
                ))}</ul>
              )}
          </section>
          {data.drafts.length > 0 && (
            <section className="card" id="my-drafts">
              <h3>Your drafts</h3>
              <ul className="plain">{data.drafts.map((d) => (
                <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
                  <span className="faint"> · from {d.based_on} · kept {when(d.updated_at)}</span></li>
              ))}</ul>
            </section>
          )}
          <section className="card" id="next">
            <h3>In the studio</h3>
            <ul className="plain">
              {data.catalogue && <li><Link to={{ page: "agents" }}>The agents you may watch</Link>, and how each is doing</li>}
              {data.authoring && <li><Link to={{ page: "new" }}>A new agent</Link>, from a template</li>}
              <li><Link to={{ page: "you" }}>What you may do in a5s</Link>, and which group gave you each role</li>
            </ul>
          </section>
        </>
      )}
    </>
  );
}
