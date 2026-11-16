// Loading and afterwards, as Ocean draws them (components/Skeleton, components/Toast): what's
// loading, in the shape it will have, still; and what was just done, said once at the foot of the
// window, beside the page's own status line, with Undo while it can still be undone.

import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Icon } from "../icons";

type Shaped = { lines?: number; title?: boolean; rows?: number; columns?: number; block?: boolean };

/** The shapes of what's loading, hidden from screen readers: a title and lines, a table's rows,
 * or a block for a chart or a canvas. */
export function Shapes({ lines = 3, title = true, rows, columns = 3, block = false }: Shaped) {
  return (
    <div className="skeleton" aria-hidden="true">
      {title && <div className="skeleton-title" />}
      {rows ? Array.from({ length: rows }, (_, row) => (
        <div key={row} className="skeleton-row">{Array.from({ length: columns }, (_, cell) => <div key={cell} />)}</div>
      )) : block ? <div className="skeleton-block" /> : Array.from({ length: lines }, (_, line) => <div key={line} className="skeleton-line" />)}
    </div>
  );
}

/** A region that's loading, laid out as what it loads will be, such as a grid of cards or a
 * row of figures, each of Shapes: it says it's busy, and "Loading…" in words for screen
 * readers, and its layout is hidden from them with its shapes. */
export function Loading({ children }: { children: ReactNode }) {
  return (
    <div aria-busy="true">
      <p className="skeleton-words" role="status">Loading…</p>
      <div aria-hidden="true">{children}</div>
    </div>
  );
}

/** What's loading, in the shape it will have: a card's title and lines, a table's rows, or a
 * block for a chart. The region says it's busy, and "Loading…" in words for screen readers; on
 * a card of its own, or `bare` inside one that's already there. */
export function Skeleton({ bare = false, ...shaped }: Shaped & { bare?: boolean }) {
  const shapes = <><p className="skeleton-words" role="status">Loading…</p><Shapes {...shaped} /></>;
  return bare ? <div aria-busy="true">{shapes}</div> : <section className="card" aria-busy="true">{shapes}</section>;
}

type Toast = { id: number; words: string; undo?: () => void };
type Say = (words: string, undo?: () => void) => void;

const Told = createContext<Say>(() => {});

/** Say what was just done in a toast, as well as in the page's own status line. */
export function useToast(): Say {
  return useContext(Told);
}

const STAYS = 6000;  // ms, and for as long as the pointer or the focus is on it
const MOST = 3;

function One({ toast, gone }: { toast: Toast; gone: (id: number) => void }) {
  const held = useRef(false);
  useEffect(() => {
    let left = STAYS;
    const tick = window.setInterval(() => {
      if (!held.current && (left -= 250) <= 0) gone(toast.id);
    }, 250);
    return () => window.clearInterval(tick);
  }, [toast.id, gone]);
  const hold = (on: boolean) => () => { held.current = on; };
  return (
    <div className="toast" onPointerEnter={hold(true)} onPointerLeave={hold(false)} onFocus={hold(true)} onBlur={hold(false)}>
      <Icon name="check" />
      <p className="toast-words">{toast.words}</p>
      {toast.undo && (
        <button type="button" className="small" onClick={() => { toast.undo?.(); gone(toast.id); }}>Undo</button>
      )}
      <button type="button" aria-label="Dismiss" onClick={() => gone(toast.id)}><Icon name="cross" /></button>
    </div>
  );
}

/** The toasts, at the foot of the window, for every page the frame holds. */
export function Toasts({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const say = useCallback<Say>((words, undo) => {
    setToasts((was) => [...was, { id: next.current++, words, undo }].slice(-MOST));
  }, []);
  const gone = useCallback((id: number) => setToasts((was) => was.filter((t) => t.id !== id)), []);
  return (
    <Told.Provider value={say}>
      {children}
      <div className="toasts" role="status" id="toasts">
        {toasts.map((toast) => <One key={toast.id} toast={toast} gone={gone} />)}
      </div>
    </Told.Provider>
  );
}
