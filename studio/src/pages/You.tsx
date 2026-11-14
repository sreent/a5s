// What someone may do in a5s: each role they hold, what gave it them, the directory or a group
// of the identity provider's, and what it lets them do. Roles change where people are managed,
// in the identity provider, and in the signed settings that give its groups roles: not here.

import { get } from "../api";
import { PageHead, useLoad, Waiting } from "../ui";

type Role = { role: string; by: string[]; may: string };
type You = { you: string; id: string; roles: Role[]; groups: string[] };

export function YouPage() {
  const { data, error } = useLoad(() => get<You>("/studio/api/you"), []);
  return (
    <>
      <PageHead crumbs={[{ label: "Home", to: { page: "home" } }]} title="What you may do"
                about="Each of your roles in a5s, what gave it you, and what it lets you do. Your organisation manages its groups in its identity provider, and a5s's signed settings say what each group may do: a role you lose there stops working at your next sign-in." />
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card" id="roles">
            <h3>{data.you}</h3>
            {data.roles.length === 0
              ? <p className="note">You hold none of a5s's roles: you use the agents that serve you, and see your own tasks and notebook. Whoever approves the agent you'd use can add you.</p>
              : (
                <table className="grid-table">
                  <thead><tr><th>Role</th><th>Lets you</th><th>Given by</th></tr></thead>
                  <tbody>{data.roles.map((r) => (
                    <tr key={r.role}><td className="mono">{r.role}</td><td>{r.may}</td><td>{r.by.join(", ")}</td></tr>
                  ))}</tbody>
                </table>
              )}
          </section>
          <section className="card" id="groups">
            <h3>Your groups</h3>
            {data.groups.length === 0
              ? <p className="note">Your latest sign-in showed none of the groups a5s's settings give roles.</p>
              : <p>Your latest sign-in showed {data.groups.map((g, i) => <span key={g}>{i > 0 && ", "}<span className="mono">{g}</span></span>)}.</p>}
          </section>
        </>
      )}
    </>
  );
}
