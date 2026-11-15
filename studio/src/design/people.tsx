// Who did something. People are round, with their initials; agents are rounded squares in the
// agent colour, with the agent's mark, wherever either appears (docs/design.md).

import { Icon } from "../icons";

export type Kind = "person" | "agent";

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word.charAt(0).toUpperCase()).join("");
}

export function Avatar({ name, kind }: { name: string; kind: Kind }) {
  return kind === "agent"
    ? <span className="avatar agent" aria-hidden="true"><Icon name="agent" /></span>
    : <span className="avatar" aria-hidden="true">{initials(name)}</span>;
}

/** Someone, or an agent, by name, with a line about them. */
export function Who({ name, kind, about }: { name: string; kind: Kind; about?: string }) {
  return (
    <span className="who" data-kind={kind}>
      <Avatar name={name} kind={kind} />
      <span>
        <span className="who-name">{name}</span>
        {about && <span className="who-about">{about}</span>}
      </span>
    </span>
  );
}
