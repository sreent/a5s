// The people's studio API in the channels app, as the signed-in person may read it: each call
// carries their sign-in, kept in memory alone while the studio is open.

let token = "";

export function signedIn(idToken: string): void {
  token = idToken;
}

export function bearer(): string {
  return token;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function get<T>(path: string): Promise<T> {
  const answer = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  const found = await answer.json().catch(() => ({}));
  if (!answer.ok) {
    const said = typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`;
    throw new ApiError(said, answer.status);
  }
  return found as T;
}

// What the API gives, as core/studio.py works it out

export type Tool = {
  name: string;
  group: string;
  description: string | null;
  reads?: boolean;
  writes?: boolean;
  destructive?: boolean;
  sends_outside?: boolean;
  changes: string | null;  // the type of change it makes, which people decide at level 1
  handles: string[];
  outside: string[];
  pinned: string | null;
  missing: boolean;
};

export type Instance = {
  id: string;
  agent: string;
  status: string;
  release: string;
  current: boolean;
  level: number;
  parts: Record<string, unknown>;
  actions: Record<string, unknown>;
  model: string | null;
  serves: string[];
  people: number;
  owner: string | null;
  deputy: string | null;
  asks: string[];
};

export type Schedule = { name: string; at: string[]; days: string[]; task: string };

export type Agent = {
  id: string;
  release: string;
  works_for: string;
  does: string;
  owners: string[];
  model: string;
  autonomy: { start: number; max: number };
  tools: Tool[];
  a5s_tools: string[];
  skills: string[];
  triggers: Record<string, unknown>[];  // each one kind and what it says, such as {message: "from ..."}
  schedules: Schedule[];
  reports: string[];
  obligations: string[];
  reminders: boolean;
  preferences: string[];
  channels: string[];
  context: Record<string, unknown>;
  budget: { per_run: number; per_person_per_day: number };
  instances: Instance[];
  instructions?: string;
};

export type Catalogue = { you: string; agents: Agent[] };

export type ModelRuns = {
  model: string;
  runs: number;
  tokens_per_run: number;
  cached_share: number | null;
  cost_per_run: number | null;
};

export type Figures = {
  runs: ModelRuns[];
  ended: { kind: string | null; outcome: string; runs: number }[];
  obligations: { due: number; on_time: number; late: number; open: number; chased: number; escalated: number };
  reminders: { due: number; on_time: number; missed: number };
  held: { held: number; approved: number; rejected: number; lapsed: number; waiting: number };
  samples: { graded: number; right: number; wrong: number; critical: number };
  denied: { kind: string; action: string; reasons: string[]; times: number }[];
  denied_partial: boolean;
  reports: { source: string; outcome: string; reports: number }[];
  returning: { agent: string; wrote_before: number; came_back: number }[];
  daily: Day[];  // each day of the period, in `zone`, the viewer's own
  zone: string;
  instances: string[];
};

/** One day's runs, by how each ended, as core/status.py's outcome() says it. */
export type Day = { day: string; runs: number; ended: Record<string, number> };

export type Person = { id: string; name: string | null };

export type RunLine = {
  run: string;
  instance: string;
  trigger: string | null;
  acts_for: Person[];
  people: number;
  opened_at: string;
  closed_at: string | null;
  outcome: string;
  tokens: number;
  model: string | null;
  read_outside: boolean;
};

export type RunsPage = { instance: string; runs: RunLine[]; hidden: number; before: string | null };

export type Call = {
  seq: number;
  at: string;
  tool: string;
  decision: string;
  reasons: string[];
  outcome: string | null;
};

export type Run = RunLine & {
  agent: string | null;
  started_by: Record<string, unknown>;
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  records: string[];
  calls: Call[];
};
