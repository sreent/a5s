// The notebook, folded into the studio from its own page (core/notebook_api.py): what agents
// noted from records, on their schedules, for their later runs, each note with the records it
// comes from, for those who keep each instance's notebook, its agent's owners and those who run
// it. They remove any that's no longer worth keeping; a note whose records stop holding it goes
// on its own after 90 days. Notes from records someone may not see stay out of their sight, and
// they're told how many, and who may see them.

import { useState } from "react";
import { get, type Note, type NotebookNow, send } from "../api";
import { Confirm } from "../design";
import { PageHead, useLoad, Waiting } from "../ui";

const listed = (them: string[], last: string) =>
  them.length > 1 ? `${them.slice(0, -1).join(", ")} ${last} ${them[them.length - 1]}` : them[0];

/** A record a note comes from, linked where its system gives it an address on the web. */
function Source({ found }: { found: Note["sources"][number] }) {
  return found.link && /^https:\/\//.test(found.link)
    ? <a href={found.link} rel="noopener noreferrer">{found.key}</a>
    : <span>{found.key}</span>;
}

export function NotebookPage() {
  const [again, setAgain] = useState(0);
  const [status, setStatus] = useState<string>();
  const { data, error } = useLoad(() => get<NotebookNow>("/notebook/api"), [again]);
  const remove = async (note: Note) => {
    try {
      await send("POST", `/notebook/api/${encodeURIComponent(note.entry)}/remove`);
      setStatus(`Removed ${note.entry}.`);
      setAgain((n) => n + 1);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };
  const kept = data ? data.instances.map((id) => data.names[id] || id) : [];
  return (
    <>
      <PageHead title="Notebook"
                about="What your agents noted from records, on their schedules, for their later runs: each note with the records it comes from. Remove any that's no longer worth keeping. A note whose records stop holding it goes on its own after 90 days." />
      <p id="status" role="status" className="note">
        {status ?? (data && data.entries.length === 0 ? `Nothing noted yet by ${listed(kept, "or")}.` : "")}
      </p>
      {!data && <Waiting error={error} />}
      {data && (
        <div id="entries">
          {data.instances.filter((id) => data.entries.some((e) => e.instance === id)).map((id) => (
            <section key={id} className="card" data-instance={id}>
              <h2>Kept by {data.names[id] || id}</h2>
              <ul className="plain">{data.entries.filter((e) => e.instance === id).map((note) => (
                <li key={note.entry} data-entry={note.entry}>
                  <p>{note.text}</p>
                  <p className="note">
                    {note.entry}, from {note.sources.map((s, i) => <span key={s.key}>{i > 0 && ", "}<Source found={s} /></span>)}.
                    Noted on {note.noted}; its records last checked on {note.checked}.
                  </p>
                  <Confirm label="Remove" title={`Remove ${note.entry}?`}
                           about="Its agent no longer has it in its later runs. The ledger keeps that you removed it, by its words' hash."
                           confirm="Remove it" danger onConfirm={() => remove(note)} />
                </li>
              ))}</ul>
            </section>
          ))}
        </div>
      )}
      {data && data.hidden > 0 && (
        <p id="hidden" className="note">
          And {data.hidden} more from records you may not see, which someone who may see them can remove
          {data.others.length ? `: ${listed(data.others, "or")}, who run its instances, may be able to` : ""}.
        </p>
      )}
    </>
  );
}
