"""Walk-throughs: a scenario's people, each in a browser of their own, taking an agent from an
idea to work through a5s's own pages and its command line alone, as phase 5 asks
(docs/phase-5.md).

A walk-through is a list of steps, each in the words a person reads and in what they do there.
A step a5s can't take fails, naming the step, as a gap to close. With A5S_GUIDE naming a
folder, each step's picture goes into it, under the walk-through's name, beside a guide.md that
tells the steps in order: the scenario's guide, which never drifts from what a5s does, since a
walk-through makes it.

What a walk-through does outside a5s, it does as the people there would, and says so: the forge
merges a pull request its reviewers approved, and a5s's scheduler, which runs on its own when
deployed, is run when its turn comes.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Where the guides go, from where the tests were started, whatever folder a walk-through is
# in when it writes, such as one it signs a release in
GUIDE = str(Path(os.environ["A5S_GUIDE"]).resolve()) if os.environ.get("A5S_GUIDE") else None


class Gap(AssertionError):
    """A step a walk-through couldn't take through a5s."""


def _slug(words: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", words.lower()).strip("-")[:48].rstrip("-")


@dataclass
class Walk:
    name: str  # its guide's folder, such as sample
    title: str
    browser: Any
    provider: Any  # the identity provider people sign in through, as whoever it's told
    steps: list[tuple[str, str | None]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_(self, person: str, url: str, width: int = 1440, height: int = 900) -> Any:
        """A browser of `person`'s own at `url`, signing in as them when the page asks."""
        self.signs_in(person)
        page = self.browser.new_page(viewport={"width": width, "height": height})
        page.on("console", lambda m: self.errors.append(f"{person}: {m.text}")
                if "Content Security Policy" in m.text else None)
        page.goto(url)
        return page

    def signs_in(self, person: str) -> None:
        """Whoever signs in next, such as afresh for a decision, is `person`."""
        self.provider.person = person

    @contextmanager
    def step(self, words: str, page: Any = None) -> Iterator[None]:
        """A step, in the words its guide tells it in, and the picture of where it ended."""
        number = len(self.steps) + 1
        try:
            yield
        except Gap:
            raise
        except Exception as exc:
            raise Gap(f"step {number}, {words!r}, couldn't be taken through a5s: {exc}") from exc
        picture = None
        if GUIDE and page is not None:
            folder = Path(GUIDE) / self.name
            folder.mkdir(parents=True, exist_ok=True)
            picture = f"{number:02d}-{_slug(words)}.png"
            page.screenshot(path=str(folder / picture))
        self.steps.append((words, picture))

    def guide(self, about: str) -> None:
        """The guide, in A5S_GUIDE, if it names a folder."""
        assert self.errors == [], self.errors
        if not GUIDE:
            return
        lines = [f"# {self.title}", "", about, ""]
        for number, (words, picture) in enumerate(self.steps, 1):
            lines += [f"{number}. {words}", ""]
            if picture:
                lines += [f"   ![{words}]({picture})", ""]
        (Path(GUIDE) / self.name).mkdir(parents=True, exist_ok=True)
        (Path(GUIDE) / self.name / "guide.md").write_text("\n".join(lines))
