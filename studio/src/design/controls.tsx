// Badges in the colours that mean something; asking before what can't be undone, in the
// browser's own dialog, which keeps focus in it and the page behind out of reach without
// styles of its own, which the pages' policy wouldn't run; and a hint of what something means,
// in Radix's tooltip, which keyboards and screen readers reach as they do the mouse.

import * as Tooltip from "@radix-ui/react-tooltip";
import { type ReactNode, useId, useRef, useState } from "react";
import { t } from "../i18n";

/** What a tool does, and how something stands: the colours a5s gives meaning to. */
export type Tone = "reads" | "writes" | "changes" | "outside" | "own" | "good" | "warn" | "bad" | "idle";

export function Badge({ tone, dot = false, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return <span className={tone ? `badge ${tone}` : "badge"}>{dot && <span className="dot" />}{children}</span>;
}

/** A button that asks first, for what can't be undone. With `typed`, the dialog asks for that
 * word typed, as `ask` says, such as "Type ben to erase it", its field taking the focus, and
 * its confirming answer stays off until the word matches, letter case aside: in the danger
 * colour, for what can't be undone and reaches someone else, whose server checks the word too,
 * so `onConfirm` hears what was typed (Ocean's Confirm). `small` is for a row's own actions. */
export function Confirm({ label, title, about, confirm, danger = false, small = false, typed, ask,
                          onConfirm }: {
  label: string; title: string; about: string; confirm: string; danger?: boolean; small?: boolean;
  typed?: string; ask?: string; onConfirm: (typed: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const aboutId = useId();
  const fieldId = useId();
  const [word, setWord] = useState("");
  const matches = typed === undefined || word.trim().toLowerCase() === typed.trim().toLowerCase();
  const kinds = [danger && "danger", small && "small"].filter(Boolean).join(" ");
  return (
    <>
      <button type="button" className={kinds || undefined} onClick={() => dialog.current?.showModal()}>
        {label}
      </button>
      {/* Escape closes it even when a hint or popover outside it, which a modal dialog leaves out of
          reach, took the key for itself first; and closing it, however, forgets what was typed */}
      <dialog ref={dialog} className="dialog" aria-labelledby={titleId} aria-describedby={aboutId}
              onKeyDown={(event) => { if (event.key === "Escape") dialog.current?.close(); }}
              onClose={() => setWord("")}>
        <h2 id={titleId}>{title}</h2>
        <p id={aboutId}>{about}</p>
        {typed !== undefined && (
          <div className="form-field">
            <label htmlFor={fieldId}>{ask ?? t("Type {word} again", { word: typed })}</label>
            <input id={fieldId} className="mono" autoComplete="off" spellCheck={false} autoFocus value={word}
                   onChange={(event) => setWord(event.target.value)} />
          </div>
        )}
        <div className="dialog-actions">
          <button type="button" autoFocus={typed === undefined} onClick={() => dialog.current?.close()}>{t("Keep it")}</button>
          <button type="button" className={danger ? "danger primary" : "primary"} disabled={!matches}
                  onClick={() => { const said = word.trim(); dialog.current?.close(); onConfirm(said); }}>
            {confirm}
          </button>
        </div>
      </dialog>
    </>
  );
}

/** A word on what something means, for whoever points at it or tabs to it. Its trigger must be
 * something a keyboard reaches, such as a button. */
export function Hint({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Provider delayDuration={250}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content className="hint" sideOffset={6}>{label}</Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
