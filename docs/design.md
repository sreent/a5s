# Design

Every page of a5s, the studio and the server's own pages alike, shares one look, built on tokens that are tested. It's calm, with colour only where it means something, and it makes plain what an agent may do, what it did, and who decides.

## Ocean

The look is called Ocean. It takes a hint of the sea: deep blues for what you can do, lagoon teal for agents, coral for any change to a record, and kelp green for what's going well. Its hues sit between MathWorks' colours and Maple's, each step's lightness fitted to the contrast its meanings need ([where the colours come from](https://github.com/sreent/ocean/blob/main/docs/design.md#where-the-colours-come-from)). An organisation's own colours replace the primitives, in one place.

Ocean began here, and is now the look a5s shares with a7c and a3t, kept in its one source, [sreent/ocean](https://github.com/sreent/ocean), with its brand book, its pieces and its checks. a5s's pages load only a5s's own files, so a5s serves a copy: Ocean's tokens, its pieces, its chart colours and IBM Plex, in [`webchat/ocean`](../src/a5s/core/webchat/ocean), at the commit [`ocean.json`](../src/a5s/core/webchat/ocean/ocean.json) names, with each file's digest. Every page loads Ocean's tokens and pieces first, then [`app.css`](../src/a5s/core/webchat/app.css), which holds a5s's own alone, the chat; the studio imports the same files, and its own [`studio.css`](../studio/src/studio.css) holds only how its pages lay Ocean's pieces out: an agent's card, an instance's figures, the runs chart, the sandbox's turns and test cases. Neither restyles a piece of Ocean's. A piece a5s needs, or a change to one, is drawn in sreent/ocean first, for a7c and a3t too, and taken here at its commit:

```bash
sh deploy/ocean.sh <commit>
```

## Tokens, in two layers

The tokens live in Ocean's [`css/tokens.css`](../src/a5s/core/webchat/ocean/css/tokens.css).

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

IBM Plex Sans for text, and IBM Plex Mono for ids and digests, both with the letters Vietnamese adds to Latin, and IBM Plex Sans Thai, drawn to match, for Thai letters. Ocean bundles all three, under the SIL Open Font License, and a5s serves its copy ([`ocean/fonts`](../src/a5s/core/webchat/ocean/fonts)): the pages' policy loads fonts only from a5s itself, so a page loads nothing from outside, which matters on premises. The Thai family, and the Vietnamese letters, load only where a page has some.

## What the tests hold it to

[`tests/test_design.py`](../tests/test_design.py) checks that:

- every colour that carries text reads against what it sits on at 4.5 to 1, as WCAG's AA asks, and focus rings and agents' marks at 3 to 1, in light and dark;
- the meanings name only primitives, so a brand is one change in one place;
- the pages load their type and their styles from a5s and from nowhere else;
- the copy of Ocean is Ocean's as its pinned commit has it, file by file, so nothing of it is changed here;
- neither `app.css` nor `studio.css` styles a selector Ocean's pieces or charts style, so Ocean stays the one source of how a piece looks.

A brand that reads less well fails the first test before anyone sees it. Ocean's own checks (`scripts/check.mjs` in sreent/ocean) hold the same and more, before a commit is taken.

## To change the brand

1. Change the primitives in Ocean's `css/tokens.css`, in sreent/ocean, or a fork of it for the organisation: the palette, and the fonts if the brand has its own, in `fonts/`. Its `node scripts/check.mjs` names any colour that reads less well.
2. Take that commit here with `sh deploy/ocean.sh <commit>`, and run `uv run pytest tests/test_design.py`.
3. Build the studio (`npm run build` in `studio/`), so it carries the change too.

## Components

The pieces pages are made of live in [`studio/src/design`](../studio/src/design), with their look in Ocean's `css/components.css`, so a page outside the studio can draw them too. The showcase, at `/studio/design`, shows each one as pages use it, in light or dark as the device is.

| Piece | What it's for |
| --- | --- |
| `Who`, `Avatar` | Who did something: people round, with their initials; agents as rounded squares in `--agent-tone` |
| `Badge` | What a tool does, or how something stands, in the colour that means it |
| `Traced` | A value an agent used, which opens to show its record, when it was read, by which run and for whom, and whether it still holds |
| `ApprovalCard` | What an agent asks someone to decide, at a phone's width at most: what it changes, why, and their yes or no, signed and kept in the ledger |
| `AgentFacts` | An agent's facts, as food carries a label, the same for every agent: what it may do, and how it does per run |
| `AutonomyLadder` | What an agent may do, the further steps its release allows, and how far it has come towards the next |
| `RunTimeline` | A run as time: each step in order, in the colour of what it did |
| `JourneyPath` | The way from a draft to an agent at work: each stage done, to do now, or later, with who does it, and the one thing to do next |
| `Confirm` | Asking first, for what can't be undone, in the browser's own dialog |
| `Hint` | A word on what something means, for whoever points at it or tabs to it |
| `Skeleton`, `Loading` | What's loading, in the shape it will have, which screen readers hear as loading |
| `Toasts` | What was just done, said once at the foot of the window as well as in the page's status line |
| `Palette` | Going anywhere someone may, by name, from any page, with Ctrl-K |

The popover a traced value opens and the hint are Radix's, which keyboards and screen readers reach as they do the mouse. The dialog is the browser's own: it keeps focus in it and the page behind it out of reach without injecting styles of its own, which the pages' policy wouldn't allow.

The browser tests open the showcase signed in, and check that:

- each piece is there;
- [axe](https://github.com/dequelabs/axe-core) finds nothing amiss in light or dark, as wide as a desktop and as a phone, by WCAG's rules and its best practices, as on every page people use (`tests/test_ui_pages.py`);
- each piece works from the keyboard: a traced value opens and closes with focus back on it, a hint shows to whoever tabs to it, the dialog starts on "Keep it" and closes with Escape even when a hint was open, a toast closes with Dismiss, and the palette chooses with the arrows and closes with Escape, focus back where it was;
- nothing on the page writes an error to the console, such as a style the pages' policy refused.

## Pages

Each page's title is its first-level heading, its sections' are the second level and theirs the third, the studio's pages and the server's alike; the sidebar names a5s. The pages are moving onto the pieces:

- **The chat** marks what an agent says with its mark, and what a5s says with its own, so who said what reads at a glance, in lines short enough to read, with today's times alone. A conversation with nothing in it yet starts with the agent and what it does, to someone it serves, and what to do: write to it.
- **Decisions** are approval cards, made for a phone: who asks and for whom, what the change does in the words code worked out when it was asked for, never the agent's own, what to know, and Approve or Reject. The cards make a column on a phone and sit side by side where there's room.
- **The catalogue** leads each agent's card with what it does, and the agent's map draws it in the agent colour.
- **An agent no instance runs** offers its owners and authors to put it to work, as the page's one thing to do: a first instance in the settings, for a few people, reading only or asking first. Those who approve versions of the settings go straight to the studio's settings, with a form for it, the agent chosen; others are told who can.
- **Each agent's page** leads its side with the agent's facts, from its release alone: its model and autonomy, its tools by what they do, and what it may spend. Where all its instances may do the same, its ladder follows, which stacks its steps wherever it's narrow.
- **A run's page** shows what it did as time: what started it and for whom, each call in the colour of what its tool does, or of a5s's refusing or holding it, with what a5s decided and why, and how the run ended.
- **The settings**, a page of the studio's since its step 3, change a version in forms, for what people change most: what each instance may do, the types of change it makes on its own, whom it serves, the model it runs on and who runs it, each type of change's limits, and the accuracy each part needs for an agent to act on its own. Each form offers only what can be: the types of change an agent's own tools make, and what its release lets it do, with why the rest can't be chosen. A form puts an agent to work: a new instance, in a part or none, starting by reading only or asking first, as low as its release starts, serving whoever adds it and run by them unless they choose otherwise. The whole text is a click away, for anything else. Either way, the review says in words what the version would change, and whose approval it needs, before anyone asks for it. A choice keeps its words beside it, and each type of change's limits wrap onto their own lines, so the forms work on a phone.

- **A draft** opens on the workbench, as Ocean's Workbench draws it, in [the designer](studio.md#the-designer), and, with nothing chosen, leads with where it stands on its way to work: shape and try it, publish it, have its release signed, which a5s then deploys, put it to work, and watch it. It says what each stage needs and who does it, and offers the one thing to do next, which takes you to it: what stops its release, the sandbox, or publishing it. Where there's a sandbox, trying it comes before publishing, though publishing without trying stays open. Once the release here holds the draft as it is, in a release other than the one it was drafted from, the path marks it signed and deployed, and its next step is the agent's page: to put it to work, or, once an instance runs it, to watch it.
- **Approving a version of the settings** is one card: who asked for it in the studio's settings, if someone did, and when it was proposed; where it stands; what it changes, with any change that widens what agents do marked so, as the studio's settings mark it; who has approved it and what's still missing; and the whole version as it would be, before the one thing to do, Approve, which a fresh sign-in signs for that version alone.
- **Grading** puts each sample on the card decisions are made on: the agent that asked or acted, what it did in the words code worked out, how it went, what code flagged, the record, and the grade. The grade chosen shows in its colour, green for right, amber for wrong and red for critical, and choosing it again takes it back. The grades go together, signed in afresh.

- **The administrators' page** names each role in words, such as "Owner of billing", with its id beside it for giving it to a group in the settings, marks a role nobody holds, and gives times as people read them; "What you may do" in the studio names roles the same way. The audit trail gives its times to the second, in UTC, as its searches are, and each long entry is a box keyboards reach as well as a mouse.
- A status line a page shows, such as why someone may not use it, starts with a capital, whatever the server's words.

On a phone, the sidebar shows each page's icon in a row, and screen readers still say each page's name.

The studio's pages for agents and runs are checked with axe too, in their own browser test.
