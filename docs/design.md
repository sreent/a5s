# Design

Every page of a5s, the studio and the server's own pages alike, shares one look, built on tokens that are tested. It's calm, with colour only where it means something, and it makes plain what an agent may do, what it did, and who decides.

## Ocean

The look is called Ocean. It takes a hint of the sea: deep blues for what you can do, lagoon teal for agents, coral for any change to a record, and kelp green for what's going well. The palette isn't anyone's brand. An organisation's own colours replace the primitives, in one place.

## Tokens, in two layers

The tokens live at the top of [`app.css`](../src/a5s/core/webchat/app.css). The studio imports the same file, so nothing is defined twice.

| Layer | What it holds | Example |
| --- | --- | --- |
| Primitives | The palette, type, spacing and radii. A brand changes these alone. | `--ocean-600`, `--space-4`, `--radius-md` |
| Meanings | What each colour is for, in light and dark. Every other style names only these. | `--text`, `--accent`, `--agent-tone`, `--changes` |

The meanings that matter most are a5s's own grammar, which is the same on every surface: the agent's map, badges, cards and the ledger.

| What a tool does | Token | How something stands | Token |
| --- | --- | --- | --- |
| Reads | `--reads` | Going well | `--good` |
| Writes, such as a draft | `--writes` | Waiting on someone | `--warn` |
| Changes a record | `--changes` | Failed | `--bad` |
| Reads from outside | `--outside` | Paused | `--idle` |
| a5s's own | `--own` | | |

Agents are drawn in `--agent-tone`, and people never are, so a page shows at a glance whether a person or an agent did something.

## Type

IBM Plex Sans for text, and IBM Plex Mono for ids and digests. a5s bundles both, under the SIL Open Font License ([`fonts/`](../src/a5s/core/webchat/fonts)), and the pages' policy loads fonts only from a5s itself, so a page loads nothing from outside, which matters on premises. Plex also has a Thai family designed to match, for when a5s needs one.

## What the tests hold it to

[`tests/test_design.py`](../tests/test_design.py) checks that:

- every colour that carries text reads against what it sits on at 4.5 to 1, as WCAG's AA asks, and focus rings and agents' marks at 3 to 1, in light and dark;
- the meanings name only primitives, so a brand is one change in one place;
- the pages load their type from a5s and from nowhere else.

A brand that reads less well fails the first test before anyone sees it.

## To change the brand

1. Change the primitives in `app.css`: the palette, and the fonts if the brand has its own, in `fonts/`.
2. Run `uv run pytest tests/test_design.py`, and adjust any colour it names until each reads.
3. Build the studio (`npm run build` in `studio/`), so it carries the change too.

## Components

The pieces pages are made of live in [`studio/src/design`](../studio/src/design), with their look in `app.css`, so a page outside the studio can draw them too. The showcase, at `/studio/design`, shows each one as pages use it, in light or dark as the device is.

| Piece | What it's for |
| --- | --- |
| `Who`, `Avatar` | Who did something: people round, with their initials; agents as rounded squares in `--agent-tone` |
| `Badge` | What a tool does, or how something stands, in the colour that means it |
| `Traced` | A value an agent used, which opens to show its record, when it was read, by which run and for whom, and whether it still holds |
| `ApprovalCard` | What an agent asks someone to decide, at a phone's width at most: what it changes, why, and their yes or no, signed and kept in the ledger |
| `AgentFacts` | An agent's facts, as food carries a label, the same for every agent: what it may do, and how it does per run |
| `AutonomyLadder` | The level an agent works at, the levels its release allows beyond it, and how far it has come toward the next |
| `RunTimeline` | A run as time: each step in order, in the colour of what it did |
| `Confirm` | Asking first, for what can't be undone, in the browser's own dialog |
| `Hint` | A word on what something means, for whoever points at it or tabs to it |

The popover a traced value opens and the hint are Radix's, which keyboards and screen readers reach as they do the mouse. The dialog is the browser's own: it keeps focus in it and the page behind it out of reach without injecting styles of its own, which the pages' policy wouldn't allow.

The browser tests open the showcase signed in, and check that:

- each piece is there;
- [axe](https://github.com/dequelabs/axe-core) finds nothing amiss in light or dark, by WCAG's rules and its best practices, as on every page people use (`tests/test_ui_pages.py`);
- each piece works from the keyboard: a traced value opens and closes with focus back on it, a hint shows to whoever tabs to it, and the dialog starts on "Keep it" and closes with Escape even when a hint was open;
- nothing on the page writes an error to the console, such as a style the pages' policy refused.

## Pages

Each page's title is its first-level heading, its sections' are the second level and theirs the third, the studio's pages and the server's alike; the sidebar names a5s. The pages are moving onto the pieces:

- **Decisions** are approval cards, made for a phone: who asks and for whom, what the change does in the words code worked out when it was asked for, never the agent's own, what to know, and Approve or Reject. The cards make a column on a phone and sit side by side where there's room.
- **The catalogue** leads each agent's card with what it does, and the agent's map draws it in the agent colour.
- **Each agent's page** leads its side with the agent's facts, from its release alone: its model and autonomy, its tools by what they do, and what it may spend. Where all its instances work at one level, its ladder follows, which stacks its steps wherever it's narrow.
- Next: a run as a timeline.
