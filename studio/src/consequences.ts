// What follows here from what an agent may do, in words, as its designer shows it while it's
// built: who decides its changes, part by part, what its levels allow, its limits, and what
// each of its tools and schedules means under a5s's base policy (core/policies/base.cedar),
// by the settings in force and the directory as they stand now.

import type { Offer, Offered, PartRule } from "./api";
import type { Schedule, Spec } from "./definition";
import { locale, t } from "./i18n";
import { plural } from "./ui";

/** Words joined as a sentence would: a, b and c; or, with "or", a, b or c. */
export const and = (them: string[], last: "and" | "or" = "and") => {
  if (them.length < 2) return them[0] ?? "";
  const words = { list: them.slice(0, -1).join(", "), last: them[them.length - 1] };
  return last === "or" ? t("{list} or {last}", words) : t("{list} and {last}", words);
};
const or = (them: string[]) => and(them, "or");
const tokens = (n: number) => t("{n} tokens", { n: n.toLocaleString(locale()) });
const percent = (x: number) => `${Math.round(x * 1000) / 10}%`;

/** Each day of a schedule, as people say it of a day it comes round on: on Mondays. */
const onDays = (): Record<string, string> => ({
  mon: t("Mondays"), tue: t("Tuesdays"), wed: t("Wednesdays"), thu: t("Thursdays"), fri: t("Fridays"),
  sat: t("Saturdays"), sun: t("Sundays"),
});
export const CHANNEL_WORDS: Record<string, string> = { teams: "Teams", matrix: "Matrix" };

/** A schedule's days, as people say them: every day, weekdays, or the days by name. */
export function dayWords(days: string[]): string {
  const set = new Set(days);
  if (set.size === 7) return t("every day");
  if (set.size === 5 && ["mon", "tue", "wed", "thu", "fri"].every((d) => set.has(d))) return t("on weekdays");
  const names = onDays();
  return t("on {days}", { days: and(Object.keys(names).filter((d) => set.has(d)).map((d) => names[d])) });
}

/** Who decides a change in a part below level 2, in words. */
export function deciders(part: PartRule): string {
  return part.deciders.length ? or(part.deciders) : t("nobody yet, so none is made there");
}

/** The scenario's tools an agent has that change records a part decides. */
export function changers(spec: Spec, offer: Offer): Offered[] {
  const has = new Set(Object.values(spec.tools).flat());
  return offer.tools.filter((tool) => has.has(tool.name) && tool.changes);
}

/** What follows from one of its tools. */
export function toolLines(tool: Offered, spec: Spec, offer: Offer): string[] {
  const max = spec.autonomy.max;
  const lines: string[] = [];
  if (tool.changes && max < 1) {  // no permit covers a change at level 0: a5s refuses it
    lines.push(t("Its release keeps it at level 0, which only observes, so a5s refuses every change it asks for. At level 1, each would wait for a yes from a decider of its record's part."));
  } else if (tool.changes) {
    const parts = offer.parts.map((p) => t("{who} in {part}", { who: deciders(p), part: p.name }));
    lines.push(parts.length
      ? t("Below level 2, each change it asks for waits for a yes from a decider of its record's part: {deciders}.", { deciders: parts.join("; ") })
      : t("Below level 2, each change it asks for waits for a yes from a decider of its record's part, its owners and their delegates."));
    const limit = offer.limits[tool.changes];
    const most = [limit?.per_run && t("{n} in a run", { n: limit.per_run }),
                  limit?.per_person_30_days && t("{n} for each person in 30 days", { n: limit.per_person_30_days })]
      .filter((x): x is string => Boolean(x));
    if (most.length) {
      lines.push(t("The settings allow {most}: past that, each waits for its decider, whatever the level.", { most: and(most) }));
    } else if (offer.parts.length) {
      lines.push(t("The settings set no limit for {action}, so at level 2 nothing caps how many it makes.", { action: tool.changes }));
    }
    if (max < 2) {
      lines.push(t("Its release goes no higher than level {max}, so every one waits for its decider.", { max }));
    } else {
      const bars = offer.parts.map((p) => p.threshold ? t("{share} in {part}", { share: percent(p.threshold), part: p.name })
        : t("never in {part}, which sets no bar", { part: p.name }));
      lines.push(bars.length
        ? t("a5s makes one alone only at level 2, which the settings give for {action} in one part at a time, never in a run that has read outside content, and only once graded samples show enough of its changes there right: {bars}.",
            { action: tool.changes, bars: and(bars) })
        : t("a5s makes one alone only at level 2, which the settings give for {action} in one part at a time, never in a run that has read outside content, and only once graded samples show enough of its changes there right.",
            { action: tool.changes }));
    }
  } else if (tool.destructive || tool.sends_outside) {
    lines.push(tool.destructive
      ? t("What it does can't be undone, so a5s lets it run only at level 2, which only the settings give, and never in a run that has read outside content.")
      : t("It sends outside the organisation, so a5s lets it run only at level 2, which only the settings give, and never in a run that has read outside content."));
    if (max < 2) lines.push(t("Its release goes no higher than level {max}, so a5s refuses every call to it.", { max }));
  } else if (tool.writes) {
    lines.push(t("It writes, but changes nothing a part decides: from level 1 it runs without anyone's yes, and the ledger keeps each call. At level 0, which only observes, a5s refuses it."));
    if (max < 1) lines.push(t("Its release keeps it at level 0, so a5s refuses every call to it."));
  } else {
    lines.push(t("It reads: a5s passes on only the records everyone the run acts for may see, in the parts its instance works in."));
  }
  if (tool.outside.length) {
    lines.push(t("What it brings from outside the organisation, its {what}, goes to a5s's reader first: the agent reads only what the reader takes from it, and the run is marked, so it never acts at level 2.",
                 { what: and(tool.outside) }));
  }
  if (tool.handles.length) {
    lines.push(t("It hands {what} over as handles: the model never sees the values, and a5s puts them back where they go.",
                 { what: and(tool.handles) }));
  }
  return lines;
}

/** What follows from one of its schedules. */
export function scheduleLines(schedule: Schedule, spec: Spec): string[] {
  const at = schedule.at.length ? and(schedule.at) : t("no time yet");
  return [t("a5s starts a run at {at}, {days}, in its instance owner's time zone, and asks it: “{task}”",
            { at, days: dayWords(schedule.days), task: schedule.task || "…" }),
          spec.context.notebook
            ? t("A run a schedule starts acts for nobody, so it writes to nobody, and what it learns from records it may note in its notebook, checked against them, for its later runs.")
            : t("A run a schedule starts acts for nobody, so it writes to nobody.")];
}

/** What follows from people writing to it. */
export function messageLines(spec: Spec): string[] {
  const on = spec.channels.map((c) => CHANNEL_WORDS[c] ?? c);
  return [t("People write to it on {channels}. Each run acts for whoever wrote, sees only what they may see, and writes to them alone.",
            { channels: on.length ? and(on) : t("no channel yet") })];
}

/** What its levels allow. */
export function levelLines(spec: Spec): string[] {
  const { start, max } = spec.autonomy;
  const lines = [start < 1
    ? t("Its instances start at level {start}: it only observes: a5s refuses any tool that writes.", { start })
    : t("Its instances start at level {start}: it may write, and each change it asks for waits for its decider.", { start })];
  if (max <= start) lines.push(t("It goes no higher."));
  else if (max === 1) lines.push(t("It may go as far as level 1, so a person decides every change it asks for."));
  else lines.push(t("It may reach level 2, making changes alone, only where the settings give it for a type of change in a part, and graded samples of its work there bear it out."));
  return lines;
}

/** Its limits: what it may spend, and how many changes of each type. */
export function limitLines(spec: Spec, offer: Offer): string[] {
  const lines = [
    t("Each run may spend {run}, and its instance {person} for each person a day, a fifth of it kept for chases and reminders.",
      { run: tokens(spec.budget.per_run), person: tokens(spec.budget.per_person_per_day) }),
    t("Each run is given {tokens} of its conversation, split by part.", { tokens: tokens(spec.context.budget_tokens) }),
  ];
  if (spec.tasks) {
    lines.push(t("A long task may spend {tokens}, over {days} at most.",
                 { tokens: tokens(spec.tasks.budget_tokens), days: plural(spec.tasks.days, "day") }));
  }
  for (const tool of changers(spec, offer)) {
    const limit = offer.limits[tool.changes ?? ""];
    if (limit?.per_run || limit?.per_person_30_days) {
      lines.push(t("{action}: {limits}, then each waits.", { action: tool.changes ?? "", limits: and([
        limit.per_run && t("{n} a run", { n: limit.per_run }),
        limit.per_person_30_days && t("{n} for each person in 30 days", { n: limit.per_person_30_days }),
      ].filter((x): x is string => Boolean(x))) }));
    }
  }
  return lines;
}

/** a5s's own tools, by their key in agent.yaml: the two last are preferences, which people set
 * through it. */
export type Ability = "reminders" | "recall" | "documents" | "agents" | "notebook" | "tasks" | Preference;

/** What its abilities, a5s's own tools, are for, each in a line, by its key in agent.yaml. */
export const abilities = (): [key: Ability, name: string, does: string][] => [
  ["reminders", t("Reminders"), t("offers reminders, and keeps those people confirm")],
  ["recall", t("Its conversation"), t("searches its conversation with the person it acts for, and corrects its summaries at their word")],
  ["documents", t("Documents from outside"), t("asks a5s's reader about documents from outside its run has read")],
  ["agents", t("Other agents"), t("asks other agents questions: the settings name which, and their owners approve it")],
  ["notebook", t("Its notebook"), t("notes what it learns from records, on its schedules, for its later runs")],
  ["tasks", t("Long tasks"), t("takes on work people ask for over more than one run, once they say yes")],
  ["digest-time", t("Their digest's time"), t("lets people set when their daily digest comes")],
  ["how-i-work", t("How they like to work"), t("keeps what people tell it of how they like to work, at their word")],
];

/** The preferences people may set through an agent, as agent.yaml lists them. */
export type Preference = "digest-time" | "how-i-work";
export const PREFERENCES: readonly string[] = ["digest-time", "how-i-work"];
