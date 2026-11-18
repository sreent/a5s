// The palette, as Ocean draws it (components/Palette): going anywhere a person may, by name, from
// any page. The browser's own dialog, a combobox over a listbox: what it found, grouped, the arrows
// choosing, Enter opening, Escape closing with the focus back where it was.

import { t } from "../i18n";
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { Icon } from "../icons";

export type PaletteOption = { id: string; name: string; where: string; group: string; icon: string };

export function Palette({ open, onClose, query, onQuery, options, onChoose, looking = false }: {
  open: boolean; onClose: () => void; query: string; onQuery: (query: string) => void;
  options: PaletteOption[]; onChoose: (option: PaletteOption) => void; looking?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useId();
  const [at, setAt] = useState(0);
  useEffect(() => {
    const shown = dialog.current;
    if (!shown) return;
    if (open && !shown.open) shown.showModal();
    if (!open && shown.open) shown.close();
  }, [open]);
  useEffect(() => setAt(0), [query, options]);
  const chosen = options.length ? Math.min(at, options.length - 1) : -1;
  const optionId = (n: number) => `${list}-o${n}`;
  useEffect(() => {
    if (chosen >= 0) document.getElementById(optionId(chosen))?.scrollIntoView({ block: "nearest" });
  });  // eslint-disable-line react-hooks/exhaustive-deps

  const keys = (event: KeyboardEvent<HTMLInputElement>) => {
    const last = options.length - 1;
    const to: Record<string, number> = { ArrowDown: chosen + 1 > last ? 0 : chosen + 1, ArrowUp: chosen - 1 < 0 ? last : chosen - 1,
                                         Home: 0, End: last };
    if (event.key in to && options.length) {
      event.preventDefault();
      setAt(to[event.key]);
    } else if (event.key === "Enter" && chosen >= 0) {
      event.preventDefault();
      onChoose(options[chosen]);
    }
  };

  // the groups, in the order the options come in
  const groups: { name: string; options: [PaletteOption, number][] }[] = [];
  options.forEach((option, n) => {
    const last = groups[groups.length - 1];
    if (last && last.name === option.group) last.options.push([option, n]);
    else groups.push({ name: option.group, options: [[option, n]] });
  });
  return (
    <dialog ref={dialog} className="dialog palette" aria-label={t("Find anything")} onClose={onClose}
            onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <div className="palette-find">
        <Icon name="find" />
        <input role="combobox" aria-expanded="true" aria-controls={list} aria-autocomplete="list"
               aria-activedescendant={chosen >= 0 ? optionId(chosen) : undefined}
               aria-label={t("Find a page, an agent, an instance or a draft")} placeholder={t("Find anything")}
               autoComplete="off" spellCheck={false} value={query} autoFocus
               onChange={(event) => onQuery(event.target.value)} onKeyDown={keys} />
      </div>
      <div id={list} className="palette-list" role="listbox" aria-label={t("What it found")}>
        {groups.map((group, g) => (
          <div key={group.name} role="group" aria-labelledby={`${list}-g${g}`}>
            <p className="label" id={`${list}-g${g}`}>{group.name}</p>
            {group.options.map(([option, n]) => (
              <div key={option.id} id={optionId(n)} role="option" className="palette-option" aria-selected={n === chosen}
                   onPointerMove={() => n !== chosen && setAt(n)} onClick={() => onChoose(option)}>
                <Icon name={option.icon} />
                <span className="palette-name">{option.name}</span>
                <span className="palette-where">{option.where}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      {!options.length && <p className="palette-none" role="status">{query.trim() && !looking
        ? t("Nothing you may open is called “{query}”.", { query: query.trim() }) : t("Looking for what you may open…")}</p>}
      <p className="palette-keys">
        <span><kbd>↑</kbd> <kbd>↓</kbd> {t("to choose")}</span><span><kbd>Enter</kbd> {t("to open")}</span><span><kbd>Esc</kbd> {t("to close")}</span>
      </p>
    </dialog>
  );
}
