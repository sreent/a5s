// The people's studio API in the channels app, as the signed-in person may read it: each call
// carries their sign-in, kept in memory alone while the studio is open. A sign-in runs out, as
// the identity provider sets it, and then the studio asks them to sign in again (round 13, C1).

let token = "";
let until = 0;  // when it runs out, in seconds, as the sign-in itself says
const outListeners = new Set<() => void>();

export function signedIn(idToken: string): void {
  token = idToken;
  try {
    const part = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const exp = JSON.parse(atob(part)).exp;
    until = typeof exp === "number" ? exp : 0;
  } catch {
    until = 0;
  }
}

/** Whether the sign-in has run out, as it says itself. */
export function runOut(): boolean {
  return until > 0 && Date.now() / 1000 >= until;
}

/** When the sign-in runs out, in milliseconds, or 0 if it doesn't say. */
export function runsOutAt(): number {
  return until * 1000;
}

/** Hear when a call is refused because the sign-in has run out. */
export function onRunOut(then: () => void): () => void {
  outListeners.add(then);
  return () => outListeners.delete(then);
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
    if (answer.status === 401 && runOut()) outListeners.forEach((then) => then());
    const detail = found.detail;  // words, or, from the settings, the problems a version has
    const said = typeof detail === "string" ? detail
      : Array.isArray(detail?.problems) ? detail.problems.join(" ") : `a5s said ${answer.status}.`;
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

// What the API gives: its types, made from its own description (api.gen.ts, which
// `uv run python -m a5s.core.studio_api` makes from core/studio_models.py), so they're always
// what the code answers. Names the pages use stand for them here.
import type * as gen from "./api.gen";

export type Tool = gen.Tool;
export type Instance = gen.Instance;
export type Schedule = gen.Schedule;

// What someone sees of an agent comes in layers, each from the roles they hold (core/studio.py):
// that it exists; what it may do; how it's built; how it's doing; what it did; changing it
export type Layer = "exists" | "uses" | "built" | "doing" | "did" | "changing";

// That it exists: for anyone who may know of it. A layer they don't see is left out.
export type AgentKnown = gen.Agent;
// What it may do: for the people it serves, those who watch its instances, and its makers
export type AgentUses = AgentKnown & Required<Pick<AgentKnown,
  "tools" | "a5s_tools" | "model" | "autonomy" | "triggers" | "schedules" | "reports" |
  "obligations" | "reminders" | "preferences" | "channels" | "context" | "budget">>;
// How it's built: for its owners, authors, engineers, release approvers, auditors and viewers
export type Agent = AgentUses & Required<Pick<AgentKnown, "skills">>;

export const usesOf = (agent: AgentKnown): agent is AgentUses => "tools" in agent;
export const builtOf = (agent: AgentKnown): agent is Agent => "skills" in agent;

// Asking for an agent (core/asks.py)
export type Ask = gen.Ask;
export type Asked = gen.Asked;
export type Catalogue = gen.Catalogue;

// Someone's home and roles (core/home.py)
export type Home = gen.Home;
export type Waiting = gen.Waiting;
export type SettingsNow = gen.SettingsNow;  // the settings, for someone who approves versions of them
export type SettingsReview = gen.SettingsReview;
export type SettingsAsked = gen.SettingsAsked;
export type Change = gen.Change;  // a change a version makes, in words, and whether it widens what agents do
export type NotebookNow = gen.NotebookNow;  // the notes of the instances someone keeps
export type Note = gen.Note;
export type TasksNow = gen.TasksNow;  // someone's own tasks, and what they asked to be done again and again
export type TaskLine = gen.TaskLine;
export type RepeatLine = gen.RepeatLine;
export type AdminNow = gen.AdminNow;  // the administrators' page
export type AdminAct = gen.AdminAct;
export type AuditNow = gen.AuditNow;  // the audit trail, for auditors and assurance
export type AuditEntries = gen.AuditEntries;
export type AuditReport = gen.AuditReport;
export type AuditExport = gen.AuditExport;
export type DecideNow = gen.DecideNow;  // the held changes someone may decide, and lately decided
export type HeldChange = gen.HeldChange;
export type Decided = gen.Decided;
export type GradeNow = gen.GradeNow;  // the samples someone may grade now
export type SampleLine = gen.SampleLine;
export type Graded = gen.Graded;
export type OfficerAsked = gen.OfficerAsked;  // the officer's request, recorded
export type VersionReview = gen.VersionReview;  // a version of the settings, as its approvers read it
export type Approved = gen.Approved;
export type Standing = gen.Standing;  // how an instance stands, for its viewer: what waits, and what they may do
export type StatusAsked = gen.StatusAsked;  // a suspension or resumption asked for, which a5s carries out
export type You = gen.You;
export type Role = gen.Role;

// Making agents: drafts, trying them in the sandbox, and publishing them (core/drafts.py)
export type Template = gen.Template;
export type DraftLine = gen.DraftLine;
export type Draft = gen.Draft;
export type Signer = gen.Signer;  // whose signature a draft's release would need, and why
export type Defined = gen.Defined;  // an agent as its folder defines it: a draft's preview
export type Offered = gen.Offered;
export type Offer = gen.Offer;
export type PartRule = gen.PartRule;  // who decides a part's changes, and its threshold for level 2
export type Limit = gen.Limit;
export type Plan = Required<gen.Plan>;  // its authors' plan for a draft's first instance, never in force
/** A plan as the API gives it, which leaves out what's empty, whole. */
export const whole = (plan: gen.Plan | undefined): Plan => ({ parts: [], serves: [], asks: [], ...plan });
export type Servable = gen.Servable;
export type Askable = gen.Askable;
export type Templates = gen.Templates;
export type Drafts = gen.Drafts;
export type CoAuthors = gen.CoAuthors;
export type Named = gen.Named;
export type Sandbox = gen.Sandbox;
export type Tried = gen.Tried;
export type ModelCall = gen.ModelCall;
export type SentMessage = gen.SentMessage;  // a provider's own, as it went
export type Cases = gen.Cases;
export type CaseLine = gen.CaseLine;
export type CaseStep = gen.CaseStep;
export type CaseRan = gen.CaseRan;
export type Publish = gen.Publish;
export type PullRequest = gen.PullRequest;

export type ModelRuns = gen.ModelRuns;
export type Figures = gen.Figures;
/** One day's runs, by how each ended, as core/status.py's outcome() says it. */
export type Day = gen.Day;
export type Person = gen.ActedFor;
export type RunLine = gen.RunLine;
export type RunsPage = gen.RunsPage;
export type Call = gen.Call;
export type Run = gen.Run;
