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

## Next

Components on Radix, for menus, dialogs and tooltips, which handle keyboard and screen readers, with a5s's own pieces for agentic work: the approval card, agent facts, a value traced to its record, the ladder of autonomy, and the run as a timeline. They'll live on a showcase page in the studio, tested for accessibility in every mode.
