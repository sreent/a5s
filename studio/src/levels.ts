// What an agent may do in a part, by name, as people read it (src/a5s/levels.py): it reads only,
// it asks first, or it acts on its own. The API and the ledger keep them as 0, 1 and 2, the order
// a5s compares them in; nothing a person reads says the number, and what the studio writes into
// settings and agent definitions says the name, which a5s reads as it reads the number.

import { t } from "./i18n";

const NAMES = ["reads only", "asks first", "acts on its own"] as const;
// each in the language spoken, as the catalogue has it
const said = () => [t("reads only"), t("asks first"), t("acts on its own")];

/** A level's name, in the language spoken. */
export const levelName = (level: number | null | undefined): string =>
  level === null || level === undefined ? t("none") : said()[Math.max(0, Math.min(level, 2))];

/** A level's name as settings and agent definitions write it, in English, as a5s reads them. */
export const writtenLevel = (level: number): string => NAMES[Math.max(0, Math.min(level, 2))];

/** A level, as settings or an agent definition give it: by name, or, as before, by number. */
export function levelOf(value: unknown, otherwise: number): number {
  if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 2) return value;
  if (typeof value === "string") {
    const said = value.trim().toLowerCase().replace(/[-_]/g, " ").replace(/\s+/g, " ");
    const at = (NAMES as readonly string[]).indexOf(said);
    if (at >= 0) return at;
  }
  return otherwise;
}
