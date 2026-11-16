// The settings, folded into the studio from the settings app (core/settings_api.py), for the
// people who approve versions of them: each part's owner, the instance approvers, agents'
// owners, the data protection officer and assurance, each for what's theirs. They see the whole
// version in force in words, and the versions waiting for approval, and ask for a change. Asking
// changes nothing: a5s proposes the new version to everyone who must approve it, and they
// approve it on its own page, signing in afresh.
//
// A change is written in forms, for what people change most: an instance's level, the types of
// change it makes on its own at level 2, whom it serves and who runs it, a new instance of an
// agent, each type of change's limits, and the accuracy each part needs for level 2. Or in the
// whole text, for anything else. The forms send the version as JSON, which a5s reads as the
// YAML it is, and the review says in words what it would change, either way.

import { type ReactNode, useEffect, useReducer, useRef, useState } from "react";
import { type Change, get, send, type SettingsAsked, type SettingsNow, type SettingsReview } from "../api";
import { useToast } from "../design";
import { Icon } from "../icons";
import { ImpactPreview } from "../Impact";
import { PageHead, sentence, To, Waiting, when } from "../ui";
import { keepUnkept, keptNow, unkept } from "../unkept";

// What they've changed and not asked for yet, against the version in force they changed, kept
// in the tab until they ask, so signing in again gives it back (round 13, C1)
type Working = { serial: number | null; data: unknown; text: string };
const WORKING = "settings";

type PartEntry = number | null | { level?: number; actions?: Record<string, number> };
type Inst = { definition: string; serves?: string[]; parts?: string[] | Record<string, PartEntry>;
              level?: number; owner?: string; deputy?: string; asks?: string[]; [key: string]: unknown };
type Limit = { per_run?: number; per_person_30_days?: number };
type Data = { instances?: Record<string, Inst>; limits?: Record<string, Limit>;
              thresholds?: Record<string, number>; [key: string]: unknown };
/** A new instance, as its form has it so far: `id` null while its name follows the suggestion. */
type Adding = { agent: string; id: string | null; part: string; level: number; serves: Set<string>;
                owner: string; deputy: string; more: string[]; asks: string[] };
type Plan = { agent: string; parts: string[]; serves: string[]; asks: string[] };

const LEVELS: Record<number, string> = {
  0: "level 0, suggests: it reads and drafts, and people do the rest",
  1: "level 1, asks: its changes wait for a person's yes",
};
const ID = /^[a-z0-9][a-z0-9-]{0,62}$/;
// whom an instance serves, as the settings write it: someone's id, or a team or a role
const WHO = /^(?:(?:team|role):[A-Za-z0-9][A-Za-z0-9._@:-]{0,127}|[A-Za-z0-9][A-Za-z0-9._@-]{0,127})$/;

const partsOf = (inst?: Inst): string[] => {
  const parts = inst?.parts || [];
  return Array.isArray(parts) ? parts : Object.keys(parts);
};

function entryOf(inst: Inst | undefined, part: string): PartEntry {  // null, a level, or {level, actions}
  const parts = inst?.parts;
  return parts && !Array.isArray(parts) ? (parts[part] ?? null) : null;
}

function partLevel(inst: Inst | undefined, part: string): number | null {
  const entry = entryOf(inst, part);
  if (typeof entry === "number") return entry;
  return entry && typeof entry.level === "number" ? entry.level : null;
}

function actionLevel(inst: Inst | undefined, part: string, action: string): number | undefined {
  const entry = entryOf(inst, part);
  const level = entry && typeof entry === "object" && entry.actions ? entry.actions[action] : undefined;
  return typeof level === "number" ? level : undefined;
}

function changePart(inst: Inst, part: string,
                    change: (entry: { level?: number; actions: Record<string, number> }) => void): void {
  // A part's own levels need the parts as a mapping, which keeps each part's as it was
  if (!inst.parts || Array.isArray(inst.parts)) {
    inst.parts = Object.fromEntries((inst.parts || []).map((each) => [each, null]));
  }
  const parts = inst.parts as Record<string, PartEntry>;
  const was = parts[part];
  const entry: { level?: number; actions: Record<string, number> } = was && typeof was === "object"
    ? { ...was, actions: { ...(was.actions || {}) } }
    : { ...(typeof was === "number" ? { level: was } : {}), actions: {} };
  change(entry);
  const kept: { level?: number; actions?: Record<string, number> } = { ...entry };
  if (!Object.keys(entry.actions).length) delete kept.actions;
  parts[part] = Object.keys(kept).length ? kept : null;
}

/** A box or button beside its words, which wrap beside it; one that can't be chosen says why. */
function Choice({ type, name, checked, label, why, onChange }: {
  type: "radio" | "checkbox"; name: string; checked: boolean; label: string; why?: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="choice">
      <input type={type} name={name} checked={checked} disabled={why !== undefined}
             onChange={(e) => onChange(e.target.checked)} />
      <span>{label}{why !== undefined && <span className="faint">: {why}</span>}</span>
    </label>
  );
}

/** A value, with its words before it, and any after it. */
function Setting({ words, after, children }: { words: string; after?: string; children: ReactNode }) {
  return <label className="setting"><span>{words}</span>{children}{after && <span>{after}</span>}</label>;
}

/** A change in the words code worked out, marked where it widens what agents do, as the page
 * that approves it marks it. */
function changeLine(change: Change, i: number) {
  return (
    <li key={i}>{change.text}{change.widens && <>{" "}<span className="badge changes">widens what agents do</span></>}</li>
  );
}

/** An agent someone chose to put to work, on its page in the studio or as its draft planned it:
 * its name, the parts it works in, whom it serves and which instances it may ask, from the
 * address, each only as the version's forms could offer it. */
function planned(): Plan | null {
  const params = new URLSearchParams(location.search);
  const agent = params.get("add");
  if (!agent || !ID.test(agent)) return null;
  const listed = (key: string) => (params.get(key) || "").split(",").filter((one) => WHO.test(one));
  return { agent, parts: listed("parts"), serves: listed("serves"), asks: listed("asks") };
}

/** Why a review or a request didn't go through, beside its button, as Ocean's error note says it. */
function Refused({ id, said }: { id: string; said: string }) {
  return (
    <p className="error-note" id={id} role="alert" tabIndex={-1}>
      <Icon name="cross" /><strong>{sentence(said)}</strong>
    </p>
  );
}

export function SettingsPage() {
  const toast = useToast();
  const [now, setNow] = useState<SettingsNow>();
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<string>();
  const working = useRef<Data | null>(null);  // the version in force, as the forms change it
  const nowRef = useRef<SettingsNow | null>(null);
  const [generation, setGeneration] = useState(0);  // the forms drawn afresh from what's in force
  const [names, setNames] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"forms" | "text">("forms");
  const [text, setText] = useState("");
  const [reviewed, setReviewed] = useState<{ found: SettingsReview; text: string }>();
  const [adding, setAdding] = useState<Adding | null>(null);
  const [addProblem, setAddProblem] = useState<string>();
  const [focus, setFocus] = useState<string>();  // what to bring into view and focus, once drawn
  const [busy, setBusy] = useState(false);
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  // What went wrong with a review or a request, said beside its button, where they are, and
  // given the focus, not in the page's status line far above (round 13, C6)
  const [refused, setRefused] = useState<{ at: "review" | "send"; said: string }>();
  useEffect(() => {
    if (refused) document.getElementById(`${refused.at}-refused`)?.focus();
  }, [refused]);

  const textNow = useRef("");
  const remember = () => keepUnkept(WORKING, { serial: nowRef.current?.in_force?.serial ?? null,
                                               data: working.current, text: textNow.current } satisfies Working);
  // A change after a review needs a review of its own before anyone asks for it
  const touched = () => {
    setReviewed(undefined);
    remember();
    redraw();
  };

  const load = async (fresh: boolean): Promise<SettingsNow> => {
    const found = await get<SettingsNow>("/settings/api");
    nowRef.current = found;
    const left = fresh ? null : unkept<Working>(WORKING);
    if (fresh || (left && left.serial !== (found.in_force?.serial ?? null))) keptNow(WORKING);  // asked for, or out of date
    if (found.in_force) {
      if (left && left.serial === found.in_force.serial && !working.current) {
        working.current = left.data as Data;
        textNow.current = left.text;
        setText(left.text);
        setStatus("What you'd changed and hadn't asked for is back, from before you signed in again.");
      } else if (fresh || !working.current) working.current = structuredClone(found.in_force.data ?? {}) as Data;
      const written = found.in_force.text;
      if (!textNow.current || fresh) textNow.current = written;
      setText((was) => (was && !fresh ? was : written));
    } else {
      setMode("text");  // the forms change a version in force: with none, there's the text
    }
    setNames((was) => ({ ...was, ...found.names }));
    setNow(found);
    return found;
  };

  useEffect(() => {
    const plan = planned();
    const params = new URLSearchParams(location.search);
    const instance = params.get("instance");
    if (location.search) history.replaceState(null, "", "/studio/settings");  // used once
    load(false).then((found) => {
      if (plan && found.releases[plan.agent]) offer(found, plan);
      else if (instance && ID.test(instance)) setFocus(`fieldset[data-instance="${CSS.escape(instance)}"]`);
      if (!found.in_force) setStatus("No settings are in force yet.");
    }).catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!focus) return;
    const found = document.querySelector<HTMLElement>(focus);
    found?.scrollIntoView({ block: "start" });
    found?.focus();
    setFocus(undefined);
  }, [focus]);

  if (error) return <><PageHead title="Settings" /><Waiting error={error} /></>;
  if (!now) return <><PageHead title="Settings" /><Waiting /></>;
  const settings = now;
  const w = working.current;
  const inForce = settings.in_force?.data as Data | null | undefined;

  // Someone an instance serves, by name, or a group, as the directory decides who is in it
  const whom = (who: string) => {
    if (who.startsWith("team:")) return `everyone in the ${who.slice(5)} team`;
    if (who.startsWith("role:")) return `everyone who holds the ${who.slice(5)} role`;
    return names[who] || who;
  };
  const people = () => Object.keys(names).filter((each) => !each.includes(":"));

  function servable(): string[] {
    // Whom a new instance may serve: each person the settings name, and each team or role the
    // settings in force serve already, as they write it
    const groups = Object.values(w?.instances || {}).flatMap((i) => i.serves || []).filter((x) => x.includes(":"));
    return [...new Set([...Object.keys(names), ...groups])];
  }

  function suggested(a: Adding): string {
    // A name for the new instance, the agent's and then its part's, unused
    const base = `${a.agent}-${a.part || "new"}`.slice(0, 60);
    let id = base;
    for (let n = 2; w?.instances?.[id]; n += 1) id = `${base}-${n}`;
    return id;
  }

  function freshAdding(agent: string, before: Partial<Adding> | null = null,
                       releases = settings.releases): Adding {
    // It starts as low as its release does, at level 1 at most, serving whoever's adding it,
    // run by them; or, for another agent, what they'd chosen
    return { agent, id: null, part: before?.part ?? "", level: Math.min(releases[agent]?.starts ?? 1, 1),
             serves: before?.serves ?? new Set([settings.me]), owner: before?.owner ?? settings.me,
             deputy: before?.deputy ?? "", more: before?.more ?? [], asks: before?.asks ?? [] };
  }

  function offer(found: SettingsNow, plan: Plan): void {
    const data = working.current;
    if (!data) return;
    const parts = [...new Set([...Object.keys(data.thresholds || {}),
                               ...Object.values(data.instances || {}).flatMap(partsOf)])];
    const groups = Object.values(data.instances || {}).flatMap((i) => i.serves || []).filter((x) => x.includes(":"));
    const among = [...new Set([...Object.keys(found.names), ...groups])];
    const known = (list: string[], from: string[]) => list.filter((one) => from.includes(one));
    const [part, ...more] = known(plan.parts, parts);
    const serves = known(plan.serves, among);  // a team or a role as the settings write it, too
    setAdding({
      agent: plan.agent, id: null, part: part ?? "", more,
      level: Math.min(found.releases[plan.agent]?.starts ?? 1, 1),
      serves: serves.length ? new Set(serves) : new Set([found.me]), owner: found.me, deputy: "",
      asks: known(plan.asks, Object.keys(data.instances || {})),
    });
    setFocus("#add-agent");
  }

  function levelsOf(id: string, inst: Inst): ReactNode {
    const release = settings.releases[inst.definition];
    const options: [number | null, string][] = [[0, LEVELS[0]], [1, LEVELS[1]], [null, release
      ? `whatever level its release starts at, now level ${release.starts}` : "whatever level its release starts at"]];
    if (inst.level === 2) {
      options.push([2, "level 2, as written: a5s holds it at level 1 in a part, and gives level 2 only to a type of change, below"]);
    }
    const was = inForce?.instances?.[id];
    return (
      <>
        <p className="lead">It works at</p>
        <div className="choices">{options.map(([n, about]) => (
          <Choice key={String(n)} type="radio" name={`level-${id}`} checked={(inst.level ?? null) === n} label={about}
                  why={release && n !== null && n > release.most && inst.level !== n
                    ? `its release allows level ${release.most} at most` : undefined}
                  onChange={() => {
                    if (n === null) delete inst.level;
                    else inst.level = n;
                    touched();
                  }} />
        ))}</div>
        {partsOf(inst).map((part) => {  // a part with a level of its own, which the level above doesn't change
          const own = partLevel(inst, part);
          if (own === null && partLevel(was, part) === null) return null;
          return (
            <Setting key={part} words={`In ${part}, it works at`}>
              <select aria-label={`${id}'s level in ${part}`} value={own === null ? "" : String(own)}
                      onChange={(e) => {
                        const level = e.target.value === "" ? null : Number(e.target.value);
                        changePart(inst, part, (entry) => {
                          if (level === null) delete entry.level;
                          else entry.level = level;
                        });
                        touched();
                      }}>
                <option value="">the level above</option>
                {(own === 2 ? [0, 1, 2] : [0, 1]).map((n) => <option key={n} value={String(n)}>{LEVELS[n] || `level ${n}`}</option>)}
              </select>
            </Setting>
          );
        })}
      </>
    );
  }

  function ownChanges(id: string, inst: Inst): ReactNode {
    const release = settings.releases[inst.definition];
    const kinds = release ? release.actions : settings.actions;  // the types of change its tools make
    const parts = partsOf(inst);
    if (!kinds.length || !parts.length) return null;
    const allowed = !release || release.most >= 2;
    return (
      <>
        <p className="lead">It makes these changes on its own, at level 2</p>
        <div className="choices">{parts.flatMap((part) => kinds.map((action) => {
          const on = actionLevel(inst, part, action) === 2;
          const earns = w?.thresholds?.[part] !== undefined;
          const why = !allowed ? `its release, ${inst.definition}, allows level ${release?.most} at most`
            : !earns ? `${part} needs no accuracy below, so it never earns level 2` : undefined;
          return (
            <Choice key={`${part}:${action}`} type="checkbox" name={`own-${id}`} checked={on}
                    label={`${action} in ${part}`} why={on ? undefined : why}
                    onChange={(checked) => {
                      // Unticked, it goes back to the level the version in force sets it, if not 2
                      const was = actionLevel(inForce?.instances?.[id], part, action);
                      const level = checked ? 2 : (was === 2 ? undefined : was);
                      changePart(inst, part, (entry) => {
                        if (level === undefined) delete entry.actions[action];
                        else entry.actions[action] = level;
                      });
                      touched();
                    }} />
          );
        }))}</div>
        <p className="note">Each within its limits, below. a5s holds it at level 1 until graded samples of its work show the accuracy its part needs.</p>
      </>
    );
  }

  function servesOf(id: string, inst: Inst): ReactNode {
    const everyone = [...new Set([...(inst.serves || []), ...Object.keys(names)])];
    const field = `input[data-adds="${CSS.escape(id)}"]`;
    const adds = () => {
      const input = document.querySelector<HTMLInputElement>(field);
      const who = input?.value.trim();
      if (!input || !who) return;
      inst.serves = [...new Set([...(inst.serves || []), who])];
      setNames((was) => ({ [who]: who, ...was }));  // the review says who they are, if the directory knows them
      input.value = "";
      touched();
      setFocus(field);
    };
    return (
      <>
        <p className="lead">It serves</p>
        <div className="choices">{everyone.map((who) => (
          <Choice key={who} type="checkbox" name={`serves-${id}`} checked={(inst.serves || []).includes(who)}
                  label={whom(who)} onChange={(checked) => {
                    const chosen = new Set(inst.serves || []);
                    if (checked) chosen.add(who);
                    else chosen.delete(who);
                    inst.serves = everyone.filter((each) => chosen.has(each));
                    touched();
                  }} />
        ))}</div>
        <div className="add-someone">
          <input type="text" data-adds={id} placeholder="an id, team:… or role:…" aria-label={`Someone else ${id} serves`}
                 onKeyDown={(e) => {
                   if (e.key === "Enter") {
                     e.preventDefault();
                     adds();
                   }
                 }} />
          <button type="button" onClick={adds}>Add</button>
        </div>
      </>
    );
  }

  function runsOf(id: string, inst: Inst): ReactNode {
    return (
      <>
        <p className="lead">Who runs it here</p>
        <div className="choices">{([["owner", "Owner"], ["deputy", "Deputy"]] as const).map(([role, label]) => (
          <Setting key={role} words={label}>
            <select aria-label={`${label} of ${id}`} value={inst[role] || ""} onChange={(e) => {
              if (e.target.value) inst[role] = e.target.value;
              else delete inst[role];
              touched();
            }}>
              <option value="">nobody</option>
              {people().map((who) => <option key={who} value={who}>{names[who]}</option>)}
            </select>
          </Setting>
        ))}</div>
      </>
    );
  }

  function addForm(parts: string[]): ReactNode {
    const agents = Object.keys(settings.releases);
    if (!agents.length || !w) return null;
    const a = adding ?? freshAdding(agents[0]);
    const release = settings.releases[a.agent];
    const change = (to: Partial<Adding>) => setAdding({ ...a, ...to });
    const add = () => {
      const id = (a.id ?? suggested(a)).trim();
      const wrong = !ID.test(id) ? "Its name is lowercase letters, digits and hyphens, starting with a letter or a digit."
        : w.instances?.[id] ? `There's an instance called ${id} already: give it another name.`
        : !a.serves.size ? "Choose whom it serves: a few people first."
        : undefined;
      setAddProblem(wrong);
      if (wrong) return;
      w.instances ||= {};
      w.instances[id] = { definition: a.agent, serves: [...a.serves], level: a.level,
                          ...(a.owner ? { owner: a.owner } : {}), ...(a.deputy ? { deputy: a.deputy } : {}),
                          parts: [...new Set([a.part, ...a.more].filter(Boolean))],
                          ...(a.asks.length ? { asks: [...a.asks] } : {}) };
      setAdding(null);
      touched();
      setFocus(`fieldset[data-instance="${CSS.escape(id)}"]`);
      setStatus(`${id} is in the forms: review it, with any other change, and ask its approvers.`);
    };
    return (
      <fieldset className="form-card adding" id="add-instance">
        <legend>Put an agent to work</legend>
        <p className="note">A new instance of an agent, for a few people first, at level 0 or 1, so it suggests, or asks before each change. Its part's owner approves it, as any change there; with no part, someone who approves instances does.</p>
        <div className="choices">
          <Setting words="Agent">
            <select id="add-agent" value={a.agent} onChange={(e) => {
              setAdding(freshAdding(e.target.value, a));
              setFocus("#add-agent");
            }}>
              {agents.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </Setting>
          <Setting words="Works in">
            <select id="add-part" value={a.part} onChange={(e) => change({ part: e.target.value })}>
              <option value="">no part's records</option>
              {parts.map((each) => <option key={each} value={each}>{each}</option>)}
            </select>
          </Setting>
          <Setting words="Its name here">
            {/* what it's called follows its part, unless they named it */}
            <input type="text" id="add-id" value={a.id ?? suggested(a)} onChange={(e) => change({ id: e.target.value })} />
          </Setting>
        </div>
        <p className="lead">It starts at</p>
        <div className="choices">{[0, 1].map((n) => (
          <Choice key={n} type="radio" name="add-level" checked={a.level === n} label={LEVELS[n]}
                  why={release && n > release.most ? `its release allows level ${release.most} at most` : undefined}
                  onChange={() => change({ level: n })} />
        ))}</div>
        {(a.more.length > 0 || a.asks.length > 0) && (  // as its draft's authors planned it, beyond the form
          <p className="note">{[a.more.length ? `It works in ${a.more.join(", ")} too.` : "",
                                a.asks.length ? `It may ask ${a.asks.join(", ")}.` : "",
                                "As its draft's authors planned it: change the version's text for anything else."]
            .filter(Boolean).join(" ")}</p>
        )}
        <p className="lead">It serves</p>
        <div className="choices">{[...new Set([...servable(), ...a.serves])].map((who) => (
          <Choice key={who} type="checkbox" name="add-serves" checked={a.serves.has(who)} label={whom(who)}
                  onChange={(checked) => {
                    const serves = new Set(a.serves);
                    if (checked) serves.add(who);
                    else serves.delete(who);
                    change({ serves });
                  }} />
        ))}</div>
        <p className="lead">Who runs it here</p>
        <div className="choices">{([["owner", "Owner"], ["deputy", "Deputy"]] as const).map(([role, label]) => (
          <Setting key={role} words={label}>
            <select aria-label={`${label} of the new instance`} value={a[role]} onChange={(e) => change({ [role]: e.target.value })}>
              <option value="">nobody</option>
              {people().map((who) => <option key={who} value={who}>{names[who]}</option>)}
            </select>
          </Setting>
        ))}</div>
        <div className="add-someone"><button type="button" id="add-it" onClick={add}>Add it to the settings</button></div>
        <p className="problem-note" role="alert">{addProblem}</p>
      </fieldset>
    );
  }

  function limitsForm(): ReactNode {
    const data = w as Data;
    return (
      <fieldset className="form-card">
        <legend>Each type of change's limits</legend>
        <p className="note">How many one run may make, and how many for each person in 30 days. Past either, a change waits for a person to decide it, whatever the level. Empty means no limit.</p>
        {[...new Set([...settings.actions, ...Object.keys(data.limits || {})])].map((action) => (
          <div key={action} className="limit">
            <p className="limit-name">{action}</p>
            {([["per_run", "In one run"], ["per_person_30_days", "For each person, in 30 days"]] as const).map(([field, words]) => (
              <Setting key={field} words={words}>
                <input type="number" min="1" max="100000" defaultValue={data.limits?.[action]?.[field] ?? ""}
                       aria-label={`${action}, ${words.toLowerCase()}`} onChange={(e) => {
                         const limits = (data.limits ||= {});
                         const limit = (limits[action] ||= {});
                         const n = Number(e.target.value);
                         if (e.target.value !== "" && Number.isInteger(n)) limit[field] = n;
                         else delete limit[field];
                         if (!Object.keys(limit).length) delete limits[action];
                         touched();
                       }} />
              </Setting>
            ))}
          </div>
        ))}
      </fieldset>
    );
  }

  function thresholdsForm(parts: string[]): ReactNode {
    const data = w as Data;
    return (
      <fieldset className="form-card">
        <legend>The accuracy level 2 needs</legend>
        <p className="note">How accurate an agent's changes in a part must be, as graded samples show, before a5s raises its cap there to level 2. Empty means it never does.</p>
        <div className="choices">{parts.map((part) => {
          const share = data.thresholds?.[part];
          return (
            <Setting key={part} words={part} after="%">
              <input type="number" min="50" max="99.9" step="0.1"
                     defaultValue={share === undefined ? "" : String(Math.round(share * 1000) / 10)}
                     aria-label={`The accuracy ${part} needs, in percent`} onChange={(e) => {
                       const thresholds = (data.thresholds ||= {});
                       const n = Number(e.target.value);
                       if (e.target.value !== "" && Number.isFinite(n)) thresholds[part] = Math.round(n * 10) / 1000;
                       else delete thresholds[part];
                       touched();
                     }} />
            </Setting>
          );
        })}</div>
      </fieldset>
    );
  }

  function forms(): ReactNode {
    if (!w) return null;
    const parts = [...new Set([...Object.keys(w.thresholds || {}), ...Object.values(w.instances || {}).flatMap(partsOf)])];
    return (
      <>
        {Object.entries(w.instances || {}).map(([id, inst]) => (
          <fieldset key={id} className="form-card" data-instance={id} tabIndex={-1}>
            <legend>{id}, the {inst.definition}</legend>
            {levelsOf(id, inst)}{ownChanges(id, inst)}{servesOf(id, inst)}{runsOf(id, inst)}
          </fieldset>
        ))}
        {addForm([...parts].sort())}
        {(settings.actions.length > 0 || Object.keys(w.limits || {}).length > 0) && limitsForm()}
        {parts.length > 0 && thresholdsForm(parts)}
      </>
    );
  }

  // The version as written: the forms' as JSON, which a5s reads as YAML, or the text
  const draft = () => (mode === "text" ? text : JSON.stringify(w));

  const review = async () => {
    setReviewed(undefined);
    setRefused(undefined);
    const written = draft();
    try {
      setReviewed({ found: await send<SettingsReview>("POST", "/settings/api/review", { text: written }), text: written });
    } catch (e) {
      setRefused({ at: "review", said: (e as Error).message });
    }
  };

  const ask = async (asking: { found: SettingsReview; text: string }) => {
    setBusy(true);
    try {
      const asked = await send<SettingsAsked>("POST", "/settings/api/requests",
                                              { text: asking.text, base: asking.found.in_force ?? null });
      setReviewed(undefined);
      setStatus(`You asked for version ${asked.serial}. a5s asks its approvers within a minute, and puts it in force once they've all approved it.`);
      toast(`You asked for version ${asked.serial}.`);
      await load(true);
      setGeneration((n) => n + 1);  // the forms start again from what's in force
    } catch (e) {
      setRefused({ at: "send", said: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const chooseMode = (chosen: "forms" | "text") => {
    setMode(chosen);
    setReviewed(undefined);
  };

  const found = reviewed?.found;
  return (
    <>
      <PageHead title="Settings"
                about="The instances at work: whom each serves, where it works and how far it may act there, and who runs it. A change is a new version, which those who must approve it approve on its own page; nothing changes until they do." />
      <p id="status" role="status" className="note">{status}</p>
      {settings.in_force && (
        <section className="card" id="in-force">
          <h2 id="in-force-title">In force: version {settings.in_force.serial}</h2>
          <ul id="whole" className="plain">{settings.in_force.whole.map((line, i) => <li key={i}>{line}</li>)}</ul>
        </section>
      )}
      {settings.waiting.length > 0 && (
        <section className="card" id="waiting-section">
          <h2>Waiting for approval</h2>
          <div id="waiting">{settings.waiting.map((version) => (
            <div key={version.serial}>
              <p><To go={version.link}>Version {version.serial}</To>{version.approved_by.length
                ? `, approved so far by ${version.approved_by.join(", ")}.` : ", which nobody has approved yet."}</p>
              <ul className="plain">{version.changes.map(changeLine)}</ul>
              {version.needs.length > 0 && <p className="note">It still waits because {version.needs.join("; ")}.</p>}
            </div>
          ))}</div>
        </section>
      )}
      <section className="card" id="edit">
        <h2>Ask for a change</h2>
        <p className="note">Change the settings below, then review them. a5s gives the new version the next number, and once you ask for it, asks everyone who must approve it. Nothing changes until they do.</p>
        {settings.in_force && (
          <div id="modes" className="modes" role="group" aria-label="How to write the change">
            <button id="by-forms" type="button" aria-pressed={mode === "forms"} onClick={() => chooseMode("forms")}>Change it here</button>
            <button id="by-text" type="button" aria-pressed={mode === "text"} onClick={() => chooseMode("text")}>Edit the text</button>
          </div>
        )}
        <div id="forms" hidden={mode !== "forms"} key={generation}>{forms()}</div>
        <div id="as-text" hidden={mode !== "text"}>
          <p className="note">The whole version, as written, for whatever the forms don't change. What you review is the way you're using: these forms, or this text.</p>
          <textarea id="text" spellCheck={false} aria-label="The settings, as written" value={text}
                    onChange={(e) => {
                      setText(e.target.value);
                      textNow.current = e.target.value;
                      remember();
                      setReviewed(undefined);
                    }} />
        </div>
        <p><button id="review" type="button" onClick={review}>Review</button></p>
        {refused?.at === "review" && <Refused id="review-refused" said={refused.said} />}
        {reviewed && found && (
          <div id="reviewed">
            <p id="reviewed-summary">{found.serial === undefined ? "a5s can't propose this:"
              : found.problems.length ? `As version ${found.serial}, a5s can't propose this:` : `As version ${found.serial}, it:`}</p>
            <ul id="problems" className="plain">{found.problems.map((problem, i) => <li key={i} className="problem">{problem}</li>)}</ul>
            {found.serial !== undefined && (
              <>
                <ul id="reviewed-changes" className="plain">{(found.changes ?? []).map(changeLine)}</ul>
                <p id="reviewed-approvers">{found.approvers?.length
                  ? `It needs the approval of ${found.approvers.join(", ")}.` : "Nobody in the directory can approve it."}</p>
                <h3>The whole version</h3>
                <ul id="reviewed-whole" className="plain">{(found.whole ?? []).map((line, i) => <li key={i}>{line}</li>)}</ul>
                {found.impact && <ImpactPreview impact={found.impact} id="reviewed-impact" />}
                {found.problems.length === 0 && (
                  <button id="send" className="primary" type="button" disabled={busy} onClick={() => ask(reviewed)}>Ask its approvers</button>
                )}
                {refused?.at === "send" && <Refused id="send-refused" said={refused.said} />}
              </>
            )}
          </div>
        )}
      </section>
      {settings.requests.length > 0 && (
        <section className="card" id="requests-section">
          <h2>What you asked for</h2>
          <ul id="requests" className="plain">{settings.requests.map((request) => (
            <li key={`${request.serial}:${request.asked_at}`}>Version {request.serial}, asked for {when(request.asked_at)}: {request.outcome}.</li>
          ))}</ul>
        </section>
      )}
    </>
  );
}
