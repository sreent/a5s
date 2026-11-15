// Badges in the colours that mean something; asking before what can't be undone, in the
// browser's own dialog, which keeps focus in it and the page behind out of reach without
// styles of its own, which the pages' policy wouldn't run; and a hint of what something means,
// in Radix's tooltip, which keyboards and screen readers reach as they do the mouse.

import * as Tooltip from "@radix-ui/react-tooltip";
import { type ReactNode, useId, useRef } from "react";

/** What a tool does, and how something stands: the colours a5s gives meaning to. */
export type Tone = "reads" | "writes" | "changes" | "outside" | "own" | "good" | "warn" | "bad" | "idle";

export function Badge({ tone, dot = false, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return <span className={tone ? `badge ${tone}` : "badge"}>{dot && <span className="dot" />}{children}</span>;
}

/** A button that asks first, for what can't be undone. */
export function Confirm({ label, title, about, confirm, danger = false, onConfirm }:
  { label: string; title: string; about: string; confirm: string; danger?: boolean; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const aboutId = useId();
  return (
    <>
      <button type="button" className={danger ? "danger" : undefined} onClick={() => dialog.current?.showModal()}>
        {label}
      </button>
      {/* Escape closes it even when a hint or popover outside it, which a modal dialog leaves out of
          reach, took the key for itself first */}
      <dialog ref={dialog} className="dialog" aria-labelledby={titleId} aria-describedby={aboutId}
              onKeyDown={(event) => { if (event.key === "Escape") dialog.current?.close(); }}>
        <h2 id={titleId}>{title}</h2>
        <p id={aboutId}>{about}</p>
        <div className="dialog-actions">
          <button type="button" autoFocus onClick={() => dialog.current?.close()}>Keep it</button>
          <button type="button" className={danger ? "danger primary" : "primary"}
                  onClick={() => { onConfirm(); dialog.current?.close(); }}>
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
