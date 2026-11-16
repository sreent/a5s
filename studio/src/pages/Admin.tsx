// The administrators' page, folded into the studio from its own (core/admin_api.py), for those
// who hold one of a5s's roles, or run it: who holds each role and what gave it them, the
// directory or a group of the identity provider's; what waits for whom; what nobody answers for;
// and the latest administrative acts. It only shows: a change is made in the settings, or with
// `a5s release` for a release.

import { type AdminAct, type AdminNow, get } from "../api";
import { t } from "../i18n";
import { PageHead, people, plural, useLoad, Waiting, when } from "../ui";

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
      <PageHead title={t("Administration")}
                about={t("Who holds each role in a5s, and what gave it them: the directory, or a group in your identity provider. Then what waits for whom, what nobody answers for, and what was done lately. This page only shows: to change anything, use the settings, or `a5s release` for a release.")} />
      {!data && <Waiting error={error} />}
      {data && (
        <div id="shown">
          <section className="card">
            <h2>{t("Who holds each role")}</h2>
            <table className="figures">
              <thead><tr><th>{t("Role")}</th><th>{t("Held by")}</th></tr></thead>
              <tbody id="roles">{data.roles.map((row) => (
                <tr key={row.role}>
                  <td><strong>{row.name}</strong><span className="role-id mono">{row.role}</span></td>
                  <td>
                    {row.held_by.length === 0 && <span className="badge warn">{t("nobody")}</span>}
                    {row.held_by.map((h, i) => (
                      <span key={h.id}>{i > 0 && <br />}{h.name} <span className="faint">({h.by.join(", ")})</span></span>
                    ))}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </section>
          <section className="card">
            <h2>{t("Groups that give roles")}</h2>
            <p id="claim" className="note">{data.claim
              ? t("Sign-ins show their groups in the {claim} claim. A role a group gives counts from someone's latest sign-in.", { claim: data.claim })
              : t("This deployment reads no groups from sign-ins, so the directory alone gives roles.")}</p>
            <Listed id="groups" none={t("None: the settings in force give no group a role.")} items={data.groups.map((g) => ({
              key: g.group, text: t("{group}: {roles}, for {people} as their latest sign-ins showed",
                { group: g.group, roles: g.roles.join(", "), people: people(g.people) }) }))} />
          </section>
          <div className="two-up">
            <section className="card">
              <h2>{t("What waits for whom")}</h2>
              <Listed id="waiting" none={t("Nothing waits.")} items={[
                ...data.waiting.settings.map((v) => ({ key: `settings:${v.serial}`,
                  text: v.needs.length ? t("Settings, version {serial}: {needs}", { serial: v.serial, needs: v.needs.join("; ") })
                    : t("Settings, version {serial}: approved, for a5s to apply", { serial: v.serial }) })),
                ...data.waiting.release.map((problem) => ({ key: `release:${problem}`, text: t("The release: {problem}", { problem }) })),
                ...data.waiting.held_changes.map((held) => {
                  const changes = plural(held.waiting, "held change");
                  const deciders = held.deciders.join(", ");
                  return { key: `held:${held.part}`, text: deciders
                    ? t("{changes} in {part}, for {deciders} to decide", { changes, part: held.part, deciders })
                    : t("{changes} in {part}, for nobody to decide", { changes, part: held.part }) };
                }),
              ]} />
            </section>
            <section className="card">
              <h2>{t("Nobody answers for")}</h2>
              <Listed id="ownerless" none={t("Everything has someone who answers for it.")} items={[
                ...data.ownerless.agents.map((a) => ({ key: `agent:${a.agent}`, warn: true,
                  text: t("The {agent}: {what}. To do: {do}.", { agent: a.agent ?? "", what: a.what, do: a.do }) })),
                ...data.ownerless.instances.map((i) => ({ key: `instance:${i.instance}`, warn: true,
                  text: t("{instance}, of the {agent}: {what}. To do: {do}.", { instance: i.instance ?? "", agent: i.agent ?? "", what: i.what, do: i.do }) })),
                ...data.ownerless.parts.map((p) => ({ key: `part:${p.part}`, warn: true,
                  text: t("{part}: {what}. To do: {do}.", { part: p.part ?? "", what: p.what, do: p.do }) })),
              ]} />
            </section>
          </div>
          <section className="card">
            <h2 id="latest-title">{t("The latest acts, over the last {days} days", { days: data.days })}</h2>
            <Listed id="latest" none={t("Nothing was done.")} items={data.latest.map((act) => ({
              key: String(act.seq), text: `${act.at ? when(act.at) : t("when, unknown")}: ${by(act)} ${act.what}${act.instance ? `, ${act.instance}` : ""}` }))} />
          </section>
        </div>
      )}
    </>
  );
}
