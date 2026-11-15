// An agent's definition, agent.yaml, as the studio's forms and its designer read and change it.
// Each change is made to the document itself, so the file keeps its comments and layout as its
// author, or its template, wrote them: someone can start an agent here and finish it in an
// editor, or the other way round.

import { Document, isMap, isScalar, isSeq, parseDocument, Scalar, type YAMLMap, type YAMLSeq } from "yaml";

export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const WEEKDAYS = DAYS.slice(0, 5);
const DAY_NAMES: Record<string, string> = Object.fromEntries(DAYS.map((d, i) =>
  [["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][i], d]));

/** When an agent works on its own, as agent.yaml says it: its times, its days, as day names
 * such as mon, and what it's asked each time. */
export type Schedule = { name: string; at: string[]; days: string[]; task: string };

/** What a5s's own abilities an agent's runs may use, beyond the scenario's tools. */
export type Context = { budget_tokens: number; recall: boolean; documents: boolean; agents: boolean; notebook: boolean };

export type Spec = {
  works_for: string;
  does: string;
  model: string;
  autonomy: { start: number; max: number };
  tools: Record<string, string[]>;  // by group, as its author grouped them
  triggers: { kind: string; about: string }[];
  schedules: Schedule[];
  obligations: string[];
  reports: string[];  // the kinds of record it reports on, daily
  reminders: boolean;
  preferences: string[];
  channels: string[];
  context: Context;
  budget: { per_run: number; per_person_per_day: number };
  tasks: { budget_tokens: number; days: number } | null;
  evaluation: { judge: string; rubric: string } | null;
};

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]);
const num = (value: unknown, otherwise: number) => (typeof value === "number" ? value : Number(value ?? otherwise) || otherwise);
const record = (value: unknown) => (value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {});

/** A schedule's days as day names, as a5s reads them: weekdays, a day, or a list of them. */
function days(value: unknown): string[] {
  if (value === undefined || value === null) return [...DAYS];
  if (value === "weekdays") return [...WEEKDAYS];
  return list(value).map((d) => String(d).toLowerCase()).map((d) => DAY_NAMES[d] ?? d);
}

/** What the forms and the designer show of a definition, or null if it doesn't read as YAML.
 * What it leaves out takes the value a5s gives it, as definitions.py says. */
export function read(text: string): Spec | null {
  const doc = parseDocument(text);
  if (doc.errors.length) return null;
  const found = record(doc.toJS());
  const autonomy = record(found.autonomy);
  const tools = record(found.tools);
  const context = record(found.context);
  const budget = record(found.budget);
  const tasks = found.tasks === undefined || found.tasks === null ? null : record(found.tasks);
  const evaluation = found.evaluation === undefined || found.evaluation === null ? null : record(found.evaluation);
  return {
    works_for: String(found.works_for ?? ""),
    does: String(found.does ?? ""),
    model: String(found.model ?? ""),
    autonomy: { start: num(autonomy.start, 1), max: num(autonomy.max, 1) },
    tools: Object.fromEntries(Object.entries(tools).map(([group, names]) =>
      [group, Array.isArray(names) ? names.map(String) : []])),
    triggers: list(found.triggers).flatMap((t) => Object.entries(record(t)).map(([kind, about]) =>
      ({ kind, about: typeof about === "string" ? about : JSON.stringify(about) }))),
    schedules: list(found.schedules).map((s) => {
      const one = record(s);
      return { name: String(one.name ?? ""), at: list(one.at).map(String), days: days(one.days), task: String(one.task ?? "") };
    }),
    obligations: list(found.obligations).map(String),
    reports: list(found.reports).map((r) => String(record(r).source ?? "")),
    reminders: found.reminders === true,
    preferences: list(found.preferences).map(String),
    channels: found.channels === undefined ? ["teams"] : list(found.channels).map(String),
    context: { budget_tokens: num(context.budget_tokens, 24000), recall: context.recall === true,
               documents: context.documents === true, agents: context.agents === true, notebook: context.notebook === true },
    budget: { per_run: num(budget.per_run, 200000), per_person_per_day: num(budget.per_person_per_day, 1000000) },
    tasks: tasks && { budget_tokens: num(tasks.budget_tokens, 400000), days: num(tasks.days, 3) },
    evaluation: evaluation && { judge: String(evaluation.judge ?? ""), rubric: String(evaluation.rubric ?? "") },
  };
}

export class Unreadable extends Error {
  constructor() {
    super("agent.yaml doesn't read as YAML as it is: put it right under Files first");
  }
}

function edited(text: string, change: (doc: Document) => void): string {
  const doc = parseDocument(text);
  if (doc.errors.length) throw new Unreadable();
  change(doc);
  return doc.toString({ flowCollectionPadding: false });  // [a, b], as people write them
}

/** With a value set in place, so its comment, and its style, such as a folded block, stay. */
export function withValue(text: string, path: string[], value: string | number | boolean): string {
  return edited(text, (doc) => {
    const node = doc.getIn(path, true);
    if (isScalar(node)) node.value = value;
    else doc.setIn(path, value);
  });
}

/** Without a key, such as tasks, for an agent that no longer takes them on. */
export function without(text: string, path: string[]): string {
  return edited(text, (doc) => {
    if (doc.hasIn(path)) doc.deleteIn(path);
  });
}

/** With a map set whole, such as tasks or a judge, as a block of its own. */
export function withMap(text: string, path: string[], value: Record<string, string | number>): string {
  return edited(text, (doc) => {
    doc.setIn(path, doc.createNode(value));
  });
}

/** With a list of words, such as its channels, set in place: its comment, and its style, such
 * as [a, b], stay. */
export function withWords(text: string, path: string[], words: string[]): string {
  return edited(text, (doc) => {
    const node = doc.getIn(path, true);
    if (isSeq(node)) {
      node.items = words.map((w) => doc.createNode(w));
      return;
    }
    const fresh = doc.createNode(words) as YAMLSeq;
    fresh.flow = true;
    doc.setIn(path, fresh);
  });
}

/** A schedule as agent.yaml holds it: its times in quotes, since YAML reads an unquoted 9:00
 * as a number, and its days as weekdays, where they are. */
function scheduleNode(doc: Document, schedule: Schedule): YAMLMap {
  const at = doc.createNode(schedule.at) as YAMLSeq;
  at.flow = true;
  for (const item of at.items) if (isScalar(item)) item.type = Scalar.QUOTE_DOUBLE;
  const weekdays = schedule.days.length === 5 && WEEKDAYS.every((d) => schedule.days.includes(d));
  const order = DAYS.filter((d) => schedule.days.includes(d));
  const node = doc.createNode({ name: schedule.name, at: [], days: weekdays ? "weekdays" : order, task: schedule.task }) as YAMLMap;
  node.set("at", at);
  const named = node.get("days", true);
  if (isSeq(named)) named.flow = true;
  return node;
}

/** With a schedule, in place of the one at `index`, or after the rest. A comment on an empty
 * list said why it was empty, so it goes once the list has one. */
export function withSchedule(text: string, schedule: Schedule, index: number | null): string {
  return edited(text, (doc) => {
    let schedules = doc.get("schedules", true);
    if (!isSeq(schedules)) {
      doc.set("schedules", doc.createNode([]));
      schedules = doc.get("schedules", true);
    }
    const seq = schedules as YAMLSeq;
    const node = scheduleNode(doc, schedule);
    if (index !== null && index < seq.items.length) {
      seq.items[index] = node;
      return;
    }
    if (seq.items.length === 0) seq.comment = undefined;
    seq.flow = false;
    seq.add(node);
  });
}

/** Without the schedule at `index`. */
export function withoutSchedule(text: string, index: number): string {
  return edited(text, (doc) => {
    const schedules = doc.get("schedules", true);
    if (!isSeq(schedules)) return;
    schedules.items.splice(index, 1);
    if (schedules.items.length === 0) schedules.flow = true;  // schedules: [], as it was
  });
}

/** With people able to write to it, or not: its trigger for messages. */
export function withMessages(text: string, on: boolean): string {
  return edited(text, (doc) => {
    let triggers = doc.get("triggers", true);
    if (!isSeq(triggers)) {
      if (!on) return;
      doc.set("triggers", doc.createNode([]));
      triggers = doc.get("triggers", true);
    }
    const seq = triggers as YAMLSeq;
    const at = seq.items.findIndex((item) => isMap(item) && item.has("message"));
    if (!on && at >= 0) seq.items.splice(at, 1);
    if (on && at < 0) {
      seq.flow = false;
      seq.add(doc.createNode({ message: "from the people it works for" }));
    }
  });
}

/** With a tool or without it. One it gains goes into the first group whose tools all do what it
 * does, as `kind` says, or else a new group named for that. */
export function withTool(text: string, tool: string, on: boolean, kind: string,
                         kindOf: (name: string) => string): string {
  return edited(text, (doc) => {
    if (!isMap(doc.get("tools", true))) doc.set("tools", doc.createNode({}));
    const groups = doc.get("tools", true) as YAMLMap;
    for (const [i, pair] of groups.items.entries()) {
      const names = pair.value;
      if (!isSeq(names)) continue;
      const at = names.items.findIndex((item) => isScalar(item) && item.value === tool);
      if (at < 0) continue;
      if (!on) {
        names.items.splice(at, 1);
        if (names.items.length === 0) groups.items.splice(i, 1);
      }
      return;
    }
    if (!on) return;
    const beside = groups.items.find((pair) => isSeq(pair.value) && pair.value.items.length > 0
      && pair.value.items.every((item) => isScalar(item) && kindOf(String(item.value)) === kind));
    if (beside && isSeq(beside.value)) {
      beside.value.add(doc.createNode(tool));
      return;
    }
    const named = groups.get(kind, true);
    if (isSeq(named)) {
      named.add(doc.createNode(tool));
      return;
    }
    const fresh = doc.createNode([tool]) as YAMLSeq;
    fresh.flow = true;
    groups.set(kind, fresh);
  });
}

/** A test case, as an agent's suite runs it on its model (tests/test_agents.py): what's said to
 * it, as whom, and at each step what it must use. */
export type Step = { say: string; uses?: string[] };
export type Case = { name: string; as: string; steps: Step[] };

export const CASES = "tests/tried.yaml";  // where the test pane keeps the cases it's given
const ABOUT = " Test cases kept from the sandbox's test pane: what was said to the agent, as whom, and\n"
  + " what it must use. Add what it must say, or never say, as the agent's other cases do.";

/** How many test cases a file of them holds: none, if it doesn't read as a list of them. */
export function keptCases(text: string | undefined): number {
  if (!text?.trim()) return 0;
  const doc = parseDocument(text);
  return !doc.errors.length && isSeq(doc.contents) ? doc.contents.items.length : 0;
}

/** Test cases, as a file of them, with one more. One with the same name is refused. */
export function withCase(text: string, testCase: Case): string {
  const doc = text.trim() ? parseDocument(text) : new Document([]);
  if (doc.errors.length) throw new Error(`${CASES} doesn't read as YAML as it is: put it right under Files first`);
  if (!text.trim()) doc.commentBefore = ABOUT;
  const cases = doc.contents;
  if (!isSeq(cases)) throw new Error(`${CASES} isn't a list of test cases`);
  if (cases.items.some((item) => isMap(item) && item.get("name") === testCase.name)) {
    throw new Error(`it has a test case called ${testCase.name} already`);
  }
  const node = doc.createNode(testCase) as YAMLMap;
  const steps = node.get("steps", true);
  for (const step of isSeq(steps) ? steps.items : []) {
    const uses = isMap(step) ? step.get("uses", true) : null;
    if (isSeq(uses)) uses.flow = true;  // [a, b], as people write them
  }
  cases.flow = false;
  cases.add(node);
  return doc.toString({ flowCollectionPadding: false });
}
