// What agents' model calls cost each calendar month (core/spending.py), at the prices models.yaml
// gives them: each part and agent someone may see against the budget the settings set it, as
// Ocean's CostPanel draws cost against plan, the spent, the budget and the forecast to the month's
// end on one scale, each with its figure, and a badge once the forecast passes the budget; with
// what each message answered cost, all in, and the pace of the last week; then each instance they
// may watch, as figures. A budget guides: it stops no work, which the token budgets each release
// sets do.

import { get } from "../api";
import type * as gen from "../api.gen";
import { Icon } from "../icons";
import { go, Link } from "../router";
import { PageHead, plural, useLoad, Waiting, Wide } from "../ui";

type Kind = "part" | "agent";

const MONTH = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
const DAY = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "long", timeZone: "UTC" });

/** An amount in the currency models.yaml prices models in, or a plain figure where it names none:
 * to the cent, or to two figures below a cent, so a cheap model's month isn't shown as nothing. */
export function money(n: number, currency: string | null): string {
  const digits: Intl.NumberFormatOptions = n !== 0 && Math.abs(n) < 0.01
    ? { maximumSignificantDigits: 2 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return currency ? n.toLocaleString(undefined, { style: "currency", currency, ...digits })
    : n.toLocaleString(undefined, digits);
}

function named(m: string): string {
  const [y, n] = m.split("-").map(Number);
  return MONTH.format(new Date(Date.UTC(y, n - 1, 1)));
}
function moved(m: string, by: number): string {
  const [y, n] = m.split("-").map(Number);
  const d = new Date(Date.UTC(y, n - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

type Bar = { name: string; amount: number; fill: "s1" | "s3" | "forecast"; told: string };

/** A set of bars on the card's one scale, each with its name and its figure beside it, so a bar
 * is never the only sign; its title is the figure in words, for whoever points at it. */
function Bars({ id, label, bars, scale, currency }:
  { id: string; label: string; bars: Bar[]; scale: number; currency: string | null }) {
  const width = (n: number) => `${scale > 0 ? Math.max(0, Math.min(100, (n / scale) * 100)) : 0}%`;
  return (
    <>
      <p className="label" id={id}>{label}</p>
      <dl aria-labelledby={id}>
        {bars.map((b) => (
          <div className="cost-row" key={b.name}>
            <dt>{b.name}</dt>
            <dd className="cost-bar">
              <svg aria-hidden="true">
                <title>{b.told}</title>
                {b.fill === "forecast"
                  ? <rect className="cost-fill forecast" x="0.75" y="0.75" width={width(b.amount)} height="10.5" rx="3" />
                  : <rect className={`cost-fill ${b.fill}`} width={width(b.amount)} height="100%" rx="3" />}
              </svg>
            </dd>
            <dd className="cost-figure">{money(b.amount, currency)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

/** One part's or agent's month against its budget, as Ocean's CostPanel. */
function Panel({ kind, spend, found }: { kind: Kind; spend: gen.Spend; found: gen.Spending }) {
  const id = `${kind}-${spend.key}`;
  const whose = kind === "part" ? spend.key : `the ${spend.key}`;
  const { currency } = found;
  const ends = DAY.format(new Date(new Date(found.ends).getTime() - 1));
  const so = found.current ? "So far" : `In ${named(found.month)}`;
  const forecast = found.current ? spend.forecast : null;
  const scale = Math.max(spend.spent, spend.budget ?? 0, forecast ?? 0);
  const at = forecast ?? spend.spent;  // what the month comes to, or is on course to
  const over = spend.budget !== null && at > spend.budget ? at - spend.budget : null;
  const end = [
    ...(spend.budget !== null ? [{ name: "Budget", amount: spend.budget, fill: "s1" as const,
                                   told: `Its budget: ${money(spend.budget, currency)} a month` }] : []),
    ...(forecast !== null ? [{ name: "Forecast", amount: forecast, fill: "forecast" as const,
                               told: `On course for ${money(forecast, currency)} by ${ends}, at the last week's pace` }] : []),
  ];
  return (
    <section className="card cost-box" id={id} aria-labelledby={`${id}-title`} data-over={over !== null}>
      <div className="cost">
        <div className="cost-head">
          <h2 id={`${id}-title`}>{spend.key}</h2>
          <p className="note">{kind === "part" ? "A part" : "An agent"} · {found.current
            ? `as of day ${found.day} of ${found.days}` : named(found.month)}</p>
        </div>
        <div className="cost-top">
          <div className="cost-bars">
            <Bars id={`${id}-so-far`} label={so} scale={scale} currency={currency}
                  bars={[{ name: "Spent", amount: spend.spent, fill: "s3",
                           told: `Spent ${money(spend.spent, currency)} ${found.current ? "so far this month" : `in ${named(found.month)}`}` }]} />
            {end.length > 0 && (
              <Bars id={`${id}-at-end`} label={found.current ? `By ${ends}` : "Against"} scale={scale}
                    currency={currency} bars={end} />
            )}
            {spend.budget !== null && (
              <div className="cost-over" id={`${id}-against`}>
                {over !== null
                  ? <span className="badge bad"><Icon name="cross" />{money(over, currency)} over budget</span>
                  : <p className="note">{money(spend.budget - at, currency)} under budget{forecast !== null ? ", at this pace" : ""}</p>}
              </div>
            )}
          </div>
          <div className="cost-indices">
            <div className="cost-index" id={`${id}-per-answer`}>
              <p className="label">Each message answered</p>
              {spend.per_answer !== null ? (
                <>
                  <strong>{money(spend.per_answer, currency)}</strong>
                  <p>All {kind === "part" ? "agents' work there" : "its runs"} cost, reports and chases too, over the {plural(spend.answered, "message")} they answered{kind === "part" ? " there" : ""}.</p>
                </>
              ) : (
                <>
                  <strong>None</strong>
                  <p>{kind === "part" ? "Agents answered no messages there" : "Its runs answered no messages"} {found.current ? "this month" : "that month"}.</p>
                </>
              )}
            </div>
            {found.current && spend.pace !== null ? (
              <div className="cost-index" id={`${id}-pace`}>
                <p className="label">A day, lately</p>
                <strong>{money(spend.pace, currency)}</strong>
                <p>The last 7 days, on average: the pace the forecast goes on at.</p>
              </div>
            ) : (
              <div className="cost-index">
                <p className="label">Runs</p>
                <strong>{spend.runs.toLocaleString()}</strong>
                <p>{spend.tokens.toLocaleString()} tokens.</p>
              </div>
            )}
          </div>
        </div>
        {spend.budget === null && (
          <p className="note">The settings set no budget for {whose}. With one, a5s shows each month against it, and tells {kind === "part" ? "its owners" : "its owners"} on their home page once a month is on course to pass it.</p>
        )}
        {spend.unpriced > 0 && (
          <p className="note">{plural(spend.unpriced, "run")} on models whose prices models.yaml doesn't give {spend.unpriced === 1 ? "isn't" : "aren't"} in these figures.</p>
        )}
      </div>
    </section>
  );
}

function Instances({ found }: { found: gen.Spending }) {
  const { currency } = found;
  return (
    <section className="card" id="instances" aria-labelledby="instances-title">
      <h2 id="instances-title">Instances</h2>
      {found.instances.length === 0 ? (
        <p className="note">None you may watch spent anything {found.current ? "this month" : "that month"}.</p>
      ) : (
        <Wide label="What each instance spent">
          <table className="figures cost-figures">
            <caption>What each instance you may watch spent {found.current ? "this month, and is on course to" : `in ${named(found.month)}`}</caption>
            <thead>
              <tr>
                <th scope="col">Instance</th>
                <th scope="col">Agent</th>
                <th scope="col" className="num">Spent</th>
                {found.current && <th scope="col" className="num">Forecast</th>}
                <th scope="col" className="num">Runs</th>
                <th scope="col" className="num">Messages answered</th>
                <th scope="col" className="num">Each message</th>
              </tr>
            </thead>
            <tbody>
              {found.instances.map((i) => (
                <tr key={i.key} data-instance={i.key}>
                  <th scope="row"><Link to={{ page: "instance", instance: i.key }}>{i.key}</Link>
                    {i.parts && i.parts.length > 0 && <span className="cost-sub">in {i.parts.join(", ")}</span>}</th>
                  <td>{i.agent}</td>
                  <td className="num">{money(i.spent, currency)}{i.unpriced > 0 && <span className="cost-sub">and {plural(i.unpriced, "run")} unpriced</span>}</td>
                  {found.current && <td className="num">{i.forecast !== null ? money(i.forecast, currency) : ""}</td>}
                  <td className="num">{i.runs.toLocaleString()}</td>
                  <td className="num">{i.answered.toLocaleString()}</td>
                  <td className="num">{i.per_answer !== null ? money(i.per_answer, currency) : "none answered"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Wide>
      )}
    </section>
  );
}

/** The month it is, in UTC, as the core counts months, and the eleven before it. */
function months(): string[] {
  const now = new Date();
  const current = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
  return Array.from({ length: 12 }, (_, n) => moved(current, -n));
}

export function SpendingPage({ month }: { month?: string }) {
  const { data, error } = useLoad(() => get<gen.Spending>(
    `/studio/api/spending${month ? `?month=${encodeURIComponent(month)}` : ""}`), [month]);
  const panels = data ? [...data.parts.map((s) => ["part", s] as const), ...data.agents.map((s) => ["agent", s] as const)] : [];
  const choices = months();
  const shown = data?.month ?? month ?? choices[0];
  return (
    <>
      <PageHead title="Spending"
                about="What agents' model calls cost each month, at the prices models.yaml gives them: each part and agent you may see against the budget the settings set it, with a forecast to the month's end at the last week's pace, and what each message answered cost, all in. A budget guides: it stops no work, which the token budgets each release sets do.">
        <label className="period">In{" "}
          <select id="month" value={shown}
                  onChange={(e) => go(e.target.value === choices[0] ? { page: "spending" } : { page: "spending", month: e.target.value })}>
            {[...new Set([...choices, shown])].map((m) => (
              <option key={m} value={m}>{named(m)}{m === choices[0] ? ", this month" : ""}</option>
            ))}
          </select>
        </label>
      </PageHead>
      {!data && <Waiting error={error} block />}
      {data && panels.length === 0 && (
        <p className="note" id="status" role="status">No part or agent you may see spent anything {data.current ? "this month" : "that month"}, and none has a budget.</p>
      )}
      {data && panels.map(([kind, s]) => <Panel key={`${kind}-${s.key}`} kind={kind} spend={s} found={data} />)}
      {data && <Instances found={data} />}
    </>
  );
}
