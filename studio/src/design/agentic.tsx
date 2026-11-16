// a5s's own pieces for agentic work (docs/design.md): a value an agent used, traced to its
// record; a decision someone makes on what an agent asks; an agent's facts, the same for every
// agent; its ladder of autonomy; a run as time; and the way from a draft to an agent at work.
// Their look is the pages' shared one (app.css), so a page outside the studio can draw them too.

import * as Popover from "@radix-ui/react-popover";
import type { ReactNode } from "react";
import { t } from "../i18n";
import { Icon } from "../icons";
import type { Tone } from "./controls";
import { Avatar } from "./people";

/** A value an agent used, which opens to show where it comes from: its record, when it was
 * read, by which run and for whom, and whether it still holds. */
export function Traced({ value, trail }: { value: ReactNode; trail: ReactNode[] }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="traced">
        <Icon name="trace" />{value}<span className="hidden"> {t("(where it comes from)")}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover" sideOffset={6} align="start" aria-label={t("Where it comes from")}>
          <span className="label">{t("Where it comes from")}</span>
          <ol className="trail">{trail.map((step, i) => <li key={i}><span>{step}</span></li>)}</ol>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** A line of what a decision changes: from what to what, or, with no `from`, what it's about. */
export type Change = { what: string; from?: ReactNode; to: ReactNode };

/** What an agent asks someone to decide, a phone's width at most: what it changes, why, and
 * their yes or no, which a5s signs and keeps in the ledger. Once decided, it says so. */
export function ApprovalCard({ agent, asks, about, changes, why, tone = "changes", decided, busy = false,
  onApprove, onDecline }: {
  agent: string; asks: string; about?: string; changes: Change[]; why: ReactNode;
  tone?: Extract<Tone, "changes" | "writes" | "outside">; decided?: "approved" | "declined";
  busy?: boolean; onApprove: () => void; onDecline: () => void;
}) {
  return (
    <section className="approval" aria-label={`${agent} ${asks}`}>
      <div className={`approval-stripe ${tone}`} />
      <div className="approval-body">
        <div className="who">
          <Avatar name={agent} kind="agent" />
          <span>
            <h3 className="approval-title">{agent} {asks}</h3>
            {about && <span className="who-about">{about}</span>}
          </span>
        </div>
        <dl className="approval-changes">
          {changes.map((change) => (
            <div key={change.what} className="pair">
              <dt>{change.what}</dt>
              <dd>{change.from === undefined ? change.to  /* what it's about, which stays */
                : <><del>{change.from}</del> → <ins>{change.to}</ins></>}</dd>
            </div>
          ))}
        </dl>
        <p className="approval-why"><strong>{t("Why:")} </strong>{why}</p>
        {decided ? (
          <p className="approval-done" role="status">{decided === "approved" ? t("You approved it.") : t("You declined it.")}</p>
        ) : (
          <div className="approval-actions">
            <button type="button" className="primary" disabled={busy} onClick={onApprove}>{t("Approve")}</button>
            <button type="button" disabled={busy} onClick={onDecline}>{t("Decline")}</button>
          </div>
        )}
        <p className="approval-signed"><Icon name="audit" />{t("Your decision is signed and kept in the ledger.")}</p>
      </div>
    </section>
  );
}

/** A part of an agent's label below its facts, such as how it does per run, or what it may
 * spend: a title, a word beside it, and its lines. */
export type FactsPart = { title: string; aside?: string; rows: [string, ReactNode][] };

/** An agent's facts, as food carries a label, the same for every agent: what it may do, then
 * a part such as how it does per run. */
export function AgentFacts({ name, version, facts, more, foot }: {
  name: string; version: string; facts: [string, ReactNode][]; more?: FactsPart; foot?: ReactNode;
}) {
  return (
    <section className="agent-facts" aria-label={t("{name}'s facts", { name })}>
      <h3>{t("Agent facts")}</h3>
      <div className="per"><span>{name}</span><span className="mono">{version}</span></div>
      <div className="rule" />
      <dl>{facts.map(([what, value]) => <Fact key={what} what={what} value={value} />)}</dl>
      {more && (
        <>
          <div className="thin" />
          <div className="per"><span>{more.title}</span><span>{more.aside}</span></div>
          <dl>{more.rows.map(([what, value]) => <Fact key={what} what={what} value={value} />)}</dl>
        </>
      )}
      {foot && <><div className="thin" /><p className="foot">{foot}</p></>}
    </section>
  );
}

function Fact({ what, value }: { what: string; value: ReactNode }) {
  return <div className="pair"><dt>{what}</dt><dd>{value}</dd></div>;
}

// The ladder's rungs, in the language spoken when they're drawn
const steps = () => [
  { name: t("Suggests"), about: t("Reads and drafts. A person does the rest.") },
  { name: t("Asks"), about: t("Changes wait for a person's yes.") },
  { name: t("Acts"), about: t("One type of change on its own, within limits, sampled and graded.") },
];

/** A level's rung in words: Suggests, Asks or Acts. */
export function rung(level: number): string {
  const rungs = steps();
  return rungs[Math.max(0, Math.min(level, rungs.length - 1))].name;
}

/** Autonomy is earned: the level an agent works at, those its release allows beyond it, and
 * how far it has come toward the next. */
export function AutonomyLadder({ level, max, toward }: {
  level: number; max: number; toward?: { what: string; graded: number; needed: number };
}) {
  return (
    <div className="ladder-box">
      <ol className="ladder" aria-label={t("Autonomy")}>
        {steps().map((step, i) => (
          <li key={step.name} aria-current={i === level ? "step" : undefined}
              className={i > max ? "barred" : i > level ? "beyond" : undefined}>
            <span className="lvl">{i === level ? t("level {n} · now", { n: i })
              : i > max ? t("level {n} · not in its release", { n: i }) : t("level {n}", { n: i })}</span>
            <strong>{step.name}</strong>
            <p>{step.about}</p>
          </li>
        ))}
      </ol>
      {toward && (
        <>
          <p className="note">{t("{what} toward level {level}: {graded} of {needed} graded samples. The part's owner decides.",
            { what: toward.what, level: level + 1, graded: toward.graded, needed: toward.needed })}</p>
          <div className="meter" role="meter" aria-label={t("{what} toward level {level}", { what: toward.what, level: level + 1 })}
               aria-valuemin={0} aria-valuemax={toward.needed} aria-valuenow={toward.graded}>
            <span style={{ width: `${Math.min(100, (100 * toward.graded) / toward.needed)}%` }} />
          </div>
        </>
      )}
    </div>
  );
}

export type Step = { at: string; tone: Tone; what: ReactNode; detail?: ReactNode };

/** A run as time: each step in order, in the colour of what it did. */
export function RunTimeline({ steps }: { steps: Step[] }) {
  return (
    <ol className="timeline">
      {steps.map((step, i) => (
        <li key={i}>
          <time>{step.at}</time>
          <span className={`node tone-${step.tone}`} aria-hidden="true" />
          <span>{step.what}{step.detail && <span className="step-detail">{step.detail}</span>}</span>
        </li>
      ))}
    </ol>
  );
}

/** A stage on the way from a draft to an agent at work: done, the one to do now, or later. */
export type Stage = { name: string; about: ReactNode; state: "done" | "now" | "later" };

// What a screen reader hears after a stage's name, in the language spoken when it's drawn
const states = (): Record<Stage["state"], string> => ({ done: t(", done"), now: t(", to do now"), later: "" });

/** The way from a draft to an agent at work, as a path: what's done, the one thing to do now,
 * and what follows it, with who does each. */
export function JourneyPath({ stages, next, label = t("From a draft to an agent at work") }: {
  stages: Stage[]; next?: ReactNode; label?: string;
}) {
  const said = states();
  return (
    <div className="journey-box">
      <ol className="journey" aria-label={label}>
        {stages.map((stage, i) => (
          <li key={stage.name} className={stage.state} aria-current={stage.state === "now" ? "step" : undefined}>
            <span className="journey-mark" aria-hidden="true">
              {stage.state === "done" ? <Icon name="check" /> : i + 1}
            </span>
            <span>
              <strong>{stage.name}</strong><span className="hidden">{said[stage.state]}</span>
              <span className="journey-about">{stage.about}</span>
            </span>
          </li>
        ))}
      </ol>
      {next && <div className="journey-next">{next}</div>}
    </div>
  );
}
