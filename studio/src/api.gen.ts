// The studio API's types, made from its description by `uv run python -m a5s.core.studio_api`:
// don't edit them here, but in core/studio_models.py, and make them again.
export type ActedFor = {
  id: string;
  name: string | null;
};

// An administrative act, as the ledger records it: who did it, when, and to what, with whom
// it was about as a stand-in until the officer agrees to names.
export type AdminAct = {
  seq: number;
  at: string | null;
  action: string;
  what: string;
  by: string | string[] | null;
  instance: string | null;
  about: Record<string, unknown>;
};

// The administrators' page: who holds each role and by what, what waits for whom, what
// nobody answers for, and the latest acts.
export type AdminNow = {
  you: string;
  roles: RoleHeld[];
  groups: GroupGives[];
  claim: string | null;
  waiting: AdminWaiting;
  ownerless: Ownerless;
  days: number;
  latest: AdminAct[];
};

// What waits for whom: versions of the settings, the release, and held changes.
export type AdminWaiting = {
  settings: VersionNeeds[];
  release: string[];
  held_changes: HeldIn[];
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
  events?: EventTaken[];
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

// An owner's grade of an answer someone said was wrong: right, wrong or critical.
export type AnswerGrade = {
  grade: string;
};

export type AnswerGraded = {
  id: number;
  grade: "right" | "wrong" | "critical";
};

// An agent's answers people said were wrong, as an owner of it may check them: newest
// first, how many others there are, how many wait, and how many have each grade.
export type AnswersSaidWrong = {
  agent: string;
  answers: SaidWrong[];
  hidden: number;
  waiting: number;
  graded: Record<string, number>;
};

// What the approval page sends with its sign-in: the salt its nonce was made with.
export type Approval = {
  salt: string;
};

// An approval recorded, for the gateway to check again, seal, and count.
export type Approved = {
  approved: boolean;
  serial: number;
  by: string;
  needs: string[];
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

// What the officer's page sends with its sign-in: what it's to do, for whom, and the salt
// its nonce was made with.
export type Asking = {
  action: string;
  person: string;
  salt: string;
};

// A page of a period's entries, as the auditor asked, and where the next begins.
export type AuditEntries = {
  entries: Record<string, unknown>[];
  next: number | null;
};

// A page of a period's entries exactly as the ledger holds them, to check and keep, with what
// proves they're its own: the entries either side, and the chain's head.
export type AuditExport = {
  entries: Record<string, unknown>[];
  next: number | null;
  head: Record<string, unknown> | null;
  bounds: Record<string, unknown>;
};

// Who's reading the trail, and how it shows people: by name, or by stand-in.
export type AuditNow = {
  you: string;
  names: boolean;
  exports: boolean;
  kinds: string[];
};

// Who holds each role, and who did what of a period's administration.
export type AuditReport = {
  roles: RoleHolders[];
  acts: AdminAct[];
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
  model?: string;
  seconds?: number;
  tokens?: number;
  cost?: number | null;
  judge_tokens?: number;
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

// A change a5s made for someone, as its page shows whoever it was for, and whoever may undo
// it: what it did, until when it can be undone, and how it stands.
export type ChangeMade = {
  id: number;
  agent: string;
  instance: string;
  record: string;
  said: string;
  made_at: string;
  until: string;
  whom: string[];
  may: boolean;
  why_not?: string;
  state: string;
  by?: string;
  outcome?: string;
};

export type CoAuthors = {
  people: Named[];
};

// A system someone may connect their own account in, so agents act there as them, with
// their permissions: whether they have, since when, and when a5s last did.
export type Connection = {
  system: string;
  title: string;
  connected: boolean;
  connecting: boolean;
  scopes: string[];
  connected_at?: string;
  used_at?: string;
  reads: string[];
};

export type ConnectionBack = {
  system: string;
  title: string;
  connecting: boolean;
};

// What a system sent someone back to a5s with, once they said whether a5s may act for them
// there: the start's state, and its code, or the error it gave for a no.
export type ConnectionReturn = {
  state: string;
  code?: string | null;
  error?: string | null;
};

export type ConnectionStarted = {
  go: string;
};

export type Connections = {
  connections: Connection[];
};

// What an agent's runs are given beyond the conversation.
export type Context = {
  budget_tokens: number;
  recall: boolean;
  documents: boolean;
  agents: boolean;
  notebook: boolean;
  handover: boolean;
};

// One day's runs, by how each ended, in the viewer's own time zone.
export type Day = {
  day: string;
  runs: number;
  ended: Record<string, number>;
};

// The held changes someone may decide now, those they were told of, and those they decided
// lately.
export type DecideNow = {
  you: string;
  proposals: HeldChange[];
};

// A decision recorded, for the core to check again, seal and act on.
export type Decided = {
  decided: string[];
  decision: string;
  by: string;
};

// What the decision page sends with a sign-in made to decide: the changes it decides, by
// their digests, the decision, the salt its nonce was made with, and, for a rejection, why,
// if the decider says.
export type Deciding = {
  proposals: string[];
  decision: string;
  salt: string;
  reason?: string | null;
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
  events: EventTaken[];
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

// The map, as someone may see it.
export type DependsOn = {
  nodes: MapNode[];
  edges: MapEdge[];
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

export type Disconnected = {
  forgotten: boolean;
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
  loaded?: string | null;
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

// What another system may tell an agent happened, and what it's asked to do each time.
export type EventTaken = {
  type: string;
  source: string;
  task: string;
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

// The samples someone may grade now, oldest first.
export type GradeNow = {
  you: string;
  samples: SampleLine[];
};

// Grades recorded, for the core to check again and seal.
export type Graded = {
  graded: number[];
  grades: Record<string, string>;
  by: string;
};

// What the grading page sends with a sign-in made to grade: the grades, by sample, and the
// salt its nonce was made with.
export type Grading = {
  grades: Record<string, string>;
  salt: string;
};

export type GroupChats = {
  agent: string;
  messages: number;
  chats: number;
  people: number;
};

// A group of the identity provider's that the settings give roles, and how many it holds.
export type GroupGives = {
  group: string;
  roles: string[];
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

export type Handover = {
  id: number;
  person: string;
  agent: string;
  team: string;
  brief: string;
  started_at: string;
  taken_by?: string;
  mine: boolean;
  unanswered: number;
  said: HandoverSaid[];
  since: HandoverSince[];
  answers: HandoverAnswer[];
  ended: boolean;
};

export type HandoverAnswer = {
  by: string;
  text: string;
  at: string;
  sent: boolean;
};

export type HandoverDone = {
  done: boolean;
};

// A conversation handed to one of someone's teams: whose, with which agent, its brief, who
// of the team has taken it, and how many of the person's messages wait for an answer.
export type HandoverLine = {
  id: number;
  person: string;
  agent: string;
  team: string;
  brief: string;
  started_at: string;
  taken_by?: string;
  mine: boolean;
  unanswered: number;
};

// What someone of a team answers a person whose conversation was handed to it.
export type HandoverReply = {
  text: string;
};

export type HandoverSaid = {
  at: string;
  text: string;
};

export type HandoverSince = {
  at: string;
  text: string;
  answered: boolean;
};

export type Handovers = {
  handovers: HandoverLine[];
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

// A change an agent asked for, held for a person to decide: in the words code worked out when
// it was asked for, who asked and for whom, what to know, and whether the viewer may decide it.
export type HeldChange = {
  key: string;
  digest: string;
  said: string;
  agent: string;
  for: string[];
  flags: string[];
  sensitive: boolean;
  status: string;
  yours: string | null;
  may_decide: boolean;
  outcome: string | null;
  proposed_at: string;
  lapses_at: string;
  links: string[];
  records: RecordLink[];
  changed: string[];
};

// Changes agents asked for in a part, waiting, and who may decide them.
export type HeldIn = {
  part: string;
  waiting: number;
  deciders: string[];
};

// Someone who holds a role, and what gave it them: the directory, or a group.
export type Holder = {
  id: string;
  name: string;
  by: string[];
};

export type Home = {
  you: string;
  waiting: Waiting[];
  drafts: DraftLine[];
  authoring: boolean;
};

// What a version would have done differently in the last weeks, decided again from the
// ledger's tool calls, and what it can't know.
export type Impact = {
  days: number;
  calls: number;
  limited: boolean;
  shifts: Shift[];
  capped: string[];
  about: string;
  hidden: number;
  beyond?: string[];
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

// A language a5s's pages speak, by its code, named in its own words.
export type Language = {
  code: string;
  name: string;
};

// The language someone chooses a5s's pages speak to them in, by its code, such as th.
export type LanguageChoice = {
  language: string;
};

export type LanguageChosen = {
  language: string;
};

// The scenario's limits for a type of change: past either, a change waits for a person,
// whatever the level.
export type Limit = {
  per_run: number | null;
  per_person_30_days: number | null;
};

// That one thing depends on another, and how, in words, such as "may call it".
export type MapEdge = {
  from: string;
  to: string;
  says: string;
};

// A thing on the map of what depends on what (core/dependencies.py): its kind, part,
// instance, agent, tool, system, model or team; its name; what it is, in a few words; its page in
// the studio, if it has one; and, for a tool, what it does: reads, writes, sends outside or
// changes records.
export type MapNode = {
  key: string;
  kind: string;
  name: string;
  about: string;
  at: string | null;
  tone: string | null;
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

// Something nobody answers for any more, what's wrong, and what to do.
export type Nobodys = {
  what: string;
  do: string;
  agent?: string;
  instance?: string;
  part?: string;
};

// A note an agent kept, with the records it comes from, when it was noted, and when its
// records were last checked.
export type Note = {
  entry: string;
  instance: string;
  text: string;
  sources: NoteSource[];
  noted: string;
  checked: string;
};

// A note removed, by its keeper.
export type NoteRemoved = {
  removed: string;
};

// A record a note comes from, by its key, and its link in its system, if it has one.
export type NoteSource = {
  key: string;
  link: string | null;
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

// The notes of the instances someone keeps, those whose every record they may see, how many
// more there are that they may not, and who else keeps those.
export type NotebookNow = {
  you: string;
  instances: string[];
  names: Record<string, string>;
  entries: Note[];
  hidden: number;
  others: string[];
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
  marks: boolean;
};

// The officer's request, recorded for the team that runs a5s to carry out, once, with the
// command it's carried out with.
export type OfficerAsked = {
  asked: string;
  person: string;
  name: string | null;
  by: string;
  lasts: string;
  command: string;
};

// The agents, instances and parts nobody answers for.
export type Ownerless = {
  agents: Nobodys[];
  instances: Nobodys[];
  parts: Nobodys[];
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

// One of a5s's pages, as every sidebar and the studio's palette show it: its key, its
// name, its icon, the heading it's under, and its address.
export type Place = {
  page: string;
  name: string;
  icon: string;
  group: string;
  at: string;
};

// Its authors' plan for a draft's first instance: the parts it would work in, whom it
// would serve, and the instances it could ask. Never in force: the signed settings are, which
// those parts' owners approve, and putting it to work starts from it.
export type Plan = {
  parts?: string[];
  serves?: string[];
  asks?: string[];
};

// A step of a task's plan, as its run keeps it, and how it stands.
export type PlanStep = {
  content: string;
  status: string;
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

// A record a held change names, and its address in its system.
export type RecordLink = {
  key: string;
  link: string;
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

// A task someone asked to be done again and again: when, how it stands, and its last task;
// or, where its words name records they may no longer see, how it stands alone.
export type RepeatLine = {
  repeat: string;
  agent: string;
  when: string;
  status: string;
  "last task"?: string;
  what?: string;
  withheld?: boolean;
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

// A role, in words, and who holds it.
export type RoleHeld = {
  role: string;
  name: string;
  held_by: Holder[];
};

// A role, and who holds it now.
export type RoleHolders = {
  role: string;
  held_by: string[];
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
  tokens_cache_written?: number;
  records: string[];
  calls: Call[];
};

export type RunCase = {
  name: string;
  speaker: string;
  steps: RunCaseStep[];
};

// A run kept as a test case: its name, the made-up person who says it, what they say, as
// its author checked it, what a right answer is, if they say, and that they checked it.
export type RunCaseAsked = {
  name: string;
  speaker: string;
  say: string;
  judged?: string | null;
  checked?: boolean;
};

// A run kept as a test case: the draft it went in, its file, and the case as kept.
export type RunCaseKept = {
  draft: string;
  file: string;
  case: RunCase;
};

// A run as a test case, for its author to check and keep (core/run_cases.py): what was
// said to the agent and what it answered, masked by code; how many of each kind code masked,
// such as names; the tools it used, which a5s let it, or held for someone to decide; and
// whether the run read content from outside, which the case can't keep.
export type RunCaseOffered = {
  run: string;
  agent: string;
  say: string;
  answer: string;
  masked: Record<string, number>;
  uses: string[];
  read_outside?: boolean;
};

export type RunCaseStep = {
  say: string;
  uses?: string[];
  judged?: string;
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

// An agent's answer someone said was wrong (core/feedback.py): when, the instance and run
// behind it, the chat it was in, the answer, why, in their words, if they said, and its grade,
// if an owner has given one; who said it only once the officer agrees to names.
export type SaidWrong = {
  id: number;
  at: string;
  instance: string | null;
  run: string;
  channel: string;
  answer: string;
  said: string | null;
  grade: "right" | "wrong" | "critical" | null;
  graded_at: string | null;
  graded_by: string | null;
  by: string | null;
};

// A sample of an agent's change, waiting for a grade: in the words code worked out when it was
// asked for or made, how it went, what code flagged, and its records as they stood then.
export type SampleLine = {
  id: number;
  kind: string;
  agent: string;
  part: string;
  action: string;
  said: string;
  records: Record<string, Record<string, unknown> | null>;
  flags: string[];
  decided: string | null;
  drawn_at: string;
};

export type Samples = {
  graded: number;
  right: number;
  wrong: number;
  critical: number;
  lapsed: number;
  right_share: number | null;
};

// Whom a draft may be tried as, of the sandbox's made-up people, and on which models, with
// the currency models.yaml prices them in, if it names one.
export type Sandbox = {
  people: Named[];
  models: string[];
  currency?: string | null;
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
  currency?: string | null;
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
  impact?: Impact;
};

export type ShadowCounts = {
  better: number;
  same: number;
  worse: number;
  wrong: number;
};

// How a shadow did: how many it answered, and how graders, and its judge, apart, graded
// its answers.
export type ShadowFigures = {
  instance: string;
  shadows: string;
  agent: string;
  status: string;
  answered: number;
  graded: ShadowCounts;
  judged: ShadowCounts;
};

export type ShadowGrade = {
  grade: string;
};

export type ShadowGraded = {
  graded: boolean;
};

// What someone asked an instance, what it answered them, and what its shadow, a new
// version, answered beside it, which went nowhere: for a grader, never whose it was.
export type ShadowPair = {
  id: number;
  agent: string;
  shadow: string;
  asked: string;
  sent: string;
  answer: string;
  at: string;
};

export type Shadows = {
  pairs: ShadowPair[];
  shadows: ShadowFigures[];
};

// Who signed in, the language they read, and the pages they may use, in the sidebar's
// order.
export type Shell = {
  you: string;
  language: string;
  pages: Place[];
};

// Calls a version would decide differently from the one in force (core/impact.py): of one
// tool, by one instance, about records in these parts.
export type Shift = {
  instance: string;
  tool: string;
  parts: string[];
  was: string;
  would: string;
  calls: number;
  why: string;
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

// A month of an agent's or instance's model calls: what they cost so far at their
// models' prices, its budget, if the settings set one, and while the month lasts, the pace of
// the last week and the forecast to its end; its runs, those whose prices aren't known, the
// messages they answered, and what each message cost, all in.
export type Spend = {
  key: string;
  spent: number;
  budget: number | null;
  pace: number | null;
  forecast: number | null;
  runs: number;
  unpriced: number;
  answered: number;
  tokens: number;
  per_answer: number | null;
  agent?: string;
  parts?: string[];
};

// A calendar month's spending, in UTC, as someone may see it: its agents and instances,
// in the currency models.yaml prices models in, if it names one.
export type Spending = {
  month: string;
  current: boolean;
  currency: string | null;
  budget_currency?: string | null;
  compared?: boolean;
  starts: string;
  ends: string;
  days: number;
  day: number;
  agents: Spend[];
  instances: Spend[];
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

// One of someone's tasks, with an agent: how it stands, what it waits on, and what it has
// spent; or, where its words name records they may no longer see, how it stands alone.
export type TaskLine = {
  task: string;
  agent: string;
  status: string;
  ended: boolean;
  progress: number;
  "has until": string;
  spent: string;
  updated: string;
  parts?: string;
  withheld?: boolean;
  what?: string;
  plan?: PlanStep[];
  why?: string;
  needed?: string | null;
  said?: string | null;
  found?: unknown;
  "so far"?: unknown[];
};

// A task cancelled, or a repeat stopped, at its owner's word.
export type TaskStopped = {
  cancelled?: string;
  stopped?: string;
};

// Someone's own tasks, with every agent, and what they asked to be done again and again.
export type TasksNow = {
  you: string;
  tasks: TaskLine[];
  repeats: RepeatLine[];
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
  marks: boolean;
  pinned: string | null;
  missing: boolean;
};

export type Tried = {
  agent: string;
  reply: string;
  run: TriedRun | null;
  model_calls: ModelCall[];
  tokens?: number;
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
  tokens_cache_written?: number;
  records: string[];
  calls: Call[];
  entries: Record<string, unknown>[];
};

// Undoing a change, signed in afresh for that act alone: the salt its nonce was made with.
export type UndoAct = {
  salt: string;
};

export type UndoAsked = {
  change: number;
  at: string;
};

export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

// A version of the settings waiting, who approved it, and whose approval it still needs.
export type VersionNeeds = {
  serial: number;
  approved_by: string[];
  needs: string[];
};

// A version of the settings as its approvers see it before approving it: what it changes
// from the one in force, in words code worked out, all of it, who approved it so far and what
// it still needs, who asked for it, and where it stands.
export type VersionReview = {
  serial: number;
  proposed_at: string;
  in_force: number | null;
  changes: Change[];
  whole: string[];
  needs: string[];
  approved_by: string[];
  asked_by: string | null;
  you: string;
  you_approved: boolean;
  status: string;
  impact?: Impact;
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
  language: string;
  languages: Language[];
};
