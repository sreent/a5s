// The studio API's types, made from its description by `uv run python -m a5s.core.studio_api`:
// don't edit them here, but in core/studio_models.py, and make them again.
export type ActedFor = {
  id: string;
  name: string | null;
};

// An agent as someone sees it: each layer of it they see, with why. What a layer they
// don't see would add is left out, not null.
export type Agent = {
  layers: Record<string, string[]>;
  listed: boolean;
  why: string[];
  instances: Instance[];
  id: string;
  release: string;
  works_for: string;
  does: string;
  owners: string[];
  tools?: Tool[];
  a5s_tools?: string[];
  model?: string;
  autonomy?: Autonomy;
  triggers?: Record<string, unknown>[];
  schedules?: Schedule[];
  reports?: string[];
  obligations?: string[];
  reminders?: boolean;
  preferences?: string[];
  channels?: string[];
  context?: Context;
  budget?: Budget;
  skills?: string[];
  instructions?: string;
  ask?: Ask | null;
  asks?: Asked[];
};

// Someone's own ask for an agent, as they see it: never who declined it (core/asks.py).
export type Ask = {
  id: string;
  agent: string;
  asked_at: string;
  ended_at: string | null;
  outcome: string | null;
};

// An open ask that waits on someone, with whose it is, and why it's theirs.
export type Asked = {
  id: string;
  agent: string;
  asker: string;
  person: string;
  asked_at: string;
  why: string[];
};

export type Authoring = {
  new: boolean;
  agents: string[];
};

// The levels an agent's release lets its instances act at: where they start, and the most.
export type Autonomy = {
  start: number;
  max: number;
};

// The tokens an instance may use, in one run, and for one person in a day.
export type Budget = {
  per_run: number;
  per_person_per_day: number;
};

// One tool call a run made, with the policy's decision, and how it ended.
export type Call = {
  seq: number;
  at: string;
  tool: string;
  decision: string;
  reasons: string[];
  outcome: string | null;
};

// Running one of a draft's test cases in the sandbox: on which of the models it offers.
export type CaseRun = {
  model?: string;
};

export type Catalogue = {
  you: string;
  agents: Agent[];
  authoring: Authoring;
};

// What an agent's runs are given beyond the conversation.
export type Context = {
  budget_tokens: number;
  recall: boolean;
  documents: boolean;
  agents: boolean;
  notebook: boolean;
};

// One day's runs, by how each ended, in the viewer's own time zone.
export type Day = {
  day: string;
  runs: number;
  ended: Record<string, number>;
};

export type Denied = {
  kind: string;
  action: string;
  reasons: string[];
  times: number;
};

// A draft's agent's folder: each file's text, by its path in it.
export type DraftFiles = {
  files: Record<string, string>;
};

// One of someone's drafts, or a co-author's, without its files (core/drafts.py).
export type DraftLine = {
  id: string;
  agent: string;
  based_on: string | null;
  created_at: string;
  updated_at: string;
  published: string | null;
  author?: string;
};

// A new draft: a new agent's name and the template it starts from, an agent of the
// release to change, or a co-author's draft to copy.
export type DraftStart = {
  name?: string | null;
  template?: string | null;
  agent?: string | null;
  copy_of?: string | null;
};

// Trying a draft in the sandbox: who to be, of its made-up people, what to say, and on
// which of the models it offers.
export type DraftTry = {
  person: string;
  text: string;
  model?: string;
};

export type Ended = {
  kind: string | null;
  outcome: string;
  runs: number;
};

// How some instances are doing over the last `days` days.
export type Figures = {
  days: number;
  obligations: Obligations;
  reminders: Reminders;
  returning: Returning[];
  returning_team: ReturningTeam;
  groups: GroupChats[];
  runs: ModelRuns[];
  held: Held;
  samples: Samples;
  questions: Questions[];
  notebook: Notebook[];
  ended: Ended[];
  daily: Day[];
  zone: string;
  denied: Denied[];
  denied_partial: boolean;
  reports: Reported[];
  instances: string[];
};

export type GroupChats = {
  agent: string;
  messages: number;
  chats: number;
  people: number;
};

export type HTTPValidationError = {
  detail?: ValidationError[];
};

// Whom to hand one's draft over to: someone who may author its agent too.
export type HandOver = {
  to: string;
};

export type Held = {
  held: number;
  approved: number;
  rejected: number;
  lapsed: number;
  waiting: number;
  approved_share: number | null;
  decided_hours_p50: number | null;
  decided_hours_p90: number | null;
};

export type Home = {
  you: string;
  waiting: Waiting[];
  drafts: DraftLine[];
  catalogue: boolean;
  authoring: boolean;
};

// One of an agent's instances, which someone may watch.
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

export type ModelRuns = {
  instance: string;
  model: string | null;
  runs: number;
  tokens_per_run: number;
  tokens_p90: number;
  cached_share: number | null;
  cost_per_run: number | null;
};

export type Notebook = {
  instance: string;
  notes: number;
  kept: number;
  refused: number;
  let_go: number;
  given: number;
  runs_given: number;
};

export type Obligations = {
  due: number;
  on_time: number;
  late: number;
  unknown: number;
  open: number;
  chased: number;
  escalated: number;
  on_time_share: number | null;
  late_hours_p50: number | null;
  late_hours_p90: number | null;
};

export type Questions = {
  instance: string;
  asked: number;
  answered: number;
  unanswered: number;
  answered_seconds_p90: number | null;
};

export type Reminders = {
  due: number;
  on_time: number;
  missed: number;
  on_time_share: number | null;
};

export type Reported = {
  source: string;
  outcome: string;
  reports: number;
};

// A version of the settings asked for, which the core proposes to everyone it needs.
export type Requested = {
  request: number;
  serial: number;
};

export type Returning = {
  agent: string;
  wrote_before: number;
  came_back: number;
  share: number | null;
  served: number;
  came_back_served: number;
  served_share: number | null;
};

export type ReturningTeam = {
  served: number;
  came_back: number;
  share: number | null;
};

// A role someone holds, what gave it them, and what it lets them do.
export type Role = {
  role: string;
  by: string[];
  may: string;
};

export type Run = {
  run: string;
  instance: string;
  trigger: string | null;
  acts_for: ActedFor[];
  people: number;
  opened_at: string;
  closed_at: string | null;
  outcome: string;
  tokens: number;
  model: string | null;
  read_outside: boolean;
  agent: string | null;
  started_by: Record<string, unknown>;
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  records: string[];
  calls: Call[];
};

export type RunLine = {
  run: string;
  instance: string;
  trigger: string | null;
  acts_for: ActedFor[];
  people: number;
  opened_at: string;
  closed_at: string | null;
  outcome: string;
  tokens: number;
  model: string | null;
  read_outside: boolean;
};

export type RunsPage = {
  instance: string;
  runs: RunLine[];
  hidden: number;
  before: string | null;
};

export type Samples = {
  graded: number;
  right: number;
  wrong: number;
  critical: number;
  lapsed: number;
  right_share: number | null;
};

// When an agent works on its own, in its instance owner's time zone, and what it's asked.
export type Schedule = {
  name: string;
  at: string[];
  days: string[];
  task: string;
};

// Which of an agent's instances is to serve someone who asked for it.
export type Serve = {
  instance: string;
};

// One of an agent's tools, with what it reads, writes or changes.
export type Tool = {
  name: string;
  group: string;
  description: string | null;
  reads?: boolean;
  writes?: boolean;
  destructive?: boolean;
  sends_outside?: boolean;
  changes: string | null;
  handles: string[];
  outside: string[];
  pinned: string | null;
  missing: boolean;
};

export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

// Something that waits for someone: what it is, why it's theirs, and where they do it, a
// page of a5s's, or the command line.
export type Waiting = {
  kind: string;
  what: string;
  why: string[];
  go: string | null;
  how?: string;
};

export type You = {
  you: string;
  id: string;
  roles: Role[];
  groups: string[];
};
