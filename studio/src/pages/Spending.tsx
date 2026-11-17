// What agents' model calls cost each calendar month (core/spending.py), at the prices models.yaml
// gives them: each part and agent someone may see against the budget the settings set it, as
// Ocean's CostPanel draws cost against plan, the spent, the budget and the forecast to the month's
// end on one scale, each with its figure, and a badge once the forecast passes the budget; with
// what each message answered cost, all in, and the pace of the last week; then each instance they
// may watch, as figures. A budget guides: it stops no work, which the token budgets each release
// sets do.

import { type FormEvent, useEffect, useState } from "react";
import { get } from "../api";
import type * as gen from "../api.gen";
import { locale, t } from "../i18n";
import { Icon } from "../icons";
import { go, Link } from "../router";
import { money, PageHead, plural, useLoad, Waiting, Wide } from "../ui";

type Kind = "part" | "agent";

const monthly = () => new Intl.DateTimeFormat(locale(), { month: "long", year: "numeric", timeZone: "UTC" });
const daily = () => new Intl.DateTimeFormat(locale(), { day: "numeric", month: "long", timeZone: "UTC" });

function named(m: string): string {
  const [y, n] = m.split("-").map(Number);
  return monthly().format(new Date(Date.UTC(y, n - 1, 1)));
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
  const whose = kind === "part" ? spend.key : t("the {agent}", { agent: spend.key });
  const { currency } = found;
  const ends = daily().format(new Date(new Date(found.ends).getTime() - 1));
  const so = found.current ? t("So far") : t("In {month}", { month: named(found.month) });
  const forecast = found.current ? spend.forecast : null;
  const scale = Math.max(spend.spent, spend.budget ?? 0, forecast ?? 0);
  const at = forecast ?? spend.spent;  // what the month comes to, or is on course to
  const over = spend.budget !== null && at > spend.budget ? at - spend.budget : null;
  const end = [
    ...(spend.budget !== null ? [{ name: t("Budget"), amount: spend.budget, fill: "s1" as const,
                                   told: t("Its budget: {amount} a month", { amount: money(spend.budget, currency) }) }] : []),
    ...(forecast !== null ? [{ name: t("Forecast"), amount: forecast, fill: "forecast" as const,
                               told: t("On course for {amount} by {day}, at the last week's pace", { amount: money(forecast, currency), day: ends }) }] : []),
  ];
  return (
    <section className="card cost-box" id={id} aria-labelledby={`${id}-title`} data-over={over !== null}>
      <div className="cost">
        <div className="cost-head">
          <h2 id={`${id}-title`}>{spend.key}</h2>
          <p className="note">{kind === "part" ? t("A part") : t("An agent")} · {found.current
            ? t("as of day {day} of {days}", { day: found.day, days: found.days }) : named(found.month)}</p>
        </div>
        <div className="cost-top">
          <div className="cost-bars">
            <Bars id={`${id}-so-far`} label={so} scale={scale} currency={currency}
                  bars={[{ name: t("Spent"), amount: spend.spent, fill: "s3",
                           told: found.current ? t("Spent {amount} so far this month", { amount: money(spend.spent, currency) })
                             : t("Spent {amount} in {month}", { amount: money(spend.spent, currency), month: named(found.month) }) }]} />
            {end.length > 0 && (
              <Bars id={`${id}-at-end`} label={found.current ? t("By {day}", { day: ends }) : t("Against")} scale={scale}
                    currency={currency} bars={end} />
            )}
            {spend.budget !== null && (
              <div className="cost-over" id={`${id}-against`}>
                {over !== null
                  ? <span className="badge bad"><Icon name="cross" />{t("{amount} over budget", { amount: money(over, currency) })}</span>
                  : <p className="note">{(forecast !== null ? t("{amount} under budget, at this pace", { amount: money(spend.budget - at, currency) })
                    : t("{amount} under budget", { amount: money(spend.budget - at, currency) }))}</p>}
              </div>
            )}
          </div>
          <div className="cost-indices">
            <div className="cost-index" id={`${id}-per-answer`}>
              <p className="label">{t("Each message answered")}</p>
              {spend.per_answer !== null ? (
                <>
                  <strong>{money(spend.per_answer, currency)}</strong>
                  <p>{kind === "part" ? t("All agents' work there cost, reports and chases too, over the {messages} they answered there.", { messages: plural(spend.answered, "message") })
                    : t("All its runs cost, reports and chases too, over the {messages} they answered.", { messages: plural(spend.answered, "message") })}</p>
                </>
              ) : (
                <>
                  <strong>{t("None")}</strong>
                  <p>{spend.answered > 0 ? t("Some runs were on models whose prices models.yaml doesn't give, so a5s doesn't say what each message cost.")
                    : kind === "part" ? (found.current ? t("Agents answered no messages there this month.") : t("Agents answered no messages there that month."))
                    : (found.current ? t("Its runs answered no messages this month.") : t("Its runs answered no messages that month."))}</p>
                </>
              )}
            </div>
            {found.current && spend.pace !== null ? (
              <div className="cost-index" id={`${id}-pace`}>
                <p className="label">{t("A day, lately")}</p>
                <strong>{money(spend.pace, currency)}</strong>
                <p>{t("The last 7 days, on average: the pace the forecast goes on at.")}</p>
              </div>
            ) : (
              <div className="cost-index">
                <p className="label">{t("Runs")}</p>
                <strong>{spend.runs.toLocaleString(locale())}</strong>
                <p>{t("{tokens} tokens.", { tokens: spend.tokens.toLocaleString(locale()) })}</p>
              </div>
            )}
          </div>
        </div>
        {spend.budget === null && (
          <p className="note">{t("The settings set no budget for {whose}. With one, a5s shows each month against it, and tells its owners on their home page once a month is on course to pass it.", { whose })}</p>
        )}
        {spend.unpriced > 0 && (
          <p className="note">{spend.unpriced === 1 ? t("1 run on a model whose prices models.yaml doesn't give isn't in these figures.")
            : t("{runs} on models whose prices models.yaml doesn't give aren't in these figures.", { runs: plural(spend.unpriced, "run") })}</p>
        )}
      </div>
    </section>
  );
}

function Instances({ found }: { found: gen.Spending }) {
  const { currency } = found;
  return (
    <section className="card" id="instances" aria-labelledby="instances-title">
      <h2 id="instances-title">{t("Instances")}</h2>
      {found.instances.length === 0 ? (
        <p className="note">{found.current ? t("None you may watch spent anything this month.") : t("None you may watch spent anything that month.")}</p>
      ) : (
        <>
        <p className="note" id="instances-about">{found.current ? t("What each instance you may watch spent this month, and is on course to")
          : t("What each instance you may watch spent in {month}", { month: named(found.month) })}</p>
        <Wide label={t("What each instance spent")}>
          <table className="figures cost-figures" aria-describedby="instances-about">
            <thead>
              <tr>
                <th scope="col">{t("Instance")}</th>
                <th scope="col">{t("Agent")}</th>
                <th scope="col" className="num">{t("Spent")}</th>
                {found.current && <th scope="col" className="num">{t("Forecast")}</th>}
                <th scope="col" className="num">{t("Runs")}</th>
                <th scope="col" className="num">{t("Messages answered")}</th>
                <th scope="col" className="num">{t("Each message")}</th>
              </tr>
            </thead>
            <tbody>
              {found.instances.map((i) => (
                <tr key={i.key} data-instance={i.key}>
                  <th scope="row"><Link to={{ page: "instance", instance: i.key }}>{i.key}</Link>
                    {i.parts && i.parts.length > 0 && <span className="cost-sub">{t("in {parts}", { parts: i.parts.join(", ") })}</span>}</th>
                  <td>{i.agent}</td>
                  <td className="num">{money(i.spent, currency)}{i.unpriced > 0 && <span className="cost-sub">{t("and {runs} unpriced", { runs: plural(i.unpriced, "run") })}</span>}</td>
                  {found.current && <td className="num">{i.forecast !== null ? money(i.forecast, currency) : ""}</td>}
                  <td className="num">{i.runs.toLocaleString(locale())}</td>
                  <td className="num">{i.answered.toLocaleString(locale())}</td>
                  <td className="num">{i.per_answer !== null ? money(i.per_answer, currency) : i.answered > 0 ? t("not known") : t("none answered")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Wide>
        </>
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

// Whether someone just asked for a month, whose choice takes the keyboard again once its page
// is drawn (round 14, E-L1)
let askedFor = false;

export function SpendingPage({ month }: { month?: string }) {
  const { data, error } = useLoad(() => get<gen.Spending>(
    `/studio/api/spending${month ? `?month=${encodeURIComponent(month)}` : ""}`), [month]);
  const panels = data ? [...data.parts.map((s) => ["part", s] as const), ...data.agents.map((s) => ["agent", s] as const)] : [];
  const choices = months();
  const shown = data?.month ?? month ?? choices[0];
  const [picked, setPicked] = useState(month ?? choices[0]);
  const show = (event: FormEvent) => {  // on Enter or the button: never as the arrow keys step
    event.preventDefault();
    if (picked === (month ?? choices[0])) return;
    askedFor = true;
    go(picked === choices[0] ? { page: "spending" } : { page: "spending", month: picked });
  };
  useEffect(() => {
    if (askedFor) {
      askedFor = false;
      document.getElementById("month")?.focus();
    }
  }, []);
  return (
    <>
      <PageHead title={t("Spending")}
                about={t("What agents' model calls cost each month, at the prices models.yaml gives them: each part and agent you may see against the budget the settings set it, with a forecast to the month's end at the last week's pace, and what each message answered cost, all in. A budget guides: it stops no work, which the token budgets each release sets do.")}>
        <form className="period" onSubmit={show}>
          <label>{t("In")}{" "}
            <select id="month" value={picked} onChange={(e) => setPicked(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") show(e); }}>
              {[...new Set([...choices, shown, picked])].map((m) => (
                <option key={m} value={m}>{m === choices[0] ? t("{month}, this month", { month: named(m) }) : named(m)}</option>
              ))}
            </select>
          </label>
          <button type="submit">{t("Show")}</button>
        </form>
      </PageHead>
      <p className="note" id="utc">{t("Each month runs from midnight UTC on its first day, as the database's clock stamps each run.")}</p>
      {!data && <Waiting error={error} block />}
      {data && !data.compared && (
        <p className="note" id="uncompared" role="status">{t("The budgets are in {theirs}, and models.yaml prices models in {prices}, so a5s compares what's spent with neither: a version of the settings with the budgets in {prices} puts that right.",
          { theirs: data.budget_currency ?? "", prices: data.currency ?? t("no currency it names") })}</p>
      )}
      {data && panels.length === 0 && (
        <p className="note" id="status" role="status">{data.current ? t("No part or agent you may see spent anything this month, and none has a budget.")
          : t("No part or agent you may see spent anything that month, and none has a budget.")}</p>
      )}
      {data && panels.map(([kind, s]) => <Panel key={`${kind}-${s.key}`} kind={kind} spend={s} found={data} />)}
      {data && <Instances found={data} />}
    </>
  );
}
