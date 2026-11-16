// The studio's home: what waits for whoever signed in, each where they do it, on its own page
// or at the command line; their drafts; and where to go next. Everyone the directory knows
// has one, whether or not they hold a role.

import { get, type Home } from "../api";
import { Link } from "../router";
import { PageHead, useLoad, Waiting, WaitList, when } from "../ui";

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
            <h2>Waiting on you</h2>
            <WaitList waiting={data.waiting} none="Nothing waits on you now." />
          </section>
          {data.drafts.length > 0 && (
            <section className="card" id="my-drafts">
              <h2>Your drafts</h2>
              <ul className="plain">{data.drafts.map((d) => (
                <li key={d.id}><Link to={{ page: "draft", draft: d.id }} className="mono">{d.agent}</Link>
                  <span className="faint"> · from {d.based_on} · kept {when(d.updated_at)}</span></li>
              ))}</ul>
            </section>
          )}
          <section className="card" id="next">
            <h2>In the studio</h2>
            <ul className="plain">
              {data.catalogue && <li><Link to={{ page: "agents" }}>The agents you may know of</Link>: what each does, and how those you watch are doing</li>}
              {data.authoring && <li><Link to={{ page: "new" }}>A new agent</Link>, from a template</li>}
              <li><Link to={{ page: "you" }}>What you may do in a5s</Link>, and which group gave you each role</li>
            </ul>
          </section>
        </>
      )}
    </>
  );
}
