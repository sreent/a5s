// The studio's words, in English, as its pages write them. A page's words go through t(), with
// {name}s for what changes, such as t("{n} over budget", { n: "£4.00" }), so another language's
// words could sit beside them one day: the studio keeps none now, as a5s's own core/words.py
// keeps none.

/** A page's words, with what changes put in. */
export function t(text: string, vars?: Record<string, string | number>): string {
  return vars ? text.replace(/\{(\w+)\}/g, (all: string, name: string) => (name in vars ? String(vars[name]) : all)) : text;
}

/** The locale numbers and dates are written in: the browser's own. */
export const locale = (): string | undefined => undefined;
