// An instance's runs, day by day in the viewer's own time zone, each day's column split by how
// its runs ended: done, cut short, failed, or still running. The status colours never say
// it alone: the legend names each, each day gives its figures on hover and on focus, and a
// table below gives them all.

import { type KeyboardEvent, useLayoutEffect, useRef, useState } from "react";
import type { Day } from "./api";
import { FAILED_OUTCOMES, plural } from "./ui";

export const ENDINGS = [
  { key: "done", name: "Done" },
  { key: "short", name: "Cut short" },
  { key: "failed", name: "Failed" },
  { key: "open", name: "Still running" },
] as const;
type Ending = (typeof ENDINGS)[number]["key"];

export function ending(outcome: string): Ending {
  if (outcome === "done") return "done";
  if (outcome === "open") return "open";
  return FAILED_OUTCOMES.includes(outcome) ? "failed" : "short";
}

function split(day: Day): Record<Ending, number> {
  const found: Record<Ending, number> = { done: 0, short: 0, failed: 0, open: 0 };
  for (const [outcome, runs] of Object.entries(day.ended)) found[ending(outcome)] += runs;
  return found;
}

const PLOT = 168;  // the plot's height, in pixels
const AXIS = 24;   // the band below it for the days
const LEFT = 36;   // the band beside it for the counts
const TOP = 16;    // room above the tallest column for its figure
const BAR = 24;    // the widest a column gets: the rest of its slot is air
const GAP = 2;     // the surface between touching marks
const ROUND = 4;   // the rounding of a column's end; its foot stays square
const TIP = 176;   // the tooltip's width

const SHORT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
const LONG = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric",
                                                  timeZone: "UTC" });
const date = (day: string) => new Date(`${day}T00:00:00Z`);  // a day, already in their zone

/** The counts up the side: whole runs, in steps of 1, 2 or 5 times a power of ten. */
export function steps(most: number): number[] {
  const rough = Math.max(1, most) / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? 10 * power);
  const top = Math.max(step, Math.ceil(most / step) * step);
  return Array.from({ length: top / step + 1 }, (_, i) => i * step);
}

function capped(x: number, y: number, w: number, h: number): string {
  const r = Math.min(ROUND, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function said(day: Day, parts: Record<Ending, number>): string {
  const how = ENDINGS.filter((e) => parts[e.key] > 0).map((e) => `${parts[e.key]} ${e.name.toLowerCase()}`);
  return `${LONG.format(date(day.day))}: ${plural(day.runs, "run")}${how.length ? `, ${how.join(", ")}` : ""}`;
}

export function RunsByDay({ days, zone }: { days: Day[]; zone: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [on, setOn] = useState<number | null>(null);  // the day hovered or focused
  const [here, setHere] = useState(days.length - 1);  // the day the keyboard is on
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const seen = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.floor(entry.contentRect.width))));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  const parts = days.map(split);
  const totals = ENDINGS.map((e) => parts.reduce((n, p) => n + p[e.key], 0));
  const most = Math.max(0, ...days.map((d) => d.runs));
  const ticks = steps(most);
  const top = ticks[ticks.length - 1];
  const band = (width - LEFT - 4) / Math.max(1, days.length);
  const bar = Math.max(2, Math.min(BAR, band - GAP));
  const y = (n: number) => TOP + PLOT - (n / top) * PLOT;
  const centre = (i: number) => LEFT + (i + 0.5) * band;
  const every = Math.max(1, Math.ceil(60 / band));  // a day's name every so many columns, so none touch
  const tallest = days.findIndex((d) => d.runs === most);
  const move = (event: KeyboardEvent<SVGGElement>, i: number) => {
    const to = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: days.length - 1 }[event.key];
    if (to === undefined || to < 0 || to >= days.length) return;
    event.preventDefault();
    setHere(to);
    (box.current?.querySelectorAll<SVGGElement>(".day")[to])?.focus();
  };
  return (
    <div className="runs-chart" ref={box}>
      {most === 0 ? <p className="note">No runs in this period.</p> : (
        <>
          <ul className="legend" aria-label="How runs ended">
            {ENDINGS.filter((_, k) => totals[k] > 0).map((e) => (
              <li key={e.key}><span className={`swatch ${e.key}`} />{e.name}</li>
            ))}
          </ul>
          <svg width={width} height={TOP + PLOT + AXIS} role="group"
               aria-label={`Runs by day over ${plural(days.length, "day")}, in ${zone}`}>
            {ticks.map((t) => (
              <g key={t}>
                <line className={t === 0 ? "baseline" : "grid"} x1={LEFT} x2={width - 4} y1={y(t)} y2={y(t)} />
                <text className="tick" x={LEFT - 8} y={y(t)} dy="0.32em" textAnchor="end">{t.toLocaleString()}</text>
              </g>
            ))}
            {days.map((day, i) => {
              const x = centre(i) - bar / 2;
              const shown = ENDINGS.filter((e) => parts[i][e.key] > 0);
              let base = TOP + PLOT;
              const marks = shown.map((e, j) => {
                const h = (parts[i][e.key] / top) * PLOT;
                const from = base - h;
                base = from;
                const painted = Math.max(1.5, h - (j > 0 ? GAP : 0));  // the surface shows below each but the lowest
                return j === shown.length - 1
                  ? <path key={e.key} className={`mark ${e.key}`} d={capped(x, from, bar, painted)} />
                  : <rect key={e.key} className={`mark ${e.key}`} x={x} y={from} width={bar} height={painted} />;
              });
              return (
                <g key={day.day} className="day" tabIndex={i === here ? 0 : -1} role="img" aria-label={said(day, parts[i])}
                   onPointerEnter={() => setOn(i)} onPointerLeave={() => setOn(null)}
                   onFocus={() => { setOn(i); setHere(i); }} onBlur={() => setOn(null)}
                   onKeyDown={(event) => move(event, i)}>
                  <rect className="hit" x={LEFT + i * band} y={TOP - 4} width={band} height={PLOT + 4} />
                  {marks}
                </g>
              );
            })}
            {tallest >= 0 && (
              <text className="figure" x={centre(tallest)} y={y(most) - 5} textAnchor="middle">{most.toLocaleString()}</text>
            )}
            {days.map((day, i) => (days.length - 1 - i) % every === 0 && (
              <text key={day.day} className="tick" y={TOP + PLOT + 16}
                    x={band < 60 && i === days.length - 1 ? width - 4 : band < 60 && i === 0 ? LEFT : centre(i)}
                    textAnchor={band < 60 && i === days.length - 1 ? "end" : band < 60 && i === 0 ? "start" : "middle"}>
                {SHORT.format(date(day.day))}
              </text>
            ))}
          </svg>
          {on !== null && (
            <div className="tip" style={{ left: Math.max(0, centre(on) + 12 + TIP <= width  // beside it, not on it
                                                           ? centre(on) + 12 : centre(on) - 12 - TIP) }}>
              <div className="tip-head">{LONG.format(date(days[on].day))}</div>
              <div className="tip-row"><strong>{days[on].runs.toLocaleString()}</strong>{days[on].runs === 1 ? "run" : "runs"}</div>
              {ENDINGS.filter((e) => parts[on][e.key] > 0).map((e) => (
                <div key={e.key} className="tip-row">
                  <span className={`line-key ${e.key}`} /><strong>{parts[on][e.key].toLocaleString()}</strong>{e.name.toLowerCase()}
                </div>
              ))}
            </div>
          )}
          <details className="as-table">
            <summary>The same, as a table</summary>
            <table className="grid-table compact">
              <thead>
                <tr><th>Day</th>{ENDINGS.map((e) => <th key={e.key} className="num">{e.name}</th>)}<th className="num">All</th></tr>
              </thead>
              <tbody>
                {days.map((day, i) => day.runs > 0 && (
                  <tr key={day.day}>
                    <td>{LONG.format(date(day.day))}</td>
                    {ENDINGS.map((e) => <td key={e.key} className="num">{parts[i][e.key]}</td>)}
                    <td className="num">{day.runs}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note">Days in {zone}. Days with no runs are left out.</p>
          </details>
        </>
      )}
    </div>
  );
}
