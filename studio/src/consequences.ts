// What follows here from what an agent may do, in words, as its designer shows it while it's
// built: who decides its changes, part by part, what its levels allow, its limits, and what
// each of its tools and schedules means under a5s's base policy (core/policies/base.cedar),
// by the settings in force and the directory as they stand now.

import type { Offer, Offered, PartRule } from "./api";
import type { Schedule, Spec } from "./definition";
import { plural } from "./ui";

/** Words joined as a sentence would: a, b and c. */
export const and = (them: string[], last = "and") =>
  them.length > 1 ? `${them.slice(0, -1).join(", ")} ${last} ${them[them.length - 1]}` : them[0] ?? "";
const or = (them: string[]) => and(them, "or");
const tokens = (n: number) => `${n.toLocaleString()} tokens`;
const percent = (x: number) => `${Math.round(x * 1000) / 10}%`;

const DAY_WORDS: Record<string, string> = {
  mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday",
};
export const CHANNEL_WORDS: Record<string, string> = { teams: "Teams", matrix: "Matrix" };

/** A schedule's days, as people say them: every day, weekdays, or the days by name. */
export function dayWords(days: string[]): string {
  const set = new Set(days);
  if (set.size === 7) return "every day";
  if (set.size === 5 && ["mon", "tue", "wed", "thu", "fri"].every((d) => set.has(d))) return "on weekdays";
  return `on ${and(Object.keys(DAY_WORDS).filter((d) => set.has(d)).map((d) => `${DAY_WORDS[d]}s`))}`;
}

/** Who decides a change in a part below level 2, in words. */
export function deciders(part: PartRule): string {
  return part.deciders.length ? or(part.deciders) : "nobody yet, so none is made there";
}

/** The scenario's tools an agent has that change records a part decides. */
export function changers(spec: Spec, offer: Offer): Offered[] {
  const has = new Set(Object.values(spec.tools).flat());
  return offer.tools.filter((t) => has.has(t.name) && t.changes);
}

/** What follows from one of its tools. */
export function toolLines(tool: Offered, spec: Spec, offer: Offer): string[] {
  const max = spec.autonomy.max;
  const lines: string[] = [];
  if (tool.changes && max < 1) {  // no permit covers a change at level 0: a5s refuses it
    lines.push("Its release keeps it at level 0, which only observes, so a5s refuses every change it asks for. At level 1, "
      + "each would wait for a yes from a decider of its record's part.");
  } else if (tool.changes) {
    const parts = offer.parts.map((p) => `${deciders(p)} in ${p.name}`);
    lines.push(`Below level 2, each change it asks for waits for a yes from a decider of its record's part${
      parts.length ? `: ${parts.join("; ")}` : ", its owners and their delegates"}.`);
    const limit = offer.limits[tool.changes];
    const most = [limit?.per_run && `${limit.per_run} in a run`,
                  limit?.per_person_30_days && `${limit.per_person_30_days} for each person in 30 days`]
      .filter((x): x is string => Boolean(x));
    if (most.length) {
      lines.push(`The settings allow ${and(most)}: past that, each waits for its decider, whatever the level.`);
    } else if (offer.parts.length) {
      lines.push(`The settings set no limit for ${tool.changes}, so at level 2 nothing caps how many it makes.`);
    }
    if (max < 2) {
      lines.push(`Its release goes no higher than level ${max}, so every one waits for its decider.`);
    } else {
      const bars = offer.parts.map((p) => p.threshold ? `${percent(p.threshold)} in ${p.name}` : `never in ${p.name}, which sets no bar`);
      lines.push(`a5s makes one alone only at level 2, which the settings give for ${tool.changes} in one part at a time, `
        + `never in a run that has read outside content, and only once graded samples show enough of its changes there right${
          bars.length ? `: ${and(bars)}` : ""}.`);
    }
  } else if (tool.destructive || tool.sends_outside) {
    lines.push(`${tool.destructive ? "What it does can't be undone" : "It sends outside the organisation"}, so a5s lets it `
      + "run only at level 2, which only the settings give, and never in a run that has read outside content.");
    if (max < 2) lines.push(`Its release goes no higher than level ${max}, so a5s refuses every call to it.`);
  } else if (tool.writes) {
    lines.push("It writes, but changes nothing a part decides: from level 1 it runs without anyone's yes, and the ledger "
      + "keeps each call. At level 0, which only observes, a5s refuses it.");
    if (max < 1) lines.push("Its release keeps it at level 0, so a5s refuses every call to it.");
  } else {
    lines.push("It reads: a5s passes on only the records everyone the run acts for may see, in the parts its instance works in.");
  }
  if (tool.outside.length) {
    lines.push(`What it brings from outside the organisation, its ${and(tool.outside)}, goes to a5s's reader first: the agent `
      + "reads only what the reader takes from it, and the run is marked, so it never acts at level 2.");
  }
  if (tool.handles.length) {
    lines.push(`It hands ${and(tool.handles)} over as handles: the model never sees the values, and a5s puts them back where they go.`);
  }
  return lines;
}

/** What follows from one of its schedules. */
export function scheduleLines(schedule: Schedule, spec: Spec): string[] {
  const at = schedule.at.length ? and(schedule.at) : "no time yet";
  return [`a5s starts a run at ${at}, ${dayWords(schedule.days)}, in its instance owner's time zone, and asks it: “${
    schedule.task || "…"}”`,
          `A run a schedule starts acts for nobody, so it writes to nobody${spec.context.notebook
            ? ", and what it learns from records it may note in its notebook, checked against them, for its later runs" : ""}.`];
}

/** What follows from people writing to it. */
export function messageLines(spec: Spec): string[] {
  const on = spec.channels.map((c) => CHANNEL_WORDS[c] ?? c);
  return [`People write to it on ${on.length ? and(on) : "no channel yet"}. Each run acts for whoever wrote, sees only `
    + "what they may see, and writes to them alone."];
}

const STARTS = ["it only observes: a5s refuses any tool that writes", "it may write, and each change it asks for waits for its decider"];

/** What its levels allow. */
export function levelLines(spec: Spec): string[] {
  const { start, max } = spec.autonomy;
  const lines = [`Its instances start at level ${start}: ${STARTS[Math.min(Math.max(start, 0), 1)]}.`];
  if (max <= start) lines.push("It goes no higher.");
  else if (max === 1) lines.push("It may go as far as level 1, so a person decides every change it asks for.");
  else lines.push("It may reach level 2, making changes alone, only where the settings give it for a type of change in a part, "
    + "and graded samples of its work there bear it out.");
  return lines;
}

/** Its limits: what it may spend, and how many changes of each type. */
export function limitLines(spec: Spec, offer: Offer): string[] {
  const lines = [
    `Each run may spend ${tokens(spec.budget.per_run)}, and its instance ${tokens(spec.budget.per_person_per_day)} for each `
      + "person a day, a fifth of it kept for chases and reminders.",
    `Each run is given ${tokens(spec.context.budget_tokens)} of its conversation, split by part.`,
  ];
  if (spec.tasks) lines.push(`A long task may spend ${tokens(spec.tasks.budget_tokens)}, over ${plural(spec.tasks.days, "day")} at most.`);
  for (const tool of changers(spec, offer)) {
    const limit = offer.limits[tool.changes ?? ""];
    if (limit?.per_run || limit?.per_person_30_days) {
      lines.push(`${tool.changes}: ${and([limit.per_run && `${limit.per_run} a run`, limit.per_person_30_days
        && `${limit.per_person_30_days} for each person in 30 days`].filter((x): x is string => Boolean(x)))}, then each waits.`);
    }
  }
  return lines;
}

/** What its abilities, a5s's own tools, are for, each in a line, by its key in agent.yaml: the two
 * last are preferences, which people set through it. */
export const ABILITIES: [key: "reminders" | "recall" | "documents" | "agents" | "notebook" | "tasks" | Preference,
  name: string, does: string][] = [
  ["reminders", "Reminders", "offers reminders, and keeps those people confirm"],
  ["recall", "Its conversation", "searches its conversation with the person it acts for, and corrects its summaries at their word"],
  ["documents", "Documents from outside", "asks a5s's reader about documents from outside its run has read"],
  ["agents", "Other agents", "asks other agents questions: the settings name which, and their owners approve it"],
  ["notebook", "Its notebook", "notes what it learns from records, on its schedules, for its later runs"],
  ["tasks", "Long tasks", "takes on work people ask for over more than one run, once they say yes"],
  ["digest-time", "Their digest's time", "lets people set when their daily digest comes"],
  ["how-i-work", "How they like to work", "keeps what people tell it of how they like to work, at their word"],
];

/** The preferences people may set through an agent, as agent.yaml lists them. */
export type Preference = "digest-time" | "how-i-work";
export const PREFERENCES: readonly string[] = ["digest-time", "how-i-work"];
