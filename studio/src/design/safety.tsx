// What a press will do, said where it happens (Ocean's EnvironmentBand, ActingAs and ActionZone;
// docs/design.md, Risk, and the friction it earns): which deployment this is, on every page;
// whose power a page's acts use, on the pages that change things alone; and where its
// consequential acts are, apart from what only shows, saying first whom and what they reach.

import { type ReactNode, useEffect, useId, useState } from "react";
import type { Acting, Environment } from "../api";
import { t } from "../i18n";
import { Icon } from "../icons";
import { shellOf } from "../Sidebar";
import { initials } from "./people";

let asked: Promise<Environment | null> | null = null;

/** Which deployment this is, as the channels say it, asked once for the page: it needs no
 * sign-in, so the sign-in's page says it too (core/environment.py). */
export function environmentOf(): Promise<Environment | null> {
  asked ??= fetch("/shell/environment").then((found) => (found.ok ? found.json() : null)).catch(() => null);
  return asked;
}

const ICON: Record<string, string> = { production: "people", staging: "tool", test: "tool", development: "code" };

/** Which deployment this is, across the top of every page, whoever's signed in: production in
 * the change's colour, filled, the rest in amber. */
export function EnvironmentBand() {
  const [here, setHere] = useState<Environment | null>(null);
  useEffect(() => {
    let on = true;
    void environmentOf().then((found) => { if (on) setHere(found); });
    return () => { on = false; };
  }, []);
  if (!here) return null;
  return (
    <section className={`env-band ${here.kind}`} id="environment" aria-label={t("Which deployment this is")}>
      <Icon name={ICON[here.kind] ?? "tool"} />
      <strong>{here.name}</strong>
      <span>{here.about}</span>
    </section>
  );
}

/** Whose power a page uses, first in its main, before its head, on a page that changes things
 * alone: the role its acts count as, and what that lets them do there, as the page's API says
 * while it holds an act a role gives them (core/acting.py), beside the initials of whoever
 * signed in. Where the API says none, there's none, so the line means a role's power is in use. */
export function ActingAs({ acting }: { acting?: Acting | null }) {
  const [who, setWho] = useState("");
  useEffect(() => {
    let on = true;
    shellOf().then((found) => { if (on) setWho(found.you); }).catch(() => {});
    return () => { on = false; };
  }, []);
  if (!acting) return null;
  return (
    <p className="acting-as" id="acting-as">
      <span className="avatar" aria-hidden="true">{initials(who)}</span>
      <span>{t("Acting as")} <strong>{acting.role}</strong>: {acting.lets}</span>
    </p>
  );
}

/** Where a page's consequential acts are, saying first whom and what they reach. What can't be
 * undone is marked so, on the failure's well, and its Confirm asks for the name typed. An
 * everyday act has no zone at all. Its buttons go in a row, or, `stacked`, as they come, for a
 * card's own actions, such as an approval card's yes and no, which lay themselves out. */
export function ActionZone({ title, reach, cantUndo = false, level = 2, stacked = false, children }: {
  title: string; reach: ReactNode; cantUndo?: boolean; level?: 2 | 3; stacked?: boolean; children: ReactNode;
}) {
  const head = useId();
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <section className={cantUndo ? "action-zone cant-undo" : "action-zone"} aria-labelledby={head}>
      <Heading id={head}>{title}</Heading>
      {cantUndo && <p className="action-zone-mark"><Icon name="cross" />{t("Can't be undone")}</p>}
      <p className="action-zone-reach">{reach}</p>
      {stacked ? children : <div className="cluster">{children}</div>}
    </section>
  );
}
