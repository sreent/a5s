// a5s's own pieces for agentic work (docs/design.md): a value an agent used, traced to its
// record; a decision someone makes on what an agent asks; an agent's facts, the same for every
// agent; its ladder of autonomy; and a run as time. Their look is the pages' shared one
// (app.css), so a page outside the studio can draw them too.

import * as Popover from "@radix-ui/react-popover";
import type { ReactNode } from "react";
import { Icon } from "../icons";
import type { Tone } from "./controls";
import { Avatar } from "./people";

/** A value an agent used, which opens to show where it comes from: its record, when it was
 * read, by which run and for whom, and whether it still holds. */
export function Traced({ value, trail }: { value: ReactNode; trail: ReactNode[] }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="traced">
        <Icon name="trace" />{value}<span className="hidden"> (where it comes from)</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover" sideOffset={6} align="start" aria-label="Where it comes from">
          <span className="label">Where it comes from</span>
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
        <p className="approval-why"><strong>Why: </strong>{why}</p>
        {decided ? (
          <p className="approval-done" role="status">You {decided} it.</p>
        ) : (
          <div className="approval-actions">
            <button type="button" className="primary" disabled={busy} onClick={onApprove}>Approve</button>
            <button type="button" disabled={busy} onClick={onDecline}>Decline</button>
          </div>
        )}
        <p className="approval-signed"><Icon name="audit" />Your decision is signed and kept in the ledger.</p>
      </div>
    </section>
  );
}

/** An agent's facts, as food carries a label: what it may do, and how it does, per run. */
export function AgentFacts({ name, version, facts, perRun, foot }: {
  name: string; version: string; facts: [string, ReactNode][]; perRun: [string, ReactNode][]; foot?: ReactNode;
}) {
  return (
    <section className="agent-facts" aria-label={`${name}'s facts`}>
      <h3>Agent facts</h3>
      <div className="per"><span>{name}</span><span className="mono">{version}</span></div>
      <div className="rule" />
      <dl>{facts.map(([what, value]) => <Fact key={what} what={what} value={value} />)}</dl>
      <div className="thin" />
      <div className="per"><span>Per run, last 30 days</span><span>median</span></div>
      <dl>{perRun.map(([what, value]) => <Fact key={what} what={what} value={value} />)}</dl>
      {foot && <><div className="thin" /><p className="foot">{foot}</p></>}
    </section>
  );
}

function Fact({ what, value }: { what: string; value: ReactNode }) {
  return <div className="pair"><dt>{what}</dt><dd>{value}</dd></div>;
}

const STEPS = [
  { name: "Suggests", about: "Reads and drafts. A person does the rest." },
  { name: "Asks", about: "Changes wait for a person's yes." },
  { name: "Acts", about: "One type of change on its own, within limits, sampled and graded." },
];

/** Autonomy is earned: the level an agent works at, those its release allows beyond it, and
 * how far it has come toward the next. */
export function AutonomyLadder({ level, max, toward }: {
  level: number; max: number; toward?: { what: string; graded: number; needed: number };
}) {
  return (
    <div>
      <ol className="ladder" aria-label="Autonomy">
        {STEPS.map((step, i) => (
          <li key={step.name} aria-current={i === level ? "step" : undefined}
              className={i > max ? "barred" : i > level ? "beyond" : undefined}>
            <span className="lvl">level {i}{i === level ? " · now" : i > max ? " · not in its release" : ""}</span>
            <strong>{step.name}</strong>
            <p>{step.about}</p>
          </li>
        ))}
      </ol>
      {toward && (
        <>
          <p className="note">{toward.what} toward level {level + 1}: {toward.graded} of {toward.needed} graded
            samples. The part's owner decides.</p>
          <div className="meter" role="meter" aria-label={`${toward.what} toward level ${level + 1}`}
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
