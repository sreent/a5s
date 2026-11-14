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
  return send<T>("GET", path);
}

/** A call to the people's API, as the person signed in, with a body to write, if any. */
export async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const answer = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const found = await answer.json().catch(() => ({}));
  if (!answer.ok) {
    const said = typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`;
    throw new ApiError(said, answer.status);
  }
  return found as T;
}

/** A file from the people's API, as the person signed in, saved where their browser saves files. */
export async function download(path: string, name: string): Promise<void> {
  const answer = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  if (!answer.ok) {
    const found = await answer.json().catch(() => ({}));
    throw new ApiError(typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`, answer.status);
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await answer.blob());
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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
  why?: string[];  // why the viewer's roles bring it into their view
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

export type Catalogue = {
  you: string;
  agents: Agent[];
  authoring: { new: boolean; agents: string[] };  // whether they may start an agent, and which they may change
};

// Making agents (core/drafts.py)

export type Template = { name: string; works_for: string; does: string; model: string; tools: string[]; lacks: string[] };

export type DraftLine = {
  id: string; agent: string; based_on: string; created_at: string; updated_at: string;
  published: string | null;  // the pull request it was last published as, if it has been
  author?: string;  // a co-author's, whose draft of an agent they may author too
};

export type Draft = DraftLine & {
  files: Record<string, string>;  // the agent's folder, each file's text by its path in it
  problems: string[];  // what would stop its release, as `a5s agent check` says it
  preview: Agent | null;  // as the catalogue would show it, if it loads
  signers: { role: string; who: string; why: string }[] | null;  // whom its release would need
  publishing: boolean;  // whether the studio opens its pull request, or its author does
  yours: boolean;  // or a co-author's, read only
  author: string;
};

export type Offered = Omit<Tool, "group" | "pinned" | "missing">;

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
