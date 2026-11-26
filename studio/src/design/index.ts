// a5s's design system, as the studio draws it (docs/design.md): its look is app.css's tokens and
// classes, which every page shares; these are the pieces pages are made of.

export { AgentFacts, ApprovalCard, AutonomyLadder, JourneyPath, rung, RunTimeline, Traced } from "./agentic";
export type { Change, FactsPart, Stage, Step } from "./agentic";
export { Badge, Confirm, Hint } from "./controls";
export type { Tone } from "./controls";
export { Avatar, initials, Who } from "./people";
export { Loading, Shapes, Skeleton, Toasts, useToast } from "./feedback";
export { Palette } from "./palette";
export { ActingAs, ActionZone, EnvironmentBand, environmentOf } from "./safety";
export type { PaletteOption } from "./palette";
export type { Kind } from "./people";
