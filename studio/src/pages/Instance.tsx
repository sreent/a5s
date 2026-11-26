// An instance's page: what of it waits, and where each is done; suspending or resuming it,
// signed in afresh for that alone; how far it may act in each part; how it's doing over a
// period, from the measures counted for it alone; and its runs, a page at a time, those whose
// every record the viewer may see.

import { useEffect, useState } from "react";
import { type Catalogue, type Figures, get, type Instance, type RunLine, type RunsPage, send,
         type Standing, type StatusAsked } from "../api";
import { hashed, salted, signInFor, takeAct } from "../auth";
import { ActingAs, ActionZone, Skeleton, useToast } from "../design";
import { locale, t } from "../i18n";
import { levelName } from "../levels";
import { Link } from "../router";
import { mayUse, shellOf } from "../Sidebar";
import { RunsByDay } from "../RunsByDay";
import { aboutInstance, type Loaded, OutcomeBadge, PageHead, people, plural, runners, share, StatusBadge,
         useLoad, Waiting, WaitList, when, Wide } from "../ui";

/** What of it waits: the changes it asked for, its samples for a grade, and its notebook, each
 * where it's done, for the viewer or for others. */
function Waits({ standing }: { standing: Loaded<Standing> }) {
  return (
    <section className="card" id="instance-waiting">
      <h2>{t("What waits on it")}</h2>
      {standing.data ? <WaitList waiting={standing.data.waiting} none={t("Nothing of it waits now.")} />
                     : <Waiting error={standing.error} />}
    </section>
  );
}

/** Who asked to suspend or resume it, and when, in a sentence: each of the two its own, as the
 * language spoken puts it. */
function askedTo(by: string, action: string, at: string): string {
  if (action === "suspend") return t("{by} asked to suspend it, {when}: a5s does so within a minute, once it has checked that sign-in again.", { by, when: at });
  if (action === "resume") return t("{by} asked to resume it, {when}: a5s does so within a minute, once it has checked that sign-in again.", { by, when: at });
  return t("{by} asked to {action} it, {when}: a5s does so within a minute, once it has checked that sign-in again.", { by, action, when: at });
}

/** What was asked of it, and whether it went wrong, beside its head, and a way to its settings,
 * for those who approve versions of them: what changes nothing yet. */
function Stopping({ id, standing, settles, problem }: {
  id: string; standing?: Standing; settles: boolean; problem?: string;
}) {
  const asked = standing?.asked;
  return (
    <>
      {asked && <p className="note" role="status" id="asked">{askedTo(asked.by, asked.action, when(asked.at))}</p>}
      {problem && <p className="problem" role="alert">{problem}</p>}
      {settles && (
        <div className="actions">
          <Link to={{ page: "settings", search: `?instance=${encodeURIComponent(id)}` }} className="button"
                id="its-settings">{t("Change its settings")}</Link>
        </div>
      )}
    </>
  );
}

/** Suspending it, which stops it at its next step, or resuming it, which only whoever suspended
 * it may, or the release approver: in a zone of its own, right below the head, as it may be
 * wanted at once, saying first whom it reaches (docs/design.md). Each is signed in afresh for
 * that alone, and carried out by a5s within a minute, once it has checked the sign-in again
 * (core/suspension.py): so no dialog besides. */
function Suspending({ inst, may, setProblem }: {
  inst: Instance; may: string; setProblem: (problem: string) => void;
}) {
  const go = (action: "suspend" | "resume") => () => {
    const salt = salted();  // the act's nonce, as core/suspension.py's `nonce` makes it
    hashed(`a5s ${action} instance ${inst.id} ${salt}`)
      .then((nonce) => signInFor({ kind: "status", action, instance: inst.id, salt }, nonce))
      .catch((e: Error) => setProblem(e.message));
  };
  const whom = inst.people === 1 ? t("the one person it serves") : t("the {n} people it serves", { n: inst.people });
  return (
    <ActionZone title={t("Suspend or resume it")} reach={may === "suspend"
      ? t("Suspending {instance} stops it at its next step, even in a run already going, and it starts no runs, so it answers none of {whom}, who are told it's suspended, until whoever suspended it, or the release approver, resumes it. Nothing it keeps is lost. You sign in again, for this alone.", { instance: inst.id, whom })
      : t("Resuming {instance} lets it answer {whom} again, and work on its own, as its settings say, from its next message. You sign in again, for this alone, with a second factor where your organisation asks for one.", { instance: inst.id, whom })}>
      {may === "suspend"
        ? <button type="button" id="suspend" className="primary" onClick={go("suspend")}>{t("Sign in and suspend it")}</button>
        : <button type="button" id="resume" className="primary" onClick={go("resume")}>{t("Sign in and resume it")}</button>}
    </ActionZone>
  );
}

/** How far it may act in each part, and each type of change its settings set a level for. */
function Reach({ inst }: { inst: Instance }) {
  const parts = Object.entries(inst.parts as Record<string, number>);
  const acts = inst.actions as Record<string, Record<string, number>>;
  return (
    <section className="card" id="reach">
      <h2>{t("How far it may act")}</h2>
      {parts.length === 0 ? <p>{t("It {level}, in no part.", { level: levelName(inst.level) })}</p> : (
        <Wide label={t("How far it may act")}><table className="grid-table compact">
          <thead><tr><th>{t("Part")}</th><th>{t("What it may do")}</th><th>{t("By type of change")}</th></tr></thead>
          <tbody>{parts.map(([part, level]) => {
            const own = Object.entries(acts[part] ?? {});
            return (
              <tr key={part}>
                <td>{part}</td>
                <td>{levelName(level)}</td>
                <td>{own.length === 0 ? <span className="faint">{t("none")}</span> : own.map(([action, at]) => (
                  <div key={action}><span className="mono">{action}</span> {levelName(at)}</div>
                ))}</td>
              </tr>
            );
          })}</tbody>
        </table></Wide>
      )}
      <p className="note">{t("As the settings its parts' owners signed give it. A type of change it may make on its own is made so only once graded samples show it's accurate enough there; until they do, a person decides each.")}</p>
    </section>
  );
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {detail && <div className="tile-detail">{detail}</div>}
    </div>
  );
}

function Tiles({ figures }: { figures: Figures }) {
  const runs = figures.ended.reduce((n, e) => n + e.runs, 0);
  const done = figures.ended.filter((e) => e.outcome === "done").reduce((n, e) => n + e.runs, 0);
  const modelled = figures.runs.reduce((n, r) => n + r.runs, 0);
  const tokens = modelled ? Math.round(figures.runs.reduce((n, r) => n + r.runs * r.tokens_per_run, 0) / modelled) : 0;
  const cached = figures.runs.find((r) => r.cached_share !== null)?.cached_share ?? null;
  const denied = figures.denied.reduce((n, d) => n + d.times, 0);
  return (
    <div className="tiles">
      <Tile label={t("Runs")} value={runs.toLocaleString(locale())} detail={t("{n} called a model", { n: modelled.toLocaleString(locale()) })} />
      <Tile label={t("Ended done")} value={runs ? `${Math.round((done / runs) * 100)}%` : t("none yet")}
            detail={t("{done} of {runs}", { done: done.toLocaleString(locale()), runs: runs.toLocaleString(locale()) })} />
      <Tile label={t("Tokens a run")} value={tokens.toLocaleString(locale())} detail={t("{share} cached", { share: share(cached) })} />
      <Tile label={t("Denied")} value={denied.toLocaleString(locale())} detail={figures.denied_partial ? t("the latest only") : t("calls a5s refused")} />
      <Tile label={t("Held changes")} value={figures.held.held.toLocaleString(locale())} detail={t("{n} waiting", { n: figures.held.waiting })} />
      <Tile label={t("Graded")} value={figures.samples.graded.toLocaleString(locale())}
            detail={figures.samples.graded ? t("{right} right, {critical} critical", { right: figures.samples.right, critical: figures.samples.critical }) : t("no samples yet")} />
      {figures.judge.both > 0 && (
        <Tile label={t("Its judge agrees")} value={share(figures.judge.agreed_share)}
              detail={t("with people, on {samples}; it missed {missed}", { samples: plural(figures.judge.both, "sample", "samples"), missed: figures.judge.missed })} />
      )}
    </div>
  );
}

function Breakdown({ figures }: { figures: Figures }) {
  const o = figures.obligations;
  const r = figures.reminders;
  return (
    <div className="two-up pairs">
      <section className="card">
        <h2>{t("How runs ended")}</h2>
        {figures.ended.length === 0 ? <p className="note">{t("No runs in this period.")}</p> : (
          <Wide label={t("What it did, by kind")}><table className="grid-table compact">
            <thead><tr><th>{t("Started by")}</th><th>{t("Ended")}</th><th className="num">{t("Runs")}</th></tr></thead>
            <tbody>{figures.ended.map((e) => (
              <tr key={`${e.kind}-${e.outcome}`}><td>{e.kind ?? t("other")}</td><td><OutcomeBadge outcome={e.outcome} /></td><td className="num">{e.runs}</td></tr>
            ))}</tbody>
          </table></Wide>
        )}
      </section>
      <section className="card">
        <h2>{t("What a5s refused")}</h2>
        {figures.denied.length === 0 ? <p className="note">{t("Nothing was denied.")}</p> : (
          <ul className="plain">{figures.denied.map((d) => (
            <li key={`${d.kind}-${d.action}-${d.reasons.join()}`}>
              <span className="mono">{d.action}</span> · {plural(d.times, "time")}
              {d.reasons.length > 0 && <div className="faint">{d.reasons.join(", ")}</div>}
            </li>
          ))}</ul>
        )}
      </section>
      <section className="card">
        <h2>{t("What fell due")}</h2>
        <dl className="facts">
          <dt>{t("What people owed")}</dt><dd>{o.due ? t("{due} due: {on_time} on time, {late} late, {open} open; {chased} chased, {escalated} taken up the line",
            { due: o.due, on_time: o.on_time, late: o.late, open: o.open, chased: o.chased, escalated: o.escalated }) : t("nothing")}</dd>
          <dt>{t("Reminders")}</dt><dd>{r.due ? t("{due} due: {on_time} on time, {missed} missed", { due: r.due, on_time: r.on_time, missed: r.missed }) : t("none fell due")}</dd>
          <dt>{t("Reports sent")}</dt><dd>{figures.reports.map((x) => `${x.source} ${x.outcome}: ${x.reports}`).join("; ") || t("none")}</dd>
        </dl>
      </section>
      <section className="card">
        <h2>{t("Who came back")}</h2>
        {figures.returning.length === 0 ? <p className="note">{t("Nobody wrote before this period.")}</p> : (
          <ul className="plain">{figures.returning.map((x) => (
            <li key={x.agent}>{t("{came_back} of the {people} who wrote to the {agent} before", { came_back: x.came_back, people: people(x.wrote_before), agent: x.agent })}</li>
          ))}</ul>
        )}
      </section>
    </div>
  );
}

function whom(run: RunLine): string {
  const named = run.acts_for.map((p) => p.name || p.id).join(", ");
  return named || (run.people ? people(run.people) : t("nobody"));
}

function Runs({ instance }: { instance: string }) {
  const [pages, setPages] = useState<RunsPage[]>([]);
  const [error, setError] = useState<string>();
  const first = useLoad(() => get<RunsPage>(`/studio/api/instances/${encodeURIComponent(instance)}/runs`), [instance]);
  const all = [...(first.data ? [first.data] : []), ...pages];
  const last = all[all.length - 1];
  const older = async () => {
    try {
      setPages([...pages, await get<RunsPage>(`/studio/api/instances/${encodeURIComponent(instance)}/runs?before=${encodeURIComponent(last.before ?? "")}`)]);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const runs = all.flatMap((p) => p.runs);
  const hidden = all.reduce((n, p) => n + p.hidden, 0);
  return (
    <section className="card wide">
      <h2>{t("Runs")}</h2>
      {!first.data && <Waiting error={first.error} />}
      {first.data?.fewer && <p className="note">{t("It serves fewer than {fewer} people, so its runs show only in its daily figures until the data protection officer agrees to name whom runs act for: one by one, each would say what one of them did.", { fewer: first.data.fewer })}</p>}
      {first.data && !first.data.fewer && runs.length === 0 && <p className="note">{t("No runs you may see.")}</p>}
      {runs.length > 0 && (
        <Wide label={t("Its runs")}><table className="grid-table runs-table">
          <thead><tr><th>{t("When")}</th><th>{t("Started by")}</th><th>{t("For")}</th><th>{t("Ended")}</th><th className="num">{t("Tokens")}</th><th /></tr></thead>
          <tbody>{runs.map((run) => (
            <tr key={run.run}>
              <td>{when(run.opened_at)}</td>
              <td>{run.trigger ?? t("other")}{run.read_outside && <span className="badge outside">{t("read outside content")}</span>}</td>
              <td>{whom(run)}</td>
              <td><OutcomeBadge outcome={run.outcome} /></td>
              <td className="num">{run.tokens.toLocaleString(locale())}</td>
              <td><Link to={{ page: "run", run: run.run }} label={t("The run at {when}", { when: when(run.opened_at) })}>{t("Open")}</Link></td>
            </tr>
          ))}</tbody>
        </table></Wide>
      )}
      {hidden > 0 && <p className="note">{t("And {runs} that read records you may not see.", { runs: plural(hidden, "run") })}</p>}
      {error && <p className="problem">{error}</p>}
      {last?.before && <button type="button" onClick={older}>{t("Older runs")}</button>}
    </section>
  );
}

// The viewer's own time zone, for which days the runs fall on
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function InstancePage({ id }: { id: string }) {
  const toast = useToast();
  const [days, setDays] = useState(30);
  const [again, setAgain] = useState(0);  // to read how it stands again, once something's asked
  const [problem, setProblem] = useState<string>();
  const standing = useLoad(() => get<Standing>(
    `/studio/api/instances/${encodeURIComponent(id)}/standing`), [id, again]);
  useEffect(() => {  // back from signing in for an act on it: ask a5s to carry it out, once
    const act = takeAct();
    if (act?.kind !== "status" || act.instance !== id) return;
    send<StatusAsked>("POST", `/studio/api/instances/${encodeURIComponent(id)}/status`,
                      { action: act.action, salt: act.salt })
      .then(() => {
        setAgain((n) => n + 1);
        toast(act.action === "suspend" ? t("You asked to suspend {instance}: a5s does it within a minute.", { instance: id })
          : t("You asked to resume {instance}: a5s does it within a minute.", { instance: id }));
      })
      .catch((e: Error) => setProblem(e.message));
  }, [id, toast]);
  const catalogue = useLoad(() => get<Catalogue>("/studio/api"), [again]);
  const figures = useLoad(() => get<Figures>(
    `/studio/api/instances/${encodeURIComponent(id)}?days=${days}&zone=${encodeURIComponent(ZONE)}`), [id, days]);
  const inst = catalogue.data?.agents.flatMap((a) => a.instances).find((i) => i.id === id);
  const shell = useLoad(shellOf, []);
  const settles = mayUse(shell.data, "settings");  // approves versions of the settings
  // what it is and what may be done with it arrive together, so nothing below them moves as
  // each comes, as it did by a third of a phone's screen (round 13, C11)
  const head = Boolean(inst && standing.data && (shell.data || shell.error));
  if (standing.error) {  // refused, or none: said once, not by each part of the page (round 13, C10)
    return <><PageHead crumbs={[{ label: t("Agents"), to: { page: "agents" } }]} title={t("An instance")}
                       about={t("One agent at work: whom it serves, how far it may act in each part, what waits on it, and how its runs have gone.")} />
      <Waiting error={standing.error} /></>;
  }
  return (
    <>
      <ActingAs acting={standing.data?.acting} />
      <PageHead crumbs={[{ label: t("Agents"), to: { page: "agents" } },
                         ...(inst ? [{ label: inst.agent, to: { page: "agent" as const, agent: inst.agent } }] : [])]}
                title={inst?.id ?? t("An instance")} badges={inst && <StatusBadge status={inst.status} />}
                about={t("One agent at work: whom it serves, how far it may act in each part, what waits on it, and how its runs have gone.")}>
        {head && inst ? (
          <>
            <div className="meta"><span>{aboutInstance(inst)}</span><span>{t("run by {runners}", { runners: runners(inst) })}</span><Link to={{ page: "map", at: `instance:${inst.id}` }} id="on-the-map">{t("What it depends on")}</Link>{standing.data?.suspended_by && <span>{t("suspended by {person}", { person: standing.data.suspended_by })}</span>}{!inst.current && <span className="badge warn">{t("still on release {release}", { release: inst.release })}</span>}</div>
            <Stopping id={id} standing={standing.data} settles={settles} problem={problem} />
          </>
        ) : <Skeleton lines={2} title={false} bare />}
        <label className="period">{t("Over the last")}{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>{plural(7, "day")}</option><option value={30}>{plural(30, "day")}</option><option value={90}>{plural(90, "day")}</option>
          </select>
        </label>
      </PageHead>
      {head && inst && standing.data?.may && <Suspending inst={inst} may={standing.data.may} setProblem={setProblem} />}
      <div className="two-up">
        <Waits standing={standing} />
        {inst ? <Reach inst={inst} /> : <section className="card" id="reach"><Skeleton lines={3} /></section>}
      </div>
      {!figures.data && <Waiting error={figures.error} />}
      {figures.data && (
        <div className={figures.stale ? "stale" : undefined}>
          <Tiles figures={figures.data} />
          <section className="card">
            <h2>{t("Runs by day")}</h2>
            <RunsByDay days={figures.data.daily} zone={figures.data.zone} />
          </section>
          <Breakdown figures={figures.data} />
        </div>
      )}
      <Runs instance={id} />
    </>
  );
}
