// The administrators' page, folded into the studio from its own (core/admin_api.py), for those
// who hold one of a5s's roles, or run it: who holds each role and what gave it them, the
// directory or a group of the identity provider's; what waits for whom; what nobody answers for;
// and the latest administrative acts. It only shows: a change is made in the settings, or with
// `a5s release` for a release.

import { type AdminAct, type AdminNow, get } from "../api";
import { PageHead, useLoad, Waiting, when } from "../ui";

const by = (act: AdminAct) => (Array.isArray(act.by) ? act.by.join(", ") : act.by) || "a5s";

function Listed({ id, items, none }: { id: string; items: { key: string; text: string; warn?: boolean }[]; none: string }) {
  return (
    <ul id={id} className="plain">
      {items.map((item) => <li key={item.key} className={item.warn ? "warn" : undefined}>{item.text}</li>)}
      {items.length === 0 && <li className="note">{none}</li>}
    </ul>
  );
}

export function AdminPage() {
  const { data, error } = useLoad(() => get<AdminNow>("/admin/api"), []);
  return (
    <>
      <PageHead title="Administration"
                about="Who holds each role in a5s, and what gave it them: the directory, or a group in your identity provider. Then what waits for whom, what nobody answers for, and what was done lately. This page only shows: to change anything, use the settings, or `a5s release` for a release." />
      {!data && <Waiting error={error} />}
      {data && (
        <div id="shown">
          <section className="card">
            <h2>Who holds each role</h2>
            <table className="figures">
              <thead><tr><th>Role</th><th>Held by</th></tr></thead>
              <tbody id="roles">{data.roles.map((row) => (
                <tr key={row.role}>
                  <td><strong>{row.name}</strong><span className="role-id mono">{row.role}</span></td>
                  <td>
                    {row.held_by.length === 0 && <span className="badge warn">nobody</span>}
                    {row.held_by.map((h, i) => (
                      <span key={h.id}>{i > 0 && <br />}{h.name} <span className="faint">({h.by.join(", ")})</span></span>
                    ))}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </section>
          <section className="card">
            <h2>Groups that give roles</h2>
            <p id="claim" className="note">{data.claim
              ? `Sign-ins show their groups in the ${data.claim} claim. A role a group gives counts from someone's latest sign-in.`
              : "This deployment reads no groups from sign-ins, so the directory alone gives roles."}</p>
            <Listed id="groups" none="None: the settings in force give no group a role." items={data.groups.map((g) => ({
              key: g.group, text: `${g.group}: ${g.roles.join(", ")}, for ${g.people} ${g.people === 1 ? "person" : "people"} as their latest sign-ins showed` }))} />
          </section>
          <div className="two-up">
            <section className="card">
              <h2>What waits for whom</h2>
              <Listed id="waiting" none="Nothing waits." items={[
                ...data.waiting.settings.map((v) => ({ key: `settings:${v.serial}`,
                  text: `Settings, version ${v.serial}: ${v.needs.length ? v.needs.join("; ") : "approved, for a5s to apply"}` })),
                ...data.waiting.release.map((problem) => ({ key: `release:${problem}`, text: `The release: ${problem}` })),
                ...data.waiting.held_changes.map((held) => ({ key: `held:${held.part}`,
                  text: `${held.waiting} held ${held.waiting === 1 ? "change" : "changes"} in ${held.part}, for ${held.deciders.join(", ") || "nobody"} to decide` })),
              ]} />
            </section>
            <section className="card">
              <h2>Nobody answers for</h2>
              <Listed id="ownerless" none="Everything has someone who answers for it." items={[
                ...data.ownerless.agents.map((a) => ({ key: `agent:${a.agent}`, warn: true, text: `The ${a.agent}: ${a.what}. To do: ${a.do}.` })),
                ...data.ownerless.instances.map((i) => ({ key: `instance:${i.instance}`, warn: true, text: `${i.instance}, of the ${i.agent}: ${i.what}. To do: ${i.do}.` })),
                ...data.ownerless.parts.map((p) => ({ key: `part:${p.part}`, warn: true, text: `${p.part}: ${p.what}. To do: ${p.do}.` })),
              ]} />
            </section>
          </div>
          <section className="card">
            <h2 id="latest-title">The latest acts, over the last {data.days} days</h2>
            <Listed id="latest" none="Nothing was done." items={data.latest.map((act) => ({
              key: String(act.seq), text: `${act.at ? when(act.at) : "when, unknown"}: ${by(act)} ${act.what}${act.instance ? `, ${act.instance}` : ""}` }))} />
          </section>
        </div>
      )}
    </>
  );
}
