// The audit trail, folded into the studio from its own page (core/audit_api.py): the ledger as
// an auditor or assurance reads it, read only, signed in with a second factor where the
// deployment asks for one. Everything a5s did and decided, in the order it happened, and never
// what anyone said, which it keeps by hash alone. Whoever approved, decided, signed or read the
// trail shows as themselves; whom agents acted for, as a stand-in, until the data protection
// officer agrees to names. Each search here is itself in the ledger.

import { type ReactNode, useState } from "react";
import { type AuditEntries, type AuditExport, type AuditNow, type AuditReport, get } from "../api";
import { signInStronger } from "../auth";
import { PageHead, useLoad, Waiting } from "../ui";

type Entry = { seq: number; at: string; kind: string; action: string; decision: string; instance?: string;
               acts_for?: string[]; reasons?: string[]; args?: Record<string, unknown> };
type Filters = Record<"since" | "until" | "kind" | "action" | "decision" | "instance" | "for" | "by", string>;

const ACTORS = ["admin", "audit", "proposal"];  // entries whose `by` acted in one of a5s's roles
const BLANK: Filters = { since: "", until: "", kind: "", action: "", decision: "", instance: "", for: "", by: "" };

// When, to the second, in UTC as the search's period is: the ledger's exact time stays in what's
// exported
const when = (at: string) =>
  `${new Date(at).toLocaleString([], { dateStyle: "medium", timeStyle: "medium", timeZone: "UTC" })} UTC`;
const utc = (value: string) => (!value ? null : value.length === 16 ? `${value}:00Z` : `${value}Z`);

/** What an entry or an act holds, as the ledger has it: a box that scrolls when it's long, which
 * keyboards reach as well as a mouse's wheel. */
function Held({ value }: { value: unknown }) {
  return <pre className="entries" tabIndex={0}>{JSON.stringify(value, null, 1)}</pre>;
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
  const [report, setReport] = useState<AuditReport>();
  const [status, setStatus] = useState<string>();

  const run = async (work: () => Promise<void>) => {
    try {
      setStatus("Reading the ledger…");
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
    setStatus(shown.length || more ? "" : "No entries in that period, as asked.");
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
    setStatus(`Exported ${lines.length} entries. Check them yourself, against the ledger's locked copies, with: a5s audit verify a5s-audit.jsonl`);
  });

  const set = (name: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [name]: e.target.value });
  const weaker = now.error && now.error.includes("second factor");  // signed in without one
  return (
    <>
      <PageHead title="Audit trail"
                about="The ledger, as an auditor reads it: everything a5s did and decided, in the order it happened, and never what anyone said, which it keeps by hash alone. Whoever approved, decided, signed or read the trail shows as themselves. Each search here is itself in the ledger." />
      {now.data && <p id="naming" className="note">{now.data.names
        ? "Whom agents acted for shows by name, as the data protection officer agreed."
        : "Whom agents acted for, told or asked about shows as a stand-in, the same one each time, until the data protection officer agrees to names."}</p>}
      <p id="status" role="status" className="note">{status}</p>
      {!now.data && <Waiting error={now.error} />}
      {weaker && (
        <div className="actions">
          <button type="button" className="primary" id="stronger" onClick={() => {
            signInStronger().catch((e: Error) => setStatus(e.message));
          }}>Sign in again, with a second factor</button>
        </div>
      )}
      {now.data && (
        <section className="card" id="find">
          <h2>Find entries</h2>
          <p>
            <label htmlFor="since">From</label> <input id="since" type="datetime-local" value={filters.since} onChange={set("since")} />{" "}
            <label htmlFor="until">to before</label> <input id="until" type="datetime-local" value={filters.until} onChange={set("until")} />{" "}
            <span className="note">in UTC</span>
          </p>
          <p>
            <label htmlFor="kind">Kind</label>{" "}
            <select id="kind" value={filters.kind} onChange={set("kind")}>
              <option value="">any</option>
              {now.data.kinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
            </select>{" "}
            <label htmlFor="action">action</label> <input id="action" size={12} value={filters.action} onChange={set("action")} />{" "}
            <label htmlFor="decision">decision</label>{" "}
            <select id="decision" value={filters.decision} onChange={set("decision")}>
              <option value="">any</option><option>allow</option><option>deny</option><option>record</option>
            </select>
          </p>
          <p>
            <label htmlFor="instance">Instance</label> <input id="instance" size={16} value={filters.instance} onChange={set("instance")} />{" "}
            <label htmlFor="for">acting for</label> <input id="for" size={20} value={filters.for} onChange={set("for")} />{" "}
            <label htmlFor="by">by</label> <input id="by" size={12} value={filters.by} onChange={set("by")} />
          </p>
          <div className="actions">
            <button type="button" id="search" className="primary" onClick={() => search(filters, false)}>Find</button>
            <button type="button" id="report" onClick={reported}>Who holds each role, and who did what</button>
            {now.data.exports && <button type="button" id="export" onClick={exported}>Export the period</button>}
          </div>
          <ul id="entries" className="plain">{entries.map((entry) => {
            const args = entry.args || {};
            const by = ACTORS.includes(entry.kind) && args.by ? (Array.isArray(args.by) ? args.by : [args.by]).map(String) : [];
            return (
              <li key={entry.seq}>
                <p>#{entry.seq}, {when(entry.at)}: {entry.kind} {entry.action}, {entry.decision}{entry.instance ? `, ${entry.instance}` : ""}</p>
                {(entry.acts_for || []).length > 0 && people("For", "for", entry.acts_for || [])}
                {by.length > 0 && people("By", "by", by)}
                {(entry.reasons || []).length > 0 && <p className="note">Why: {(entry.reasons || []).join(", ")}</p>}
                {Object.keys(args).length > 0 && <Held value={args} />}
              </li>
            );
          })}</ul>
          {next && <button type="button" id="more" onClick={() => search(filters, true)}>Later entries</button>}
        </section>
      )}
      {report && (
        <section className="card" id="roles">
          <h2>Who holds each role now</h2>
          <ul id="holders" className="plain">{report.roles.map((row) => (
            <li key={row.role}>{row.role}: {row.held_by.join(", ") || "nobody"}</li>
          ))}</ul>
          <h2>What was done in the period</h2>
          <ul id="acts" className="plain">
            {report.acts.map((act) => (
              <li key={act.seq}>
                <p>{act.at ? when(act.at) : "when, unknown"}: {(Array.isArray(act.by) ? act.by.join(", ") : act.by) || "a5s"} {act.what}{act.instance ? `, ${act.instance}` : ""}</p>
                {Object.keys(act.about || {}).length > 0 && <Held value={act.about} />}
              </li>
            ))}
            {report.acts.length === 0 && <li className="note">Nothing was done in the period.</li>}
          </ul>
        </section>
      )}
    </>
  );
}
