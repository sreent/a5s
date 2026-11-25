// The notebook, folded into the studio from its own page (core/notebook_api.py): what agents
// noted from records, on their schedules, for their later runs, each note with the records it
// comes from, for those who keep each instance's notebook, its agent's owners and those who run
// it. They remove any that's no longer worth keeping; a note goes once its records change, as
// a5s reads them again each day. Notes from records someone may not see stay out of their sight, and
// they're told how many, and who may see them.

import { useState } from "react";
import { get, type Note, type NotebookNow, send } from "../api";
import { Confirm, useToast } from "../design";
import { t } from "../i18n";
import { PageHead, plural, useLoad, Waiting } from "../ui";

const listed = (them: string[], last: string) =>
  them.length > 1 ? `${them.slice(0, -1).join(", ")} ${last} ${them[them.length - 1]}` : them[0];

/** A record a note comes from, linked where its system gives it an address on the web. */
function Source({ found }: { found: Note["sources"][number] }) {
  return found.link && /^https:\/\//.test(found.link)
    ? <a href={found.link} rel="noopener noreferrer">{found.key}</a>
    : <span>{found.key}</span>;
}

export function NotebookPage() {
  const toast = useToast();
  const [status, setStatus] = useState<string>();
  const { data, error, reload } = useLoad(() => get<NotebookNow>("/notebook/api"), []);
  const remove = async (note: Note) => {
    try {
      await send("POST", `/notebook/api/${encodeURIComponent(note.entry)}/remove`);
      await reload();  // it says so with the note gone from sight
      setStatus(t("Removed {entry}.", { entry: note.entry }));
      toast(t("Removed {entry} from the notebook.", { entry: note.entry }));
    } catch (e) {
      setStatus((e as Error).message);
    }
  };
  const kept = data ? data.instances.map((id) => data.names[id] || id) : [];
  return (
    <>
      <PageHead title={t("Notebook")}
                about={t("What your agents noted from records, on their schedules, for their later runs: each note with the records it comes from. Remove any that's no longer worth keeping. A note goes once its records change: a5s reads them again each day.")} />
      <p id="status" role="status" className="note">
        {status ?? (data && data.entries.length === 0 ? t("Nothing noted yet by {whom}.", { whom: listed(kept, t("or")) }) : "")}
      </p>
      {!data && <Waiting error={error} />}
      {data && (
        <div id="entries">
          {data.instances.filter((id) => data.entries.some((e) => e.instance === id)).map((id) => (
            <section key={id} className="card" data-instance={id}>
              <h2>{t("Kept by {whom}", { whom: data.names[id] || id })}</h2>
              <ul className="plain">{data.entries.filter((e) => e.instance === id).map((note) => (
                <li key={note.entry} data-entry={note.entry}>
                  <p>{note.text}</p>
                  <p className="note">
                    {t("{entry}, from", { entry: note.entry })} {note.sources.map((s, i) => <span key={s.key}>{i > 0 && ", "}<Source found={s} /></span>)}
                    {t(". Noted on {noted}; its records last checked on {checked}.", { noted: note.noted, checked: note.checked })}
                  </p>
                  <Confirm label={t("Remove")} title={t("Remove {entry}?", { entry: note.entry })}
                           about={t("Its agent no longer has it in its later runs. The ledger keeps that you removed it, by its words' hash.")}
                           confirm={t("Remove it")} danger onConfirm={() => remove(note)} />
                </li>
              ))}</ul>
            </section>
          ))}
        </div>
      )}
      {data && data.hidden > 0 && (
        <p id="hidden" className="note">
          {data.others.length
            ? t("And {more} from records you may not see, which someone who may see them can remove: {others}, who run its instances, may be able to.",
                { more: plural(data.hidden, "more", "more"), others: listed(data.others, t("or")) })
            : t("And {more} from records you may not see, which someone who may see them can remove.",
                { more: plural(data.hidden, "more", "more") })}
        </p>
      )}
    </>
  );
}
