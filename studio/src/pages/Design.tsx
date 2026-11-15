// The design system's living showcase (docs/design.md): Ocean's colours as they are, its type,
// and each piece pages are made of, as pages use it, with the sample's people and agents. The
// browser tests open it in light and dark and check it with axe.

import { useEffect, useState } from "react";
import { AgentFacts, ApprovalCard, AutonomyLadder, Badge, Confirm, Hint, RunTimeline, Traced, Who }
  from "../design";
import { PageHead } from "../ui";

const MEANINGS = [
  ["page", "the page"], ["surface", "cards"], ["sunken", "wells"], ["line", "lines"], ["text", "text"],
  ["muted", "quieter text"], ["faint", "labels"], ["accent", "what you can do"], ["accent-soft", "chosen"],
  ["agent-tone", "agents"], ["reads", "reads"], ["writes", "writes"], ["changes", "changes a record"],
  ["outside", "outside"], ["own", "a5s's own"], ["good", "going well"], ["warn", "waiting"],
  ["bad", "failed"], ["idle", "paused"],
] as const;

function Swatches() {
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => {
    const read = () => {
      const css = getComputedStyle(document.documentElement);
      setValues(Object.fromEntries(MEANINGS.map(([name]) => [name, css.getPropertyValue(`--${name}`).trim()])));
    };
    read();
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", read);
    return () => scheme.removeEventListener("change", read);
  }, []);
  return (
    <ul className="swatches">
      {MEANINGS.map(([name, what]) => (
        <li key={name}>
          <span className="swatch" style={{ background: `var(--${name})` }} />
          <span><code>--{name}</code> {what}<span className="faint"> {values[name]}</span></span>
        </li>
      ))}
    </ul>
  );
}

export function DesignPage() {
  const [decided, setDecided] = useState<"approved" | "declined">();
  const [removed, setRemoved] = useState(false);
  return (
    <>
      <PageHead title="Design" about="Ocean: the look every page of a5s shares, and the pieces its pages are made
        of, each as pages use it. Colour means something here: what a tool does, how something stands, and
        whether a person or an agent did it." />

      <section className="card wide" data-piece="colours">
        <h2>Colours</h2>
        <p className="note">What each colour is for, in light or dark as your device is. Pages name these, never a
          colour of their own.</p>
        <Swatches />
      </section>

      <section className="card wide" data-piece="type">
        <h2>Type</h2>
        <p className="type-sample big">Waiting on you</p>
        <p className="type-sample">Changes to records wait for a person to decide at level 1.</p>
        <p className="type-sample mono">0.1.0+f0a5fd78a056 · run r-8f3a2c</p>
      </section>

      <div className="two-up">
        <section className="card" data-piece="buttons">
          <h2>Buttons and badges</h2>
          <div className="chips">
            <button type="button" className="primary">Approve</button>
            <button type="button">Ask why</button>
            <button type="button" className="link">Open the run</button>
          </div>
          <p className="label">What a tool does</p>
          <div className="chips">
            <Badge tone="reads">reads</Badge><Badge tone="writes">writes</Badge>
            <Badge tone="changes">changes</Badge><Badge tone="outside">outside</Badge>
            <Badge tone="own">a5s's own</Badge>
            <Hint label="Coral always means a change to a record; amber, something written, such as a draft.">
              <button type="button" className="link">What do these mean?</button>
            </Hint>
          </div>
          <p className="label">How it stands</p>
          <div className="chips">
            <Badge tone="good" dot>active</Badge><Badge tone="warn" dot>waiting on you</Badge>
            <Badge tone="bad" dot>failed</Badge><Badge tone="idle" dot>paused</Badge>
          </div>
        </section>

        <section className="card" data-piece="people">
          <h2>People and agents</h2>
          <p className="note">People are round and agents are rounded squares in the agent colour, wherever they
            appear, so who did what reads at a glance.</p>
          <div className="chips">
            <Who name="Priya Nair" kind="person" about="owns 2 agents" />
            <Who name="assistant" kind="agent" about="works in billing" />
            <Who name="watcher" kind="agent" about="level 0" />
          </div>
          <p className="label">A value, traced to its record</p>
          <p data-piece="traced">The due date it read: <Traced value="15 Nov" trail={[
            <><strong>Q-1001</strong>, in billing, as its system holds it</>,
            <>Read at 14:02 by run <code>r-8f3a2c</code>, for Ben Okafor</>,
            <>Unchanged since: checked again before the reply</>]} /></p>
        </section>
      </div>

      <div className="two-up">
        <section className="card" data-piece="approval">
          <h2>A decision</h2>
          <ApprovalCard agent="assistant" asks="asks to change a due date"
            about="for Ben Okafor · billing · 2 minutes ago"
            changes={[{ what: "Question", to: "Q-1001" }, { what: "Due", from: "15 Nov", to: "30 Nov" }]}
            why="the customer asked in chat on 12 Nov, and billing allows one extension of up to 30 days."
            decided={decided} onApprove={() => setDecided("approved")} onDecline={() => setDecided("declined")} />
        </section>

        <section className="card" data-piece="facts">
          <h2>Agent facts</h2>
          <AgentFacts name="assistant" version="0.1.0"
            facts={[["Works for", "billing, 2 people"], ["Autonomy", "level 1: changes wait for a yes"],
              ["Reads", "records, messages"], ["Writes", "drafts"], ["Changes", "due dates, with a yes"],
              ["Outside content", "none"], ["Data", "personal"]]}
            perRun={[["Model calls", "3"], ["Tokens", "4.2k, 61% cached"], ["Cost", "$0.002"],
              ["Graded samples", "48, 96% right"]]}
            foot="Owned by Priya Nair. Sample figures." />
        </section>
      </div>

      <div className="two-up">
        <section className="card" data-piece="ladder">
          <h2>Autonomy, earned</h2>
          <AutonomyLadder level={1} max={2} toward={{ what: "Due-date changes", graded: 36, needed: 50 }} />
        </section>

        <section className="card" data-piece="timeline">
          <h2>A run, as time</h2>
          <RunTimeline steps={[
            { at: "14:02:01", tone: "idle", what: <>Ben Okafor: <q>Can we give them until the end of the month?</q></> },
            { at: "14:02:03", tone: "reads", what: <><code>get_record</code> Q-1001</>, detail: "reads · 120 ms" },
            { at: "14:02:04", tone: "reads", what: <><code>search_records</code> extension policy</>, detail: "reads · 340 ms" },
            { at: "14:02:06", tone: "changes", what: <><code>change_due_date</code> held for a yes</>,
              detail: "changes · waiting on Ana Ortiz" },
            { at: "14:05:40", tone: "good", what: "Ana Ortiz approved; the change was made", detail: "signed · in the ledger" },
          ]} />
        </section>
      </div>

      <section className="card wide" data-piece="confirm">
        <h2>Asking first</h2>
        <p className="note">For what can't be undone, a page asks first, and says what will happen.</p>
        {removed ? <p role="status">The draft is gone.</p> : (
          <Confirm label="Delete this draft" title="Delete the draft of scout?"
            about="Its folder and its test cases go with it, and nobody can bring them back." confirm="Delete it"
            danger onConfirm={() => setRemoved(true)} />
        )}
      </section>
    </>
  );
}
