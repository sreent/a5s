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

// An instance a new one could ask, of those the person may watch: its agent, and the parts
// it works in.
export type Askable = {
  id: string;
  agent: string;
  parts: string[];
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

export type CaseLine = {
  number: number;
  name: string;
  file: string;
  suite_alone: string[];
};

// A test case run in the sandbox, or why it wasn't.
export type CaseRan = {
  name: string;
  file: string;
  ran: boolean;
  why?: string;
  passed?: boolean;
  problems?: string[];
  steps?: CaseStep[];
};

// Running one of a draft's test cases in the sandbox: on which of the models it offers.
export type CaseRun = {
  model?: string;
};

export type CaseStep = {
  say: string;
  reply: string;
  called: string[];
  wrong: string[];
  judged?: Judged;
};

export type Cases = {
  cases: CaseLine[];
  problem?: string;
};

export type Catalogue = {
  you: string;
  agents: Agent[];
  authoring: Authoring;
};

// A change a version of the settings makes, in words code worked out, and whether it widens
// what agents do, as the page that approves it marks it.
export type Change = {
  text: string;
  widens: boolean;
};

export type CoAuthors = {
  people: Named[];
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

// An agent as its folder defines it, whole, as the catalogue would show it: a draft's
// preview.
export type Defined = {
  id: string;
  release: string;
  works_for: string;
  does: string;
  owners: string[];
  model: string;
  autonomy: Autonomy;
  tools: Tool[];
  a5s_tools: string[];
  skills: string[];
  triggers: Record<string, unknown>[];
  schedules: Schedule[];
  reports: string[];
  obligations: string[];
  reminders: boolean;
  preferences: string[];
  channels: string[];
  context: Context;
  budget: Budget;
  instances: Instance[];
  instructions: string;
};

export type Denied = {
  kind: string;
  action: string;
  reasons: string[];
  times: number;
};

// How a draft was described in words: its author's words, the model that proposed what it
// needs, and a note on each thing it was given or not, for its author to check.
export type Described = {
  words: string;
  model: string;
  notes: DescribedNote[];
};

// One thing a draft described in words was given, and why, or wasn't, and why not.
export type DescribedNote = {
  what: string;
  given: boolean;
  why: string;
};

// A draft: its agent's folder, file by file, what would stop its release, and how the
// catalogue would show it, if it loads.
export type Draft = {
  id: string;
  agent: string;
  based_on: string | null;
  created_at: string;
  updated_at: string;
  published: string | null;
  files: Record<string, string>;
  plan: Plan;
  described?: Described | null;
  yours: boolean;
  author: string | null;
  drafted_before: Drafter[];
  problems: string[];
  preview: Defined | null;
  signers: Signer[] | null;
  publishing: boolean;
  released: boolean;
  at_work: boolean;
};

// A draft's agent's folder: each file's text, by its path in it, and, if it changes, its
// authors' plan for its first instance.
export type DraftFiles = {
  files: Record<string, string>;
  plan?: Plan | null;
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

// A new draft: a new agent's name and the template it starts from, or what it's for in
// its author's words, for the sandbox's model to propose what it needs; an agent of the
// release to change; or a co-author's draft to copy.
export type DraftStart = {
  name?: string | null;
  template?: string | null;
  describe?: string | null;
  model?: string | null;
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

// Someone who drafted a draft before whoever holds it now, and how it went on from them.
export type Drafter = {
  name: string;
  at: string;
  how: "handed" | "copied";
};

export type Drafts = {
  drafts: DraftLine[];
  theirs: DraftLine[];
};

export type Dropped = {
  dropped: string;
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
  judge: Judge;
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

export type HandedOver = {
  handed: string;
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

// The version of the settings in force: as written, all of it in words, and as data, which
// the forms change.
export type InForce = {
  serial: number;
  text: string;
  whole: string[];
  data: Record<string, unknown> | null;
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
  people: number;
  owner: string | null;
  deputy: string | null;
  asks: string[];
};

// How far an agent's judge agrees with people, on the samples both graded (core/judging.py).
export type Judge = {
  both: number;
  agreed: number;
  missed: number;
  false_alarms: number;
  agreed_share: number | null;
  kappa: number | null;
};

// What a judge said of a step a case says what a right answer is for, or why none did.
export type Judged = {
  grade: "right" | "wrong" | "critical" | null;
  why: string;
  judge: string | null;
};

// The scenario's limits for a type of change: past either, a change waits for a person,
// whatever the level.
export type Limit = {
  per_run: number | null;
  per_person_30_days: number | null;
};

// One call to the model a try made: what it was sent, what came back, and how.
export type ModelCall = {
  sent: Sent;
  came: unknown;
  status: number;
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

export type Named = {
  id: string;
  name: string;
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

export type Offer = {
  tools: Offered[];
  models: string[];
  parts: PartRule[];
  no_part: string[];
  limits: Record<string, Limit>;
  servable: Servable[];
  askable: Askable[];
  owed?: string[];
};

// One of the scenario's tools an agent may be given, with what it reads, writes or
// changes.
export type Offered = {
  name: string;
  description: string | null;
  reads: boolean;
  writes: boolean;
  destructive: boolean;
  sends_outside: boolean;
  changes: string | null;
  handles: string[];
  outside: string[];
};

// A part of the business, as the settings in force know it: who decides a change to one
// of its records below level 2, by name, who approves an instance that works in it, its
// owners, and how right graded samples must show an agent's changes there before a5s raises
// its cap to level 2, if it ever may.
export type PartRule = {
  name: string;
  deciders: string[];
  owners: string[];
  threshold: number | null;
};

// Its authors' plan for a draft's first instance: the parts it would work in, whom it
// would serve, and the instances it could ask. Never in force: the signed settings are, which
// those parts' owners approve, and putting it to work starts from it.
export type Plan = {
  parts?: string[];
  serves?: string[];
  asks?: string[];
};

// A publish under way: the code to enter at GitHub's sign-in, and how it stands.
export type Publish = {
  id: string;
  status: "signing in" | "opened" | "refused" | "lapsed";
  agent: string;
  user_code: string | null;
  verify_at: string | null;
  interval: number;
  expires_in: number;
  pull: string | null;
  problem: string | null;
  branch: string;
};

// A draft's pull request, for its author to open themselves: where its folder goes, and
// what it says.
export type PullRequest = {
  folder: string;
  title: string;
  body: string;
  ready: boolean;
};

export type Questions = {
  instance: string;
  asked: number;
  answered: number;
  unanswered: number;
  answered_seconds_p90: number | null;
};

// What an agent's release lets its instances be set to: the level it starts at, the most it
// allows, and the types of change its own tools make.
export type ReleaseLevels = {
  starts: number;
  most: number;
  actions: string[];
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
  name: string;
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
  fewer: number | null;
};

export type Samples = {
  graded: number;
  right: number;
  wrong: number;
  critical: number;
  lapsed: number;
  right_share: number | null;
};

// Whom a draft may be tried as, of the sandbox's made-up people, and on which models.
export type Sandbox = {
  people: Named[];
  models: string[];
};

// When an agent works on its own, in its instance owner's time zone, and what it's asked.
export type Schedule = {
  name: string;
  at: string[];
  days: string[];
  task: string;
};

export type Sent = {
  messages: SentMessage[];
  tools?: Record<string, unknown>[];
  [key: string]: unknown;
};

export type SentMessage = {
  role: string;
  content?: unknown;
  tool_calls?: Record<string, unknown>[];
  [key: string]: unknown;
};

// Someone an instance could serve, as the settings name them, or whoever is signed in: a
// person by their name, or a team or a role as written.
export type Servable = {
  id: string;
  name: string;
};

// Which of an agent's instances is to serve someone who asked for it.
export type Serve = {
  instance: string;
};

// A version asked for, which a5s proposes to everyone it needs within a minute.
export type SettingsAsked = {
  request: number;
  serial: number;
};

// The settings, for someone who approves versions of them: the version in force, what the
// forms offer, the versions waiting for approval, and what they asked for lately.
export type SettingsNow = {
  you: string;
  me: string;
  in_force: InForce | null;
  names: Record<string, string>;
  actions: string[];
  releases: Record<string, ReleaseLevels>;
  waiting: VersionWaiting[];
  requests: SettingsRequest[];
};

// A version someone asked for, and what became of it.
export type SettingsRequest = {
  asked_at: string;
  serial: number;
  outcome: string;
  link: string | null;
};

// A version someone wrote, reviewed before they ask for it: why a5s couldn't propose it, or
// what it would change, all of it in words, and whose approval it needs.
export type SettingsReview = {
  problems: string[];
  serial?: number;
  in_force?: number | null;
  changes?: Change[];
  whole?: string[];
  approvers?: string[];
};

// Whose signature a draft's release would need, and why: and who holds that role in the
// directory, by name, where a person holds it; for a new agent's owner, nobody, till the
// directory names someone.
export type Signer = {
  role: string;
  who: string;
  why: string;
  held_by?: string[] | null;
};

// How an instance stands, for someone who may watch it: what of it waits, each where it's
// done; who suspended it, if it's suspended; what they may do to it from its page, suspend it
// or resume it, if either; and what was asked for there that a5s hasn't carried out yet.
export type Standing = {
  waiting: Waiting[];
  suspended_by: string | null;
  may: string | null;
  asked: StatusAsked | null;
};

// Suspending or resuming an instance from its page: which, and the salt the page made its
// sign-in's nonce with.
export type StatusAct = {
  action: string;
  salt: string;
};

// Suspending or resuming an instance, asked for on its page, which a5s carries out within
// a minute, once it has checked the sign-in that asked for it again (core/suspension.py).
export type StatusAsked = {
  action: string;
  by: string;
  at: string;
};

// An agent a new one may start from, and the tools it needs that the scenario hasn't.
export type Template = {
  name: string;
  works_for: string;
  does: string;
  model: string;
  tools: string[];
  lacks: string[];
};

export type Templates = {
  templates: Template[];
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

export type Tried = {
  agent: string;
  reply: string;
  run: TriedRun | null;
  model_calls: ModelCall[];
};

// A try's run, as the sandbox shows it: its entries in the sandbox's own ledger too, of
// made-up people alone.
export type TriedRun = {
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
  entries: Record<string, unknown>[];
};

export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

// A version waiting for approval: what it changes, who approved it so far, and why it still
// waits, on its own page.
export type VersionWaiting = {
  serial: number;
  link: string;
  changes: Change[];
  approved_by: string[];
  needs: string[];
};

// Something that waits for someone: what it is, why it's theirs, and where they do it, a
// page of a5s's, or the command line.
export type Waiting = {
  kind: string;
  what: string;
  why: string[];
  go: string | null;
  how?: string;
  since?: string;
};

// A version of the settings as someone wrote it in the settings app, and the version in
// force they reviewed it against, by its serial, once they have.
export type Written = {
  text: string;
  base?: number | null;
};

export type You = {
  you: string;
  id: string;
  roles: Role[];
  groups: string[];
};
