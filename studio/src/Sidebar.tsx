// The sidebar every page of a5s has (webchat/shell.js), as the studio draws it: the pages the
// signed-in person may use, named, ordered and under the headings /shell/api gives them, which
// every sidebar and the palette take from there alone (core/shell_api.py), and who they are.

import { type ReactNode, useEffect, useState } from "react";
import { get, type Place, type Shell } from "./api";
import { FindButton } from "./Find";
import { t } from "./i18n";
import { Icon } from "./icons";
import { inside, Link, useRoute } from "./router";

let shell: Promise<Shell> | null = null;

/** Who signed in, and the pages they may use, as /shell/api works them out: asked once for
 * the studio, by the sidebar and any page that offers a way to another, or afresh, as finding
 * anything does each time it opens, so a role lost meanwhile takes its page away (round 13, B6). */
export function shellOf(afresh = false): Promise<Shell> {
  if (afresh) shell = null;
  shell ??= get<Shell>("/shell/api").catch((e) => {
    shell = null;  // asked again next time
    throw e;
  });
  return shell;
}

/** Whether someone may use one of a5s's pages, as the sidebar lists them for them. */
export const mayUse = (found: Shell | null | undefined, page: string): boolean =>
  Boolean(found?.pages.some((place) => place.page === page));

/** A way to one of a5s's pages: one in the studio opens without leaving it, and is marked if
 * it's here; the rest are pages of their own. */
function To({ place, here, label, title, children }: {
  place: Place; here: string; label?: string; title?: string; children: ReactNode;
}) {
  const route = inside(place.at);
  return route
    ? <Link to={route} label={label} title={title} current={place.page === here}>{children}</Link>
    : <a href={place.at} aria-label={label} title={title}>{children}</a>;
}

/** The pages under each heading, in the order they come. */
function headed(pages: Place[]): [string, Place[]][] {
  const found: [string, Place[]][] = [];
  for (const place of pages) {
    const last = found[found.length - 1];
    if (last && last[0] === place.group) last[1].push(place);
    else found.push([place.group, [place]]);
  }
  return found;
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

/** A page that's one of a sidebar page's own, such as one conversation handed over, which
 * marks that page, not the studio's. */
const WITHIN: Record<string, string> = { handover: "handovers", approve: "settings" };

export function Sidebar({ signedIn, rail = false }: { signedIn: boolean; rail?: boolean }) {
  const [found, setFound] = useState<Shell | null>(null);
  const page = useRoute().page;
  // the page it marks: the one whose address this is, or whose own page this is, or else the
  // studio, for its own pages, such as an agent's or a run's
  const here = found?.pages.find((place) => inside(place.at)?.page === (WITHIN[page] ?? page))
    ?.page ?? "studio";
  useEffect(() => {
    if (!signedIn) return;
    shellOf().then(setFound).catch(() => setFound(null));
  }, [signedIn]);
  if (rail) {  // on the workbench, the sidebar shrunk to its icons, each still named
    const pages = found?.pages ?? [];
    return (
      <aside className="wb-rail">
        <a className="brand" href="/chat/" aria-label="a5s"><span className="mark">a5</span></a>
        <FindButton rail />
        <nav aria-label={t("a5s's pages")}>
          {pages.map((place) => (
            <To key={place.page} place={place} here={here} label={place.name} title={place.name}>
              <Icon name={place.icon} />
            </To>
          ))}
        </nav>
        {found && <span className="avatar" role="img" aria-label={found.you} title={found.you}>{initials(found.you)}</span>}
      </aside>
    );
  }
  return (
    <aside className="sidebar">
      <a className="brand" href="/chat/"><span className="mark">a5</span><span>a5s</span></a>
      {signedIn && <div className="find-slot"><FindButton id="find-anything" /></div>}
      <nav id="pages" aria-label={t("a5s's pages")}>
        {found && headed(found.pages).map(([heading, shown]) => (
          <div key={heading} className="nav-group">
            <div className="group">{heading}</div>
            {shown.map((place) => (
              <To key={place.page} place={place} here={here}><Icon name={place.icon} /><span>{place.name}</span></To>
            ))}
          </div>
        ))}
      </nav>
      <div className="me" id="me">
        {found && <><span className="avatar">{initials(found.you)}</span><span>{found.you}</span></>}
      </div>
    </aside>
  );
}
