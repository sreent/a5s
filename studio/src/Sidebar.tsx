// The sidebar every page of a5s has (webchat/shell.js), as the studio draws it: the pages the
// signed-in person may use, as /shell/api works them out, and who they are.

import { useEffect, useState } from "react";
import { get } from "./api";
import { Icon } from "./icons";

const PAGES: [string, [string, string, string][]][] = [
  ["Work", [["chat", "Chat", "chat"], ["tasks", "Tasks", "tasks"], ["notebook", "Notebook", "book"]]],
  ["Build", [["studio", "Studio", "studio"]]],
  ["Decide", [["decide", "Decisions", "decide"], ["grade", "Grading", "grade"],
              ["settings", "Settings", "settings"]]],
  ["Oversee", [["audit", "Audit trail", "audit"], ["admin", "Administration", "admin"],
               ["officer", "Data protection", "officer"]]],
];

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

export function Sidebar({ signedIn }: { signedIn: boolean }) {
  const [found, setFound] = useState<{ you: string; pages: string[] } | null>(null);
  useEffect(() => {
    if (!signedIn) return;
    get<{ you: string; pages: string[] }>("/shell/api").then(setFound).catch(() => setFound(null));
  }, [signedIn]);
  return (
    <aside className="sidebar">
      <a className="brand" href="/chat/"><span className="mark">a5</span><span>a5s</span></a>
      <nav id="pages" aria-label="a5s's pages">
        {found && PAGES.map(([heading, items]) => {
          const shown = items.filter(([key]) => found.pages.includes(key));
          if (!shown.length) return null;
          return (
            <div key={heading} className="nav-group">
              <div className="group">{heading}</div>
              {shown.map(([key, name, glyph]) => (
                <a key={key} href={`/${key}/`} aria-current={key === "studio" ? "page" : undefined}>
                  <Icon name={glyph} /><span>{name}</span>
                </a>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="me" id="me">
        {found && <><span className="avatar">{initials(found.you)}</span><span>{found.you}</span></>}
      </div>
    </aside>
  );
}
