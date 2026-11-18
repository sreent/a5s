// The studio's words in the language whoever signed in reads (core/languages.py): English, as its
// pages write them, or Thai, from the catalogue in i18n/th.ts, where it has their words; anything
// it hasn't stays as written. A page's words go through t(), with {name}s for what changes, such
// as t("{n} over budget", { n: "£4.00" }). The language comes with the sidebar's /shell/api, and
// is kept in the tab, so a page opens in it the next time before that answer comes.

import { TH } from "./i18n/th";

export type Language = "en" | "th";
const KEPT = "a5s.language";

function remembered(): Language {
  try {
    return localStorage.getItem(KEPT) === "th" ? "th" : "en";
  } catch {
    return "en";  // storage that can't be read: English, until /shell/api says
  }
}

let current: Language = remembered();
const listeners = new Set<() => void>();
document.documentElement.lang = current;

/** The language the studio speaks now. */
export function language(): Language {
  return current;
}

/** Speak a language from now on, such as the one /shell/api says someone reads. */
export function setLanguage(code: string): void {
  const next: Language = code === "th" ? "th" : "en";
  document.documentElement.lang = next;
  try {
    localStorage.setItem(KEPT, next);
  } catch {
    // only a convenience for the next page that opens
  }
  if (next === current) return;
  current = next;
  listeners.forEach((then) => then());
}

/** Be told when the language changes, as the app is, to draw its pages again in it. */
export function onLanguage(then: () => void): () => void {
  listeners.add(then);
  return () => listeners.delete(then);
}

/** Words in the language spoken now, with what changes put in. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const said = (current === "th" ? TH[text] : undefined) ?? text;
  return vars ? said.replace(/\{(\w+)\}/g, (all: string, name: string) => (name in vars ? String(vars[name]) : all)) : said;
}

/** Whether the catalogue has words for these, in a language other than English: for the tests
 * that check a page's words are all there. */
export function has(text: string): boolean {
  return text in TH;
}

/** Numbers and dates as the language spoken writes them: Thai's Buddhist era is left to the
 * browser's own Thai, as people there read dates. */
export const locale = (): string | undefined => (current === "th" ? "th-TH" : undefined);
