// The designer: an agent built by hand on its canvas, the workbench's Design view (Ocean's
// Workbench and FlowNode). It adopts n8n's canvas, and extends it where an agent and a5s's
// governance need more (docs/studio.md#the-designer): the parts to add on the left, the
// scenario's tools by what they do, a5s's own abilities and what starts a run; the agent on the
// canvas, with what starts it, its reply, and its model, a5s's checks and its tools hanging below
// it; and on the right, whatever is chosen, to change, with what follows from it: who decides
// its changes, part by part, who signs its release, and its limits. With nothing chosen, the
// draft as a whole: where it stands, what stops its release, and what follows from it all.
//
// Each change is made to agent.yaml, as the forms and its files make theirs, and kept and checked
// as theirs are, and says what it made follow. The same, as a list, for a keyboard or a phone,
// which a narrow screen starts with.

import { type ReactNode, useEffect, useRef, useState } from "react";
import type { Offer, Offered, Plan, Signer, Tool } from "./api";
import { type Ability, abilities, and, CHANNEL_WORDS, changers, dayWords, deciders, levelLines, limitLines,
  messageLines, PREFERENCES, scheduleLines, toolLines } from "./consequences";
import { DAYS, read, type Schedule, type Spec, Unreadable, withMap, withMessages, without, withoutSchedule,
  withReports, withSchedule, withTool, withValue, withWords } from "./definition";
import { breakable, type Flow, FlowMap, type Step } from "./FlowMap";
import { t } from "./i18n";
import { Icon } from "./icons";
import { levelName, writtenLevel } from "./levels";
import { levels, plural, type Risk, risk, RISK_NAMES, ToolBadges, useView, Views } from "./ui";

type Files = Record<string, string>;

const ORDER: Risk[] = ["changes", "outside", "writes", "reads"];
const DRAG = "application/x-a5s-tool";
const SHOWN = "a5s.studio.design-shown";
const FIRST_SCHEDULE: Omit<Schedule, "name"> = { at: ["09:00"], days: ["mon", "tue", "wed", "thu", "fri"],
                                                 task: "Look through the open records." };
/** What an ability's being added or taken away makes follow, in words. */
const turned = (): Record<Ability, [now: string, gone: string]> => ({
  reminders: [t("Now it offers reminders, and keeps those people confirm."), t("It no longer offers reminders.")],
  recall: [t("Now it searches its conversation with the person it acts for, and corrects its summaries at their word."),
           t("It no longer searches its conversation with the person it acts for.")],
  documents: [t("Now it asks a5s's reader about documents from outside its run has read."),
              t("It no longer asks a5s's reader about documents from outside its run has read.")],
  agents: [t("Now it asks other agents questions, those the settings name."), t("It no longer asks other agents questions.")],
  notebook: [t("Now it notes what it learns from records, on its schedules, for its later runs."),
             t("It no longer notes what it learns from records.")],
  tasks: [t("Now it takes on long tasks people ask for, over more than one run, once they say yes."),
          t("It no longer takes on long tasks.")],
  "digest-time": [t("Now it lets people set when their daily digest comes."),
                  t("It no longer lets people set when their daily digest comes.")],
  "how-i-work": [t("Now it keeps what people tell it of how they like to work, at their word."),
                 t("It no longer keeps what people tell it of how they like to work.")],
});

const asTool = (t: Offered): Tool => ({ ...t, group: "", pinned: null, missing: false });
const has = (spec: Spec, key: Ability) => (key === "tasks" ? Boolean(spec.tasks) : key === "reminders" ? spec.reminders
  : PREFERENCES.includes(key) ? spec.preferences.includes(key) : spec.context[key as keyof Spec["context"]] === true);

// The agent as steps: what the canvas and the list both show

/** Whom a plan would serve, by the names the settings give them. */
const servedBy = (plan: Plan, offer: Offer) =>
  plan.serves.map((id) => offer.servable.find((s) => s.id === id)?.name ?? id);

function flowOf(spec: Spec, name: string, offer: Offer, problems: number, plan: Plan): Flow {
  const offered = new Map(offer.tools.map((t) => [t.name, t]));
  const starts: Step[] = [];
  spec.triggers.forEach((trigger, i) => {
    if (trigger.kind === "message") {
      const channels = and(spec.channels.map((c) => CHANNEL_WORDS[c] ?? c)) || t("no channel");
      starts.push({ key: "messages", icon: "message", name: t("A message"),
                    about: plan.serves.length ? t("from {who}, on {channels}", { who: and(servedBy(plan, offer)), channels })
                      : t("{about}, on {channels}", { about: trigger.about, channels }) });
    } else starts.push({ key: `trigger:${i}`, icon: "run", name: trigger.kind, about: trigger.about });
  });
  spec.schedules.forEach((s, i) => starts.push({ key: `schedule:${i}`, icon: "clock", name: s.name || t("a schedule"),
                                                  about: t("{at}, {days}", { at: s.at.join(", ") || t("no time"), days: dayWords(s.days) }) }));
  if (spec.obligations.length) starts.push({ key: "obligations", icon: "bell", name: t("What people owe"), about: spec.obligations.join(", ") });
  spec.reports.forEach((source, i) => starts.push({ key: `report:${i}`, icon: "report", name: t("A report"), about: t("on {source}", { source }) }));
  const tools: Step[] = [...new Set(Object.values(spec.tools).flat())].map((n): Step => {
    const tool = offered.get(n);
    if (!tool) return { key: `tool:${n}`, icon: "tool", name: n, tone: "refused" as const, slot: "tools" as const, about: t("not one of the scenario's tools") };
    const kind = risk(asTool(tool));
    return { key: `tool:${n}`, icon: "tool", name: n, tone: kind, slot: "tools" as const,
             about: tool.changes ? t("changes {action}", { action: tool.changes }) : RISK_NAMES[kind].toLowerCase() };
  }).sort((a, b) => ORDER.indexOf(a.tone as Risk) - ORDER.indexOf(b.tone as Risk));
  const own = abilities().filter(([key]) => has(spec, key));
  const model = spec.model || t("no model");
  return {
    starts,
    agent: { key: "agent", icon: "agent", name, problems: problems || undefined,
             about: plan.parts.length ? t("{model}, {levels}, in {parts}", { model, levels: levels(spec.autonomy), parts: and(plan.parts) })
               : `${model}, ${levels(spec.autonomy)}` },
    end: { key: "reply", icon: "message", name: t("Reply"), about: t("to whoever it acts for"), tone: "own" },
    hanging: [
      { key: "model", icon: "model", name: t("Model"), about: spec.model || t("none yet"), slot: "model" },
      { key: "checks", icon: "shield", name: t("a5s's checks"), about: t("policy, need-to-know, limits"), tone: "own", slot: "checks" },
      ...tools,
      ...(own.length ? [{ key: "own", icon: "agent", name: t("a5s's own"), tone: "own" as const, slot: "tools" as const,
                          about: own.length > 1 ? t("{ability} and {more}", { ability: own[0][1].toLowerCase(), more: plural(own.length - 1, "more", "more") })
                            : own[0][1].toLowerCase() }] : []),
      ...plan.asks.map((id): Step => {  // the instances its first instance may ask, as planned
        const asked = offer.askable.find((a) => a.id === id);
        return { key: `ask:${id}`, icon: "agent", name: id, tone: "agent", slot: "tools",
                 about: !asked ? t("asks it") : asked.parts.length ? t("asks it: the {agent}, in {parts}", { agent: asked.agent, parts: and(asked.parts) })
                   : t("asks it: the {agent}", { agent: asked.agent }) };
      }),
    ],
  };
}

// The parts to add, on the left

function Picker({ spec, offer, add, ability, start, owe, report }: { spec: Spec; offer: Offer; add: (tool: Offered) => void;
  ability: (key: Ability, on: boolean) => void; start: (what: "schedule" | "messages") => void;
  owe: (kind: string) => void; report: (kind: string) => void }) {
  const [find, setFind] = useState("");
  const given = new Set(Object.values(spec.tools).flat());
  const words = find.trim().toLowerCase();
  const left = offer.tools.filter((t) => !given.has(t.name)
    && (!words || `${t.name} ${t.description ?? ""}`.toLowerCase().includes(words)));
  const addable = abilities().filter(([key, label]) => !has(spec, key) && (!words || label.toLowerCase().includes(words)));
  return (
    <section className="fd-palette" aria-label={t("What to add")}>
      <input type="search" id="pick-find" placeholder={t("Find a tool")} aria-label={t("Find a tool")} value={find}
             onChange={(e) => setFind(e.target.value)} />
      {ORDER.map((kind) => {
        const these = left.filter((t) => risk(asTool(t)) === kind);
        if (!these.length) return null;
        return (
          <div key={kind} className="fd-group">
            <p className="label">{RISK_NAMES[kind]}</p>
            {these.map((tool) => (
              <button key={tool.name} type="button" className="fd-part" draggable data-tool={tool.name}
                      title={tool.description ?? tool.name}
                      onDragStart={(e) => { e.dataTransfer.setData(DRAG, tool.name); e.dataTransfer.effectAllowed = "copy"; }}
                      onClick={() => add(tool)}>
                <span className={`fd-type ${kind}`}><Icon name="tool" /></span>
                <span className="fd-text"><span className="mono"><span className="hidden">{t("Add")} </span>{breakable(tool.name)}</span>
                  {tool.description && <span className="fd-about">{tool.description}</span>}</span>
              </button>
            ))}
          </div>
        );
      })}
      {!left.length && !words && <p className="note">{t("It has each of the scenario's tools.")}</p>}
      {addable.length > 0 && (
        <div className="fd-group">
          <p className="label">{t("a5s's own")}</p>
          {addable.map(([key, label, does]) => (
            <button key={key} type="button" className="fd-part" data-ability={key} title={t("It {does}.", { does })}
                    onClick={() => ability(key, true)}>
              <span className="fd-type own"><Icon name="agent" /></span>
              <span className="fd-text"><span><span className="hidden">{t("Add")} </span>{label}</span><span className="fd-about">{t("It {does}.", { does })}</span></span>
            </button>
          ))}
        </div>
      )}
      {!words && (
        <div className="fd-group">
          <p className="label">{t("What starts it")}</p>
          <button type="button" className="fd-part" id="add-schedule" onClick={() => start("schedule")}>
            <span className="fd-type"><Icon name="clock" /></span><span className="fd-text"><span><span className="hidden">{t("Add")} </span>{t("A schedule")}</span>
              <span className="fd-about">{t("It works on its own, at times you set.")}</span></span>
          </button>
          {!spec.triggers.some((trigger) => trigger.kind === "message") && (
            <button type="button" className="fd-part" id="add-messages" onClick={() => start("messages")}>
              <span className="fd-type"><Icon name="message" /></span><span className="fd-text"><span><span className="hidden">{t("Add")} </span>{t("A message")}</span>
                <span className="fd-about">{t("People write to it.")}</span></span>
            </button>
          )}
          {(offer.owed ?? []).filter((kind) => !spec.obligations.includes(kind)).map((kind) => (
            <button key={kind} type="button" className="fd-part" data-owed={kind} onClick={() => owe(kind)}>
              <span className="fd-type"><Icon name="bell" /></span><span className="fd-text"><span><span className="hidden">{t("Add")} </span>{t("What people owe, in the {kind}", { kind })}</span>
                <span className="fd-about">{t("It reminds its people of what falls due.")}</span></span>
            </button>
          ))}
          {(offer.owed ?? []).filter((kind) => !spec.reports.includes(kind)).map((kind) => (
            <button key={`report-${kind}`} type="button" className="fd-part" data-report={kind} onClick={() => report(kind)}>
              <span className="fd-type"><Icon name="report" /></span><span className="fd-text"><span><span className="hidden">{t("Add")} </span>{t("A daily report on the {kind}", { kind })}</span>
                <span className="fd-about">{t("Each working day, it tells each person it serves what changed in their own.")}</span></span>
            </button>
          ))}
        </div>
      )}
      <p className="wb-hint">{t("Drag a tool onto the canvas, or press Enter on one to add it.")}</p>
    </section>
  );
}

// What's chosen, on the right

type Edit = (next: string, said?: string) => void;

function Head({ icon, tone, title, kind, children }: { icon: string; tone?: string; title: string; kind: string;
  children?: ReactNode }) {
  return (
    <div className="wb-head">
      <div className={`flow-step ${tone ?? ""}`}><div className="flow-box"><Icon name={icon} /></div></div>
      <div>
        <h2 id="inspector-title" tabIndex={-1}>{title}</h2>
        <p>{kind}</p>
      </div>
      {children}
    </div>
  );
}

function Follows({ lines, title = t("What follows") }: { lines: string[]; title?: string }) {
  return (
    <div className="wb-well follows">
      <Icon name="shield" />
      <div><strong>{title}</strong><ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul></div>
    </div>
  );
}

function ToolPanel({ name, text, spec, offer, edit, kindOf, done }: { name: string; text: string; spec: Spec; offer: Offer;
  edit: Edit; kindOf: (n: string) => string; done: () => void }) {
  const tool = offer.tools.find((each) => each.name === name);
  const away = () => {
    const last = tool?.changes && changers(spec, offer).length === 1;
    edit(withTool(text, name, false, kindOf(name), kindOf),
         last ? t("Took {tool} away. It changes no records now, so nobody decides anything it does.", { tool: name })
           : t("Took {tool} away.", { tool: name }));
    done();
  };
  return (
    <>
      <Head icon="tool" tone={tool ? risk(asTool(tool)) : "refused"} title={name} kind={tool ? t("the scenario's tool") : t("not the scenario's")}>
        {tool && <ToolBadges tool={asTool(tool)} />}
      </Head>
      {!tool ? <p className="problem">{t("The scenario hasn't got a tool called {tool}, so nothing would release it: take it away, or ask the scenario's engineers for it.", { tool: name })}</p>
        : <>
            {tool.description && <p className="note">{tool.description}</p>}
            <Follows lines={toolLines(tool, spec, offer)} />
          </>}
      <div className="wb-actions"><button type="button" className="danger" id="take-away" onClick={away}>{t("Take {tool} away", { tool: name })}</button></div>
    </>
  );
}

function SchedulePanel({ index, text, spec, edit, done }: { index: number; text: string; spec: Spec; edit: Edit; done: () => void }) {
  const schedule = spec.schedules[index];
  const [at, setAt] = useState(schedule ? schedule.at.join(", ") : "");  // as typed, while it's typed
  if (!schedule) return null;
  const set = (next: Partial<Schedule>, said?: string) => edit(withSchedule(text, { ...schedule, ...next }, index), said);
  const day = (d: string, on: boolean) => {
    const days = on ? [...schedule.days, d] : schedule.days.filter((x) => x !== d);
    set({ days }, scheduleLines({ ...schedule, days }, spec)[0]);
  };
  return (
    <>
      <Head icon="clock" title={schedule.name || t("A schedule")} kind={t("a schedule: it works on its own")} />
      <label className="wb-field"><span className="wb-label">{t("Its name")}</span>
        <input id="schedule-name" value={schedule.name} onChange={(e) => set({ name: e.target.value })} />
        <span className="wb-hint">{t("Lowercase letters, digits and hyphens.")}</span></label>
      <label className="wb-field"><span className="wb-label">{t("At")}</span>
        <input id="schedule-at" value={at} inputMode="numeric" onChange={(e) => {
          setAt(e.target.value);
          set({ at: e.target.value.split(/[\s,]+/).filter(Boolean) });
        }} />
        <span className="wb-hint">{t("Such as 09:00, 13:30, in its instance owner's time zone.")}</span></label>
      <fieldset className="wb-field">
        <legend className="wb-label">{t("On")}</legend>
        <div className="choices inline">{DAYS.map((d) => (
          <label key={d} className="choice"><input type="checkbox" checked={schedule.days.includes(d)}
                                                onChange={(e) => day(d, e.target.checked)} /> {d}</label>
        ))}</div>
      </fieldset>
      <label className="wb-field"><span className="wb-label">{t("What a5s asks it each time")}</span>
        <textarea id="schedule-task" rows={3} value={schedule.task} onChange={(e) => set({ task: e.target.value })} /></label>
      <Follows lines={scheduleLines(schedule, spec)} />
      <div className="wb-actions"><button type="button" className="danger" id="take-away" onClick={() => {
        edit(withoutSchedule(text, index), t("Took the schedule {name} away.", { name: schedule.name }));
        done();
      }}>{t("Take it away")}</button></div>
    </>
  );
}

function MessagesPanel({ text, spec, edit, done }: { text: string; spec: Spec; edit: Edit; done: () => void }) {
  const known = [...new Set([...Object.keys(CHANNEL_WORDS), ...spec.channels])];
  const channel = (c: string, on: boolean) => {
    const channels = on ? [...spec.channels, c] : spec.channels.filter((x) => x !== c);
    edit(withWords(text, ["channels"], channels), messageLines({ ...spec, channels })[0]);
  };
  const about = spec.triggers.find((trigger) => trigger.kind === "message")?.about;
  return (
    <>
      <Head icon="message" title={t("A message")} kind={about ?? t("people write to it")} />
      <fieldset className="wb-field">
        <legend className="wb-label">{t("On")}</legend>
        <div className="choices inline">{known.map((c) => (
          <label key={c} className="choice"><input type="checkbox" checked={spec.channels.includes(c)}
                                                onChange={(e) => channel(c, e.target.checked)} /> {CHANNEL_WORDS[c] ?? c}</label>
        ))}</div>
      </fieldset>
      <Follows lines={messageLines(spec)} />
      <div className="wb-actions"><button type="button" className="danger" id="take-away" onClick={() => {
        edit(withMessages(text, false), t("People can no longer write to it: only what else starts its runs does."));
        done();
      }}>{t("Stop people writing to it")}</button></div>
    </>
  );
}

function AgentPanel({ name, text, spec, offer, edit, ability, planning }: { name: string; text: string; spec: Spec; offer: Offer;
  edit: Edit; ability: (key: Ability, on: boolean) => void; planning: Planning }) {
  const level = (end: "start" | "max", n: number) => {
    const next = { ...spec, autonomy: { ...spec.autonomy, [end]: n } };
    edit(withValue(text, ["autonomy", end], writtenLevel(n)), levelLines(next).join(" "));  // by name
  };
  const models = [...new Set([spec.model, ...offer.models].filter(Boolean))];
  return (
    <>
      <Head icon="agent" tone="agent" title={name} kind={t("the agent, {levels}", { levels: levels(spec.autonomy) })} />
      <label className="wb-field"><span className="wb-label">{t("Works for")}</span>
        <input id="works-for" value={spec.works_for} onChange={(e) => edit(withValue(text, ["works_for"], e.target.value))} /></label>
      <label className="wb-field"><span className="wb-label">{t("What it does")}</span>
        <textarea id="does" rows={4} value={spec.does} onChange={(e) => edit(withValue(text, ["does"], e.target.value))} /></label>
      <label className="wb-field"><span className="wb-label">{t("Model")}</span>
        <select id="model" value={spec.model} onChange={(e) => edit(withValue(text, ["model"], e.target.value), t("Its model is {model} now.", { model: e.target.value }))}>
          {models.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span className="wb-hint">{t("Of those the deployment approves.")}</span></label>
      <div className="wb-pair">
        <label className="wb-field"><span className="wb-label">{t("Where it starts")}</span>
          <select id="level-start" value={spec.autonomy.start} onChange={(e) => level("start", Number(e.target.value))}>
            {[0, 1].map((n) => <option key={n} value={n}>{levelName(n)}</option>)}
          </select></label>
        <label className="wb-field"><span className="wb-label">{t("The most it may do")}</span>
          <select id="level-max" value={spec.autonomy.max} onChange={(e) => level("max", Number(e.target.value))}>
            {[0, 1, 2].map((n) => <option key={n} value={n}>{levelName(n)}</option>)}
          </select></label>
      </div>
      <Follows lines={levelLines(spec)} />
      <PlanFields {...planning} />
      <OwnAbilities spec={spec} ability={ability} />
    </>
  );
}

type Planning = { plan: Plan; offer: Offer; part: (part: string, on: boolean) => void;
                 serve: (who: string, on: boolean) => void; ask: (instance: string, on: boolean) => void };

/** Its first instance, as its authors mean to ask for it: where it would work, whom it would
 * serve, and which instances it could ask. The settings decide each, once its parts' owners
 * approve them; the plan is what putting it to work starts from. */
function PlanFields({ plan, offer, part, serve, ask }: Planning) {
  return (
    <section className="wb-section" aria-labelledby="plan-title">
      <h2 id="plan-title">{t("Its first instance, as you plan it")}</h2>
      <p className="wb-hint">{t("Kept with the draft, and never in force: where it works, and for whom, are the settings', which its parts' owners approve once its release is signed. Putting it to work starts from this.")}</p>
      <fieldset className="wb-field">
        <legend className="wb-label">{t("Works in")}</legend>
        {offer.parts.length ? <div className="choices inline">{offer.parts.map((p) => (
          <label key={p.name} className="choice"><input type="checkbox" checked={plan.parts.includes(p.name)}
                                                     onChange={(e) => part(p.name, e.target.checked)} /> {p.name}</label>
        ))}</div> : <span className="wb-hint">{t("No parts the settings know, so none, and an instance approver approves it.")}</span>}
      </fieldset>
      <fieldset className="wb-field">
        <legend className="wb-label">{t("Serves, a few people first")}</legend>
        {offer.servable.map((s) => (
          <label key={s.id} className="choice"><input type="checkbox" checked={plan.serves.includes(s.id)}
                                                   onChange={(e) => serve(s.id, e.target.checked)} /> {s.name}</label>
        ))}
        <span className="wb-hint">{t("Those the settings name already, and you.")}</span>
      </fieldset>
      {offer.askable.length > 0 && (
        <fieldset className="wb-field">
          <legend className="wb-label">{t("May ask")}</legend>
          {offer.askable.map((a) => (
            <label key={a.id} className="choice"><input type="checkbox" checked={plan.asks.includes(a.id)}
                                                     onChange={(e) => ask(a.id, e.target.checked)} /> {a.id}</label>
          ))}
          <span className="wb-hint">{t("Instances you may see at work.")}</span>
        </fieldset>
      )}
    </section>
  );
}

function AskPanel({ id, offer, ask }: { id: string; offer: Offer; ask: (instance: string, on: boolean) => void }) {
  const asked = offer.askable.find((a) => a.id === id);
  return (
    <>
      <Head icon="agent" tone="agent-tone" title={id} kind={asked ? t("an instance of the {agent}", { agent: asked.agent }) : t("an instance")} />
      <Follows lines={[
        t("Its first instance may ask {id} questions, for the people it acts for, once the settings name it: the owners of its parts approve that with the rest of it.", { id }),
        t("{id} answers only with what those people may see, and its answers come back as what {id} said, never as records.", { id }),
      ]} />
      <div className="wb-actions"><button type="button" className="danger" id="take-away" onClick={() => ask(id, false)}>
        {t("Stop it asking {id}", { id })}</button></div>
    </>
  );
}

function OwnAbilities({ spec, ability }: { spec: Spec; ability: (key: Ability, on: boolean) => void }) {
  return (
    <fieldset className="wb-field">
      <legend className="wb-label">{t("a5s's own abilities")}</legend>
      {abilities().map(([key, label, does]) => (
        <label key={key} className="choice">
          <input type="checkbox" checked={has(spec, key)} onChange={(e) => ability(key, e.target.checked)} />
          <span><strong>{label}</strong> <span className="faint">{t("It {does}.", { does })}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

function OwnPanel({ text, spec, edit, ability }: { text: string; spec: Spec; edit: Edit; ability: (key: Ability, on: boolean) => void }) {
  return (
    <>
      <Head icon="agent" tone="own" title={t("a5s's own")} kind={t("a5s's tools, held to its own rules")} />
      <OwnAbilities spec={spec} ability={ability} />
      {spec.tasks && (
        <div className="wb-pair">
          <label className="wb-field"><span className="wb-label">{t("Tokens a task may spend")}</span>
            <input id="task-tokens" type="number" min={10000} step={10000} value={spec.tasks.budget_tokens}
                   onChange={(e) => edit(withValue(text, ["tasks", "budget_tokens"], Number(e.target.value)))} /></label>
          <label className="wb-field"><span className="wb-label">{t("Days a task has")}</span>
            <input id="task-days" type="number" min={1} max={30} value={spec.tasks.days}
                   onChange={(e) => edit(withValue(text, ["tasks", "days"], Number(e.target.value)))} /></label>
        </div>
      )}
    </>
  );
}

function ModelPanel({ text, spec, offer, edit }: { text: string; spec: Spec; offer: Offer; edit: Edit }) {
  const judge = (alias: string) => {
    if (!alias) edit(without(text, ["evaluation"]), t("No model judges its work now: people's grades alone."));
    else edit(spec.evaluation ? withValue(text, ["evaluation", "judge"], alias) : withMap(text, ["evaluation"], { judge: alias, rubric: "" }),
              t("{model} judges each sample of its work beside people's grades, never instead of them: no verdict changes what an agent may do.", { model: alias }));
  };
  const models = [...new Set([spec.model, ...offer.models].filter(Boolean))];
  return (
    <>
      <Head icon="model" title={t("Model")} kind={t("through a5s's gateway")} />
      <label className="wb-field"><span className="wb-label">{t("Its model")}</span>
        <select id="design-model" value={spec.model} onChange={(e) => edit(withValue(text, ["model"], e.target.value), t("Its model is {model} now.", { model: e.target.value }))}>
          {models.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span className="wb-hint">{t("Of those the deployment approves, for the data the settings say it may see.")}</span></label>
      <label className="wb-field"><span className="wb-label">{t("Its judge, beside people's grades")}</span>
        <select id="design-judge" value={spec.evaluation?.judge ?? ""} onChange={(e) => judge(e.target.value)}>
          <option value="">{t("none: people's grades alone")}</option>
          {[...new Set([...(spec.evaluation ? [spec.evaluation.judge] : []), ...offer.models])].map((m) => <option key={m} value={m}>{m}</option>)}
        </select></label>
      {spec.evaluation && (
        <label className="wb-field"><span className="wb-label">{t("What a right change is, for its judge")}</span>
          <textarea id="design-rubric" rows={3} value={spec.evaluation.rubric}
                    onChange={(e) => edit(withValue(text, ["evaluation", "rubric"], e.target.value))} />
          <span className="wb-hint">{t("In its owners' words. The judge never changes what an agent may do: people's grades do.")}</span></label>
      )}
    </>
  );
}

function ChecksPanel({ text, spec, offer, edit }: { text: string; spec: Spec; offer: Offer; edit: Edit }) {
  const number = (path: string[]) => (e: { target: { value: string } }) => edit(withValue(text, path, Number(e.target.value)));
  return (
    <>
      <Head icon="shield" tone="own" title={t("a5s's checks")} kind={t("every call to a tool passes them")} />
      <p className="note">{t("Its tool must be its release's, pinned as the scenario has it; the record in a part its instance works in, and one everyone the run acts for may see; and a change waits, or is made, as what it may do there and the scenario's limits say.")}</p>
      <div className="wb-pair">
        <label className="wb-field"><span className="wb-label">{t("Tokens a run may spend")}</span>
          <input id="budget-run" type="number" min={1000} step={10000} value={spec.budget.per_run} onChange={number(["budget", "per_run"])} /></label>
        <label className="wb-field"><span className="wb-label">{t("For each person a day")}</span>
          <input id="budget-person" type="number" min={1000} step={100000} value={spec.budget.per_person_per_day}
                 onChange={number(["budget", "per_person_per_day"])} /></label>
      </div>
      <label className="wb-field"><span className="wb-label">{t("Tokens of its conversation each run is given")}</span>
        <input id="budget-context" type="number" min={1000} step={1000} value={spec.context.budget_tokens}
               onChange={number(["context", "budget_tokens"])} /></label>
      <Follows title={t("Its limits")} lines={limitLines(spec, offer)} />
    </>
  );
}

function ReplyPanel({ spec }: { spec: Spec }) {
  return (
    <>
      <Head icon="message" tone="own" title={t("Reply")} kind={t("what each run ends in")} />
      <p>{spec.schedules.length
        ? t("Each run writes only to the people it acts for, in the conversation it was started in, and a run a schedule starts acts for nobody, so it writes to nobody. a5s checks what it sends: links only to the scenario's records, and any value it worked out itself marked as its own.")
        : t("Each run writes only to the people it acts for, in the conversation it was started in. a5s checks what it sends: links only to the scenario's records, and any value it worked out itself marked as its own.")}</p>
    </>
  );
}

function OtherPanel({ chosen, spec, away }: { chosen: string; spec: Spec; away: () => void }) {
  const [kind, at] = chosen.split(":");
  const [title, said] = kind === "obligations" ? [t("What people owe"), t("It reminds its people of what falls due in the {kinds}, each run acting for the person it's for.",
                                                                          { kinds: and(spec.obligations) })]
    : kind === "report" ? [t("A report"), t("Once a day, it tells each person it serves what changed in their own {kind}, in their digest: code works the facts out, and the run, acting for them, puts them into words.",
                                            { kind: spec.reports[Number(at)] })]
    : [spec.triggers[Number(at)]?.kind ?? t("A start"), spec.triggers[Number(at)]?.about ?? ""];
  return (
    <>
      <Head icon={kind === "report" ? "report" : kind === "obligations" ? "bell" : "run"} title={title} kind={t("what starts its runs")} />
      <p>{said}</p>
      {kind === "obligations" || kind === "report"
        ? <div className="wb-actions"><button type="button" className="danger" id="take-away" onClick={away}>{t("Take it away")}</button></div>
        : <p className="note">{t("Change it under Files, in agent.yaml.")}</p>}
    </>
  );
}

/** What follows from it all, as it stands: who decides its changes, who signs, its limits. */
export function Consequences({ spec, offer, signers, plan }: { spec: Spec; offer: Offer; signers: Signer[] | null; plan: Plan }) {
  const changing = changers(spec, offer);
  const planned = plan.parts.length ? offer.parts.filter((p) => plan.parts.includes(p.name)) : offer.parts;
  const given = new Set(Object.values(spec.tools).flat());
  const alone = offer.tools.filter((tool) => given.has(tool.name) && !tool.changes && (tool.destructive || tool.sends_outside));
  const actions = [...new Set(changing.map((tool) => tool.changes ?? ""))];
  const waits = { actions: and(actions) };
  const serving = plan.serves.length ? and(servedBy(plan, offer)) : "";
  const asking = plan.asks.length ? and(plan.asks) : "";
  return (
    <>
      <section id="decides" aria-labelledby="decides-title">
        <h2 id="decides-title">{t("Who decides its changes")}</h2>
        {!changing.length ? <p>{t("Nobody: it changes no records a part decides.")}</p>
          : spec.autonomy.max < 1 ? <p>{t("Nobody yet: its release lets it read only, so a5s refuses every change it asks for, {actions}.", waits)}</p> : (
          <>
            <p>{plan.parts.length
              ? (spec.autonomy.max < 2
                ? t("Each change it asks for, {actions}, waits for a yes from a decider of its record's part, in the parts you plan its first instance in, since its release lets it ask first at most:", waits)
                : t("Unless it acts on its own, each change it asks for, {actions}, waits for a yes from a decider of its record's part, in the parts you plan its first instance in:", waits))
              : (spec.autonomy.max < 2
                ? t("Each change it asks for, {actions}, waits for a yes from a decider of its record's part, since its release lets it ask first at most:", waits)
                : t("Unless it acts on its own, each change it asks for, {actions}, waits for a yes from a decider of its record's part:", waits))}</p>
            {planned.length
              ? <ul className="plain">{planned.map((p) => <li key={p.name}><strong>{p.name}</strong>: {deciders(p)}</li>)}</ul>
              : <p className="note">{t("its owners and their delegates, as the settings and the directory name them.")}</p>}
          </>
        )}
        {alone.length > 0 && <p>{t("{tools} run only where it acts on its own, which only the settings give.", { tools: and(alone.map((tool) => tool.name)) })}</p>}
      </section>
      <section id="to-work" aria-labelledby="to-work-title">
        <h2 id="to-work-title">{t("Who puts it to work")}</h2>
        <p>{plan.parts.length
          ? t("Its parts' owners approve it, as a version of the settings, once its release is signed: {owners}.", { owners: planned.map((p) =>
              t("{who}, for {part}", { who: p.owners.length ? and(p.owners) : t("nobody yet"), part: p.name })).join("; ") })
          : offer.no_part.length
            ? t("With no part, an instance approver approves it, as a version of the settings, once its release is signed: {approvers}.", { approvers: and(offer.no_part) })
            : t("Its parts' owners approve it, as a version of the settings, once its release is signed.")}</p>
        {(plan.serves.length > 0 || plan.asks.length > 0) && (
          <p className="note">{plan.serves.length && plan.asks.length ? t("As planned, serving {who}, and asking {instances}.", { who: serving, instances: asking })
            : plan.serves.length ? t("As planned, serving {who}.", { who: serving }) : t("As planned, asking {instances}.", { instances: asking })}</p>
        )}
      </section>
      <section id="signers" aria-labelledby="signers-title">
        <h2 id="signers-title">{t("Who signs its release")}</h2>
        {signers === null && <p className="note">{t("Once its definition loads.")}</p>}
        {signers?.length === 0 && <p className="note">{t("Nobody more than for any release: it changes nothing of what's released here.")}</p>}
        {signers && signers.length > 0 && (
          <ul className="plain">{signers.map((s) => (
            <li key={s.role} data-role={s.role}><strong>{s.who}</strong>{s.held_by?.length ? `: ${and(s.held_by, "or")}` : ""}
              <span className="faint">{s.held_by?.length === 0 ? t(", because {why}.", { why: s.why }) : t(", because {why}", { why: s.why })}</span>
              {s.held_by?.length === 0 && (  // a new agent's owner, before the directory names one
                <span className="problem"> {t("Nobody holds that role in the directory yet: its release can't be approved until the directory names someone.")}</span>
              )}</li>
          ))}</ul>
        )}
        <p className="wb-hint">{t("As")} <span className="mono">a5s release</span> {t("works it out, from what it changes of the agents released here. The pull request it's published as names them.")}</p>
      </section>
      <section id="limits" aria-labelledby="limits-title">
        <h2 id="limits-title">{t("Its limits")}</h2>
        <ul className="plain">{[...levelLines(spec), ...limitLines(spec, offer)].map((l) => <li key={l}>{l}</li>)}</ul>
      </section>
    </>
  );
}

// The list: the same steps, row by row, each opening in place

function DesignList({ flow, chosen, pick, close, panel, adding, picker, views, after }: { flow: Flow; chosen: string | null;
  pick: (key: string, keyboard: boolean) => void; close: (key: string) => void; panel: (key: string) => ReactNode;
  adding: boolean; picker: ReactNode; views: ReactNode; after: ReactNode }) {
  const row = (step: Step) => (
    <li key={step.key}>
      <button type="button" className={`flow-row ${step.tone ?? ""}`} aria-expanded={chosen === step.key} data-row={step.key}
              onClick={(e) => pick(step.key, e.detail === 0)}>
        <Icon name={step.icon} />
        <span className="flow-row-text"><span className="flow-row-name">{step.name}</span>
          {step.about && <span className="flow-row-about">{step.about}</span>}</span>
        {!!step.problems && <span className="badge bad">{plural(step.problems, "problem")}</span>}
      </button>
      {chosen === step.key && (  // its settings, in place; Escape closes them
        <div className="flow-inline" onKeyDown={(e) => { if (e.key === "Escape") close(step.key); }}>{panel(step.key)}</div>
      )}
    </li>
  );
  return (
    <div className="flow-listing" onKeyDown={(e) => {
      const at = (e.target as HTMLElement).closest("[data-row]")?.getAttribute("data-row");
      if (e.key === "Escape" && at && chosen === at) close(at);
    }}>
      {views}
      <section aria-labelledby="list-starts"><h2 id="list-starts">{t("What starts its runs")}</h2><ul>{flow.starts.map(row)}</ul></section>
      <section aria-labelledby="list-agent"><h2 id="list-agent">{t("The agent")}</h2>
        <ul>{[flow.agent, ...(flow.end ? [flow.end] : [])].map(row)}</ul></section>
      <section aria-labelledby="list-hangs"><h2 id="list-hangs">{t("What it works with")}</h2><ul>{flow.hanging.map(row)}</ul></section>
      <section aria-labelledby="list-add">
        <h2 id="list-add">{t("Add to it")}</h2>
        <button type="button" aria-expanded={adding} id="list-adding" onClick={(e) => pick("add", e.detail === 0)}>
          <Icon name="plus" /> {t("Add a tool, an ability or a start")}</button>
        {adding && <div className="flow-inline">{picker}</div>}
      </section>
      {after}
    </div>
  );
}

export function Designer({ name, files, offer, signers, problems, change, plan, changePlan, overview, tryIt, asked }: {
  name: string;
  files: Files;
  offer: Offer;
  signers: Signer[] | null;
  problems: number;
  change: (files: Files) => void;
  plan: Plan;  // its first instance, as its authors mean to ask for it
  changePlan: (plan: Plan, files?: Files) => void;
  overview: ReactNode;  // the draft's own, with nothing chosen: where it stands, and what stops its release
  tryIt: ReactNode;  // the canvas's one thing to do, at its foot
  asked: number;  // each time someone asks to see what stops its release
}) {
  const [shown, setShown] = useView(SHOWN);
  const [chosen, setChosen] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [focus, setFocus] = useState(0);  // each time the inspector should take the keyboard's focus
  const [toProblems, setToProblems] = useState(0);
  useEffect(() => {  // the draft as a whole, to see what stops its release
    if (!asked) return;
    setChosen(null);
    setToProblems((n) => n + 1);
  }, [asked]);
  useEffect(() => {
    if (toProblems) document.getElementById("problems")?.focus();
  }, [toProblems]);
  const before = useRef<Signer[] | null | undefined>(undefined);
  useEffect(() => {  // who signs, once the change is kept: what it made follow for its release
    const was = before.current;
    before.current = signers;
    if (!was || !signers) return;
    const had = new Set(was.map((s) => s.role));
    const now = new Set(signers.map((s) => s.role));
    const words = [...signers.filter((s) => !had.has(s.role)).map((s) => t("Now {who} must sign its release: {why}.", { who: s.who, why: s.why })),
                   ...was.filter((s) => !now.has(s.role)).map((s) => t("{who} needn't sign it now.", { who: `${s.who[0].toUpperCase()}${s.who.slice(1)}` }))];
    if (words.length) setNotice((said) => `${said} ${words.join(" ")}`.trim());
  }, [signers]);
  useEffect(() => {
    if (focus) document.getElementById(shown === "list" && !chosen ? "list-adding" : "inspector-title")?.focus();
  }, [focus]);  // eslint-disable-line react-hooks/exhaustive-deps

  const text = files["agent.yaml"] ?? "";
  const spec = read(text);
  if (!spec) return <div className="wb-body whole"><div className="wb-view"><p className="problem">{new Unreadable().message}</p></div></div>;
  const kinds = new Map(offer.tools.map((tool) => [tool.name, risk(asTool(tool))]));
  const kindOf = (n: string) => kinds.get(n) ?? "reads";
  const edit: Edit = (next, said) => {
    if (next === text) return;
    change({ ...files, "agent.yaml": next });
    if (said !== undefined) setNotice(said);
  };
  const choose = (key: string | null, keyboard = false) => {
    setChosen(key);
    if (keyboard) setFocus((n) => n + 1);
  };
  const add = (tool: Offered) => {
    if (Object.values(spec.tools).flat().includes(tool.name)) return;
    edit(withTool(text, tool.name, true, kindOf(tool.name), kindOf), t("Added {tool}. {follows}", { tool: tool.name, follows: toolLines(tool, spec, offer)[0] }));
    choose(`tool:${tool.name}`, true);
  };
  const ability = (key: Ability, on: boolean) => {
    const next = key === "tasks" ? (on ? withMap(text, ["tasks"], { budget_tokens: 400000, days: 3 }) : without(text, ["tasks"]))
      : key === "reminders" ? withValue(text, ["reminders"], on)
      : PREFERENCES.includes(key) ? withWords(text, ["preferences"], on ? [...new Set([...spec.preferences, key])]
        : spec.preferences.filter((p) => p !== key))
      : withValue(text, ["context", key], on);
    const [added, gone] = turned()[key];
    edit(next, on ? added : gone);
    if (on) choose("own", true);
  };
  const start = (what: "schedule" | "messages") => {
    if (what === "messages") {
      edit(withMessages(text, true), messageLines(spec)[0]);
      choose("messages", true);
      return;
    }
    const names = new Set(spec.schedules.map((s) => s.name));
    let n = 1;
    while (names.has(n === 1 ? "morning" : `morning-${n}`)) n += 1;
    const schedule = { ...FIRST_SCHEDULE, name: n === 1 ? "morning" : `morning-${n}` };
    edit(withSchedule(text, schedule, null), t("Added a schedule, {name}. {follows}", { name: schedule.name, follows: scheduleLines(schedule, spec)[0] }));
    choose(`schedule:${spec.schedules.length}`, true);
  };
  const owe = (kind: string) => {
    edit(withWords(text, ["obligations"], [...new Set([...spec.obligations, kind])]),
         t("Now it reminds its people of what falls due in the {kind}, each run acting for the person it's for.", { kind }));
    choose("obligations", true);
  };
  const report = (kind: string) => {
    edit(withReports(text, [...spec.reports, kind]),
         t("Each working day, it tells each person it serves what changed in their own {kind}, in their digest.", { kind }));
    choose(`report:${spec.reports.length}`, true);
  };
  const remove = (key: string) => {  // from the keyboard, as n8n takes a step away
    const [kind, rest] = [key.split(":")[0], key.slice(key.indexOf(":") + 1)];
    if (kind === "tool") {
      edit(withTool(text, rest, false, kindOf(rest), kindOf), t("Took {tool} away.", { tool: rest }));
      choose(null, true);
    } else if (kind === "schedule") {
      edit(withoutSchedule(text, Number(rest)), t("Took the schedule {name} away.", { name: spec.schedules[Number(rest)]?.name ?? "" }));
      choose(null, true);
    } else if (kind === "obligations") {
      edit(withWords(text, ["obligations"], []), t("It no longer reminds its people of what falls due."));
      choose(null, true);
    } else if (kind === "report") {
      const gone = spec.reports[Number(rest)];
      edit(withReports(text, spec.reports.filter((_, i) => i !== Number(rest))),
           t("It no longer reports on the {kind} each day.", { kind: gone }));
      choose(null, true);
    }
  };
  const pick = (key: string, keyboard: boolean) => {
    if (key === "add" || key === "add-tool" || key === "add-start") {
      if (shown === "list") choose(chosen === "add" ? null : "add", keyboard);
      else {
        choose(null);
        document.getElementById("pick-find")?.focus();
      }
      return;
    }
    choose(shown === "list" && chosen === key ? null : key, keyboard);
  };
  const done = () => choose(null, true);
  const toggled = (list: string[], one: string, on: boolean) => (on ? [...new Set([...list, one])] : list.filter((x) => x !== one));
  const planning: Planning = {
    plan, offer,
    part: (part, on) => {
      const parts = toggled(plan.parts, part, on);
      changePlan({ ...plan, parts });
      const rule = offer.parts.find((p) => p.name === part);
      setNotice(on && rule ? t("It would work first in {parts}: {deciders} would decide its changes there.", { parts: and(parts), deciders: deciders(rule) })
                   : on || parts.length ? t("It would work first in {parts}.", { parts: and(parts) }) : t("It would work in no part's records first."));
    },
    serve: (who, on) => {
      const serves = toggled(plan.serves, who, on);
      changePlan({ ...plan, serves });
      setNotice(serves.length ? t("It would serve {who} first.", { who: and(servedBy({ ...plan, serves }, offer)) }) : t("It would serve nobody yet."));
    },
    ask: (instance, on) => {
      const asks = toggled(plan.asks, instance, on);
      const enabling = on && !spec.context.agents;  // asking another agent is its release's to allow
      changePlan({ ...plan, asks }, enabling ? { ...files, "agent.yaml": withValue(text, ["context", "agents"], true) } : undefined);
      setNotice(!on ? t("It won't ask {instance}.", { instance })
        : enabling ? t("Its first instance may ask {instance}, once the settings name it. Its release now lets it ask other agents, those the settings name, so its release approver signs that.", { instance })
        : t("Its first instance may ask {instance}, once the settings name it.", { instance }));
      if (!on && chosen === `ask:${instance}`) choose(null, true);  // its own panel, gone with it
    },
  };
  const flow = flowOf(spec, name, offer, problems, plan);
  const panel = (key: string): ReactNode => {
    const [kind, rest] = [key.split(":")[0], key.slice(key.indexOf(":") + 1)];
    if (kind === "tool") return <ToolPanel key={key} name={rest} text={text} spec={spec} offer={offer} edit={edit} kindOf={kindOf} done={done} />;
    if (kind === "schedule") return <SchedulePanel key={key} index={Number(rest)} text={text} spec={spec} edit={edit} done={done} />;
    if (kind === "messages") return <MessagesPanel text={text} spec={spec} edit={edit} done={done} />;
    if (kind === "agent") return <AgentPanel name={name} text={text} spec={spec} offer={offer} edit={edit} ability={ability} planning={planning} />;
    if (kind === "ask") return <AskPanel key={key} id={rest} offer={offer} ask={planning.ask} />;
    if (kind === "own") return <OwnPanel text={text} spec={spec} edit={edit} ability={ability} />;
    if (kind === "model") return <ModelPanel text={text} spec={spec} offer={offer} edit={edit} />;
    if (kind === "checks") return <ChecksPanel text={text} spec={spec} offer={offer} edit={edit} />;
    if (kind === "reply") return <ReplyPanel spec={spec} />;
    return <OtherPanel chosen={key} spec={spec} away={() => remove(key)} />;
  };
  const known = chosen !== null && chosen !== "add"
    && [...flow.starts, flow.agent, ...(flow.end ? [flow.end] : []), ...flow.hanging].some((s) => s.key === chosen);
  const said = notice && <p className="wb-well notice" id="what-changed" role="status"><Icon name="check" /><span>{notice}</span></p>;
  const picker = <Picker spec={spec} offer={offer} add={add} ability={ability} start={start} owe={owe} report={report} />;
  const drop = (dragged: DataTransfer) => {
    const tool = offer.tools.find((each) => each.name === dragged.getData(DRAG));
    if (tool) add(tool);
    return Boolean(tool);
  };
  const listing = shown === "list";
  const close = (key: string) => {  // a row's settings closed, the keyboard back on its row
    setChosen(null);
    window.setTimeout(() => document.querySelector<HTMLElement>(`[data-row="${CSS.escape(key)}"]`)?.focus());
  };
  const views = <Views shown={shown} show={setShown} canvas={t("Canvas")} />;
  return (
    <div className={`wb-body ${listing ? "whole" : "designer"}`} id="designer">
      {!listing && picker}
      {listing ? (
        <DesignList flow={flow} chosen={chosen} pick={pick} close={close} panel={panel} adding={chosen === "add"} picker={picker}
                    views={views} after={<>{said}{overview}<Consequences spec={spec} offer={offer} signers={signers} plan={plan} /></>} />
      ) : (
        <FlowMap flow={flow} label={t("How it's wired")} chosen={known ? chosen : null} pick={pick} remove={remove} drop={drop}
                 stubs={[{ key: "add-tool", icon: "plus", name: t("Add a tool"), slot: "tools" },
                         { key: "add-start", icon: "plus", name: t("Add what starts it") }]}>
          <button type="button" className="flow-add" onClick={() => pick("add", true)}>{t("+ Add")}</button>
          <div className="flow-run">{tryIt}</div>
          <div className="flow-views">{views}</div>
        </FlowMap>
      )}
      {!listing && (
        <section className="wb-inspector" aria-label={known ? t("What's chosen") : t("The draft")}>
          {said}
          {known ? <>{panel(chosen as string)}<div className="wb-actions"><button type="button" className="link" onClick={() => choose(null, true)}>
            {t("The draft as a whole")}</button></div></>
            : <>{overview}<Consequences spec={spec} offer={offer} signers={signers} plan={plan} /></>}
        </section>
      )}
    </div>
  );
}
