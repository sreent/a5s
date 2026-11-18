// The audit trail, folded into the studio from its own page (core/audit_api.py): the ledger as
// an auditor or assurance reads it, read only, signed in with a second factor where the
// deployment asks for one. Everything a5s did and decided, in the order it happened, and never
// what anyone said, which it keeps by hash alone. Whoever approved, decided, signed or read the
// trail shows as themselves; whom agents acted for, as a stand-in, until the data protection
// officer agrees to names. Each search here is itself in the ledger.

import { type ReactNode, useState } from "react";
import { type AuditEntries, type AuditExport, type AuditNow, type AuditReport, type AuditTrail, get } from "../api";
import { signInStronger } from "../auth";
import { locale, t } from "../i18n";
import { PageHead, plural, useLoad, Waiting } from "../ui";

type Entry = { seq: number; at: string; kind: string; action: string; decision: string; instance?: string;
               acts_for?: string[]; reasons?: string[]; args?: Record<string, unknown> };
type Filters = Record<"since" | "until" | "kind" | "action" | "decision" | "instance" | "for" | "by", string>;

const ACTORS = ["admin", "audit", "proposal"];  // entries whose `by` acted in one of a5s's roles
const BLANK: Filters = { since: "", until: "", kind: "", action: "", decision: "", instance: "", for: "", by: "" };

// When, to the second, in UTC as the search's period is: the ledger's exact time stays in what's
// exported
const when = (at: string) =>
  `${new Date(at).toLocaleString(locale(), { dateStyle: "medium", timeStyle: "medium", timeZone: "UTC" })} UTC`;
const utc = (value: string) => (!value ? null : value.length === 16 ? `${value}:00Z` : `${value}Z`);

/** What an entry or an act holds, as the ledger has it: a box that scrolls when it's long, which
 * keyboards reach as well as a mouse's wheel. */
function Held({ value }: { value: unknown }) {
  return <pre className="entries" tabIndex={0}>{JSON.stringify(value, null, 1)}</pre>;
}

// How long ago, in the words of the language spoken
const ago = (n: number, unit: "minute" | "hour") => (n > 0 ? t("{n} ago", { n: plural(n, unit) })
  : unit === "minute" ? t("just now") : t("within the last hour"));

/** Whether the trail checks out, as a5s's copier last found it (round 15, E8): it reads every
 * locked copy once a day, so this page needn't. An entry is evidence only once it's copied, so
 * the newest say so. */
function Trail({ trail }: { trail: AuditTrail | null }) {
  return (
    <section className="card" id="trail">
      <h2>{t("Whether the trail checks out")}{" "}
        {trail?.checks_out && <span className="badge good">{t("It checks out")}</span>}
        {trail && trail.problems.length > 0 && <span className="badge bad">{t("It doesn't check out")}</span>}
        {trail && !trail.checks_out && trail.problems.length === 0 && <span className="badge warn">{t("Not checked yet")}</span>}
      </h2>
      {!trail && <p className="note">{t("a5s keeps no locked copies of the ledger here, so nothing shows whether anyone rewrote it.")}</p>}
      {trail && trail.problems.length > 0 && (
        <>
          <p>{t("What a5s found wrong with the ledger and its locked copies:")}</p>
          <ul id="problems">{trail.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>
          <p className="note">{t("Tell assurance and the team that runs a5s: until they know why, take what this page shows as unproven.")}</p>
        </>
      )}
      {trail?.checks_out && trail.checked_hours_ago !== null && (
        <p>{t("Every entry follows the one before it, and the ledger matched its locked copies when a5s last checked it whole, {when}.",
          { when: ago(trail.checked_hours_ago, "hour") })}</p>
      )}
      {trail && !trail.checks_out && trail.problems.length === 0 && (
        <p>{t("a5s checks the whole ledger against its locked copies when its copier starts, and once a day: it hasn't yet.")}</p>
      )}
      {trail && (
        <p className="note">{trail.copied_through === null ? t("Nothing is copied yet.")
          : t("The locked copies hold every entry through #{seq}, copied {when}.",
              { seq: trail.copied_through, when: ago(trail.copied_minutes_ago ?? 0, "minute") })}{" "}
          {t("Entries written since aren't copied yet: what people decided is copied within a minute, and the rest within 15 minutes. Until they are, someone with the database's own powers could rewrite them unseen.")}
          {trail.failing && ` ${t("The copier's last try failed: it tries again each minute.")}`}
        </p>
      )}
    </section>
  );
}

function period(filters: Filters): URLSearchParams {
  const query = new URLSearchParams();
  for (const name of ["since", "until"] as const) {
    const at = utc(filters[name]);
    if (at) query.set(name, at);
  }
  return query;
}

export function AuditPage() {
  const now = useLoad(() => get<AuditNow>("/audit/api"), []);
  const [filters, setFilters] = useState<Filters>(BLANK);
  const [asked, setAsked] = useState<URLSearchParams>();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [copiedThrough, setCopiedThrough] = useState<number | null>(null);  // (round 15, E8)
  const [broken, setBroken] = useState<Set<number>>(new Set());
  const [report, setReport] = useState<AuditReport>();
  const [status, setStatus] = useState<string>();

  const run = async (work: () => Promise<void>) => {
    try {
      setStatus(t("Reading the ledger…"));
      await work();
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const search = (given: Filters, more: boolean) => run(async () => {
    let query: URLSearchParams;
    if (more && asked) {
      query = new URLSearchParams(asked);
      if (next) query.set("after", String(next));
    } else {
      query = period(given);
      for (const name of ["kind", "action", "decision", "instance", "for", "by"] as const) {
        const value = given[name].trim();
        if (value) query.set(name, value);
      }
      setAsked(query);
      setReport(undefined);
    }
    const found = await get<AuditEntries>(`/audit/api/entries?${query}`);
    const shown = found.entries as unknown as Entry[];
    setEntries((was) => (more ? [...was, ...shown] : shown));
    setNext(found.next);
    setCopiedThrough(found.copied_through);
    setBroken((was) => new Set([...(more ? was : []), ...found.broken]));
    setStatus(shown.length || more ? "" : t("No entries in that period, as asked."));
  });

  const finding = (name: "for" | "by", value: string): ReactNode => (
    <button type="button" key={value} onClick={() => {
      const given = { ...filters, for: name === "for" ? value : "", by: name === "by" ? value : "" };
      setFilters(given);
      search(given, false);
    }}>{value}</button>
  );

  const people = (label: string, name: "for" | "by", values: string[]) => (
    <p className="note">{label} {values.map((value, i) => <span key={value}>{i > 0 && ", "}{finding(name, value)}</span>)}</p>
  );

  const reported = () => run(async () => {
    setReport(await get<AuditReport>(`/audit/api/report?${period(filters)}`));
    setStatus("");
  });

  const exported = () => run(async () => {  // the period exactly as the ledger holds it, a page at a time
    const lines: string[] = [];
    let after: number | null = null;
    let bounds: Record<string, unknown> = {};
    do {
      const query = period(filters);
      if (after) query.set("after", String(after));
      const page: AuditExport = await get<AuditExport>(`/audit/api/export?${query}`);
      for (const entry of page.entries) lines.push(JSON.stringify(entry));
      after = page.next;
      bounds = { ...page.bounds, head: page.head };
    } while (after);
    const file = new Blob([[JSON.stringify({ export: bounds }), ...lines].map((each) => `${each}\n`).join("")],
                          { type: "application/x-ndjson" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(file);
    link.download = "a5s-audit.jsonl";
    link.click();
    URL.revokeObjectURL(link.href);
    setStatus(t("Exported {n} entries. Check them yourself, against the ledger's locked copies, with: a5s audit verify a5s-audit.jsonl",
      { n: lines.length }));
  });

  const set = (name: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [name]: e.target.value });
  const weaker = now.error && now.error.includes("second factor");  // signed in without one
  return (
    <>
      <PageHead title={t("Audit trail")}
                about={t("The ledger, as an auditor reads it: everything a5s did and decided, in the order it happened, and never what anyone said, which it keeps by hash alone. Whoever approved, decided, signed or read the trail shows as themselves. Each search here is itself in the ledger.")} />
      {now.data && <p id="naming" className="note">{now.data.names
        ? t("Whom agents acted for shows by name, as the data protection officer agreed.")
        : t("Whom agents acted for, told or asked about shows as a stand-in, the same one each time, until the data protection officer agrees to names.")}</p>}
      <p id="status" role="status" className="note">{status}</p>
      {!now.data && <Waiting error={now.error} />}
      {weaker && (
        <div className="actions">
          <button type="button" className="primary" id="stronger" onClick={() => {
            signInStronger().catch((e: Error) => setStatus(e.message));
          }}>{t("Sign in again, with a second factor")}</button>
        </div>
      )}
      {now.data && <Trail trail={now.data.trail} />}
      {now.data && (
        <section className="card" id="find">
          <h2>{t("Find entries")}</h2>
          <p>
            <label htmlFor="since">{t("From")}</label> <input id="since" type="datetime-local" value={filters.since} onChange={set("since")} />{" "}
            <label htmlFor="until">{t("to before")}</label> <input id="until" type="datetime-local" value={filters.until} onChange={set("until")} />{" "}
            <span className="note">{t("in UTC")}</span>
          </p>
          <p>
            <label htmlFor="kind">{t("Kind")}</label>{" "}
            <select id="kind" value={filters.kind} onChange={set("kind")}>
              <option value="">{t("any")}</option>
              {now.data.kinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
            </select>{" "}
            <label htmlFor="action">{t("action")}</label> <input id="action" size={12} value={filters.action} onChange={set("action")} />{" "}
            <label htmlFor="decision">{t("decision")}</label>{" "}
            <select id="decision" value={filters.decision} onChange={set("decision")}>
              {/* the ledger's own decisions, as its entries say them */}
              <option value="">{t("any")}</option><option>allow</option><option>deny</option><option>record</option>
            </select>
          </p>
          <p>
            <label htmlFor="instance">{t("Instance")}</label> <input id="instance" size={16} value={filters.instance} onChange={set("instance")} />{" "}
            <label htmlFor="for">{t("acting for")}</label> <input id="for" size={20} value={filters.for} onChange={set("for")} />{" "}
            <label htmlFor="by">{t("by")}</label> <input id="by" size={12} value={filters.by} onChange={set("by")} />
          </p>
          <div className="actions">
            <button type="button" id="search" className="primary" onClick={() => search(filters, false)}>{t("Find")}</button>
            <button type="button" id="report" onClick={reported}>{t("Who holds each role, and who did what")}</button>
            {now.data.exports && <button type="button" id="export" onClick={exported}>{t("Export the period")}</button>}
          </div>
          <ul id="entries" className="plain">{entries.map((entry) => {
            const args = entry.args || {};
            const by = ACTORS.includes(entry.kind) && args.by ? (Array.isArray(args.by) ? args.by : [args.by]).map(String) : [];
            return (
              <li key={entry.seq}>
                <p>#{entry.seq}, {when(entry.at)}: {entry.kind} {entry.action}, {entry.decision}{entry.instance ? `, ${entry.instance}` : ""}
                  {broken.has(entry.seq) && <> <span className="badge bad" data-broken>{t("doesn't check out")}</span></>}
                  {now.data?.trail && (copiedThrough === null || entry.seq > copiedThrough)
                    && <> <span className="badge warn" data-uncopied>{t("not copied yet")}</span></>}</p>
                {(entry.acts_for || []).length > 0 && people(t("For"), "for", entry.acts_for || [])}
                {by.length > 0 && people(t("By"), "by", by)}
                {(entry.reasons || []).length > 0 && <p className="note">{t("Why: {why}", { why: (entry.reasons || []).join(", ") })}</p>}
                {Object.keys(args).length > 0 && <Held value={args} />}
              </li>
            );
          })}</ul>
          {next && <button type="button" id="more" onClick={() => search(filters, true)}>{t("Later entries")}</button>}
        </section>
      )}
      {report && (
        <section className="card" id="roles">
          <h2>{t("Who holds each role now")}</h2>
          <ul id="holders" className="plain">{report.roles.map((row) => (
            <li key={row.role}>{row.role}: {row.held_by.join(", ") || t("nobody")}</li>
          ))}</ul>
          <h2>{t("What was done in the period")}</h2>
          <ul id="acts" className="plain">
            {report.acts.map((act) => (
              <li key={act.seq}>
                <p>{act.at ? when(act.at) : t("when, unknown")}: {(Array.isArray(act.by) ? act.by.join(", ") : act.by) || "a5s"} {act.what}{act.instance ? `, ${act.instance}` : ""}</p>
                {Object.keys(act.about || {}).length > 0 && <Held value={act.about} />}
              </li>
            ))}
            {report.acts.length === 0 && <li className="note">{t("Nothing was done in the period.")}</li>}
          </ul>
        </section>
      )}
    </>
  );
}
