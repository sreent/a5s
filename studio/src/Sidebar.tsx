// The sidebar every page of a5s has (webchat/shell.js), as the studio draws it: the pages the
// signed-in person may use, as /shell/api works them out, and who they are.

import { type ReactNode, useEffect, useState } from "react";
import { get } from "./api";
import { Icon } from "./icons";
import { Link, type Route, useRoute } from "./router";

const PAGES: [string, [string, string, string][]][] = [
  ["Work", [["chat", "Chat", "chat"], ["tasks", "Tasks", "tasks"], ["notebook", "Notebook", "book"]]],
  ["Build", [["studio", "Studio", "studio"]]],
  ["Decide", [["decide", "Decisions", "decide"], ["grade", "Grading", "grade"],
              ["settings", "Settings", "settings"]]],
  ["Oversee", [["audit", "Audit trail", "audit"], ["admin", "Administration", "admin"],
               ["officer", "Data protection", "officer"]]],
];

export type Shell = { you: string; pages: string[] };
let shell: Promise<Shell> | null = null;

/** Who signed in, and the pages they may use, as /shell/api works them out: asked once for
 * the studio, by the sidebar and any page that offers a way to another. */
export function shellOf(): Promise<Shell> {
  shell ??= get<Shell>("/shell/api").catch((e) => {
    shell = null;  // asked again next time
    throw e;
  });
  return shell;
}

// The studio's own pages, which it opens without leaving it: the rest are pages of their own
const INSIDE: Record<string, Route> = { studio: { page: "home" }, settings: { page: "settings" },
                                         notebook: { page: "notebook" }, tasks: { page: "tasks" },
                                         admin: { page: "admin" }, audit: { page: "audit" } };

/** A way to one of a5s's pages: within the studio, without leaving it; marked if it's here. */
function To({ page, here, label, title, children }: {
  page: string; here: string; label?: string; title?: string; children: ReactNode;
}) {
  const inside = INSIDE[page];
  return inside
    ? <Link to={inside} label={label} title={title} current={page === here}>{children}</Link>
    : <a href={`/${page}/`} aria-label={label} title={title}>{children}</a>;
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

export function Sidebar({ signedIn, rail = false }: { signedIn: boolean; rail?: boolean }) {
  const [found, setFound] = useState<Shell | null>(null);
  const page = useRoute().page;
  const here = page in INSIDE ? page : "studio";  // the page it marks
  useEffect(() => {
    if (!signedIn) return;
    shellOf().then(setFound).catch(() => setFound(null));
  }, [signedIn]);
  if (rail) {  // on the workbench, the sidebar shrunk to its icons, each still named
    const pages = found ? PAGES.flatMap(([, items]) => items.filter(([key]) => found.pages.includes(key))) : [];
    return (
      <aside className="wb-rail">
        <a className="brand" href="/chat/" aria-label="a5s"><span className="mark">a5</span></a>
        <nav aria-label="a5s's pages">
          {pages.map(([key, name, glyph]) => (
            <To key={key} page={key} here={here} label={name} title={name}><Icon name={glyph} /></To>
          ))}
        </nav>
        {found && <span className="avatar" role="img" aria-label={found.you} title={found.you}>{initials(found.you)}</span>}
      </aside>
    );
  }
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
                <To key={key} page={key} here={here}><Icon name={glyph} /><span>{name}</span></To>
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
