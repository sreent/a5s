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

In CI, its agents run on the stand-in model, scripted for each walk-through, so it gives the same
answers every time. At night, with A5S_TEST_WALK_MODEL naming an approved model, such as
deepseek-v4-pro, they run on it instead, on the scenarios' synthetic data: what the script would
have it say goes nowhere, a step waits for whatever the agent answers, and the walk-through checks
what came of it, a change held or made, rather than its words.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import yaml

from a5s import cli, db
from a5s.core import publishing
from a5s.core.releases import Releases, running
from conftest import FAKE_MODELS, ROOT, FakeModel
from fake_github import CLIENT as GITHUB

# Where the guides go, from where the tests were started, whatever folder a walk-through is
# in when it writes, such as one it signs a release in
GUIDE = str(Path(os.environ["A5S_GUIDE"]).resolve()) if os.environ.get("A5S_GUIDE") else None


# The approved model a walk-through's agents run on at night: the stand-in's script if none
LIVE = os.environ.get("A5S_TEST_WALK_MODEL")


class Gap(AssertionError):
    """A step a walk-through couldn't take through a5s."""


class Unscripted:
    """A real model, as a walk-through walks on at night: nothing scripts what it says, and
    the walk-through sees none of what it's sent."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.answering = None

    def reply(self, *_: Any) -> None:
        """What the stand-in would have said: a real model says its own."""


@dataclass
class On:
    """What a walk-through's agents run on: the stand-in's script, or, at night, a real model."""

    model: Any  # its script, a FakeModel, or Unscripted
    alias: str  # the approved model's alias, as the deployment's models.yaml names it
    models: str  # that models.yaml
    http: httpx.Client  # how the gateway reaches it
    transport: httpx.BaseTransport | None  # and the sandbox: the script's, or the internet's

    @property
    def live(self) -> bool:
        return isinstance(self.model, Unscripted)


def walking_on(answering: Any = None) -> On:
    """The stand-in, scripted, answering what `answering` answers by what it is, such as a
    judge's; or, with A5S_TEST_WALK_MODEL set, that approved model, through the internet."""
    if LIVE:
        return On(Unscripted(), LIVE, (ROOT / "config" / "models.yaml").read_text(),
                  httpx.Client(timeout=180), None)
    model = FakeModel(answering=answering)
    transport = httpx.MockTransport(model.handler)
    return On(model, "fake", FAKE_MODELS, httpx.Client(transport=transport), transport)


def decided_in_trail(page: Any, by: str) -> None:
    """On the audit trail, found for an instance: its held change's decision, by `by`, as the
    ledger has it, and that a5s then made it, the auditor asking only for what `by` decided."""
    page.fill("#by", by)
    page.click("#search")
    page.wait_for_selector("#entries li:has-text('proposal decide')", timeout=30000)
    shown = page.locator("#entries li").all_inner_texts()
    assert any("proposal decide, allow" in e and f"By {by}" in e for e in shown), shown
    assert any("proposal made, record" in e and f"By {by}" in e for e in shown), shown
    page.fill("#by", "")


def watched(walk: Walk, stack: Any, url: str, instance: str, person: str, name: str, tool: str,
            record: str) -> None:
    """Someone who owns a part an instance works in watches its dashboard and opens the run that
    just used `tool` on `record`, whose records they may see."""
    page = walk.as_(person, f"{url}/studio/instances/{instance}")
    with walk.step(f"{name} watches {instance} on its own page, as the owner of one of its parts: "
                   "its runs and how they ended, and what it may do.", page):
        page.wait_for_selector(".tile-label:text-is('Runs')", timeout=30000)
        assert int(page.locator(".tile", has=page.locator(".tile-label:text-is('Runs')")
                              ).locator(".tile-value").inner_text()) >= 1
        assert "done" in page.inner_text("section.card:has(h2:text-is('How runs ended'))")
        assert "Asks" in page.inner_text("#reach")
    used = next(e["run"] for e in reversed(stack.ledger())
                if e["kind"] == "tool" and e["action"] == tool and e["instance"] == instance)
    with walk.step(f"They open that run: {tool} on {record}, from its message to its outcome. "
                   "The studio shows what it did, never what anyone said.", page):
        page.wait_for_selector(f".runs-table a[href='/studio/runs/{used}']", timeout=30000).click()
        page.wait_for_selector(f".timeline >> text={tool}", timeout=30000)
        assert record in page.inner_text(".chips")
        assert "A message started it" in page.inner_text(".timeline")
        assert "Ended: done" in page.inner_text(".timeline")
        assert page.locator("#entries").count() == 0  # nobody's words, nor their hashes
        page.locator(".timeline").scroll_into_view_if_needed()


def tried(walk: Walk, stack: Any, page: Any, on: On, owner: str, person: str, question: str,
          tool: str, args: dict, answer: str, record: str, case: str) -> None:
    """An author tries a draft's read in the sandbox, keeps it as a case and runs that case before
    publishing. The model's script is ignored on a real model, whose run must use the same tool."""
    who = stack.gateway.scenario.person(person).name
    stack.model.reply(None, (tool, args))
    stack.model.reply(answer)
    with walk.step(f"{owner} tries the draft in the sandbox as {who}, on its made-up records, and "
                   f"keeps the exchange as a test case: {tool} answers about {record}, allowed by "
                   "a5s's checks.", page):
        page.click("#try-it")
        page.wait_for_selector(f"#try-as option[value={person}]", state="attached", timeout=30000)
        page.select_option("#try-as", person)
        page.select_option("#try-model", on.alias)
        page.fill("#try-text", question)
        page.click(".try-say button[type=submit]")
        page.wait_for_selector(".try-answer .try-reply", timeout=180000)
        assert on.live or record in page.inner_text(".try-answer .try-reply")
        assert "allow" in page.inner_text(".try-answer .run-calls")
        page.fill("#case-name", case)
        page.click("#keep-case")
        page.wait_for_selector("#case-kept", timeout=30000)
        page.wait_for_selector("#kept >> text=kept", timeout=30000)
    stack.model.reply(None, (tool, args))
    stack.model.reply(answer)
    with walk.step(f"They run the case there: it uses {tool} again, and passes.", page):
        page.click("#run-cases")
        page.wait_for_selector("#cases-summary >> text=1 of 1 passed", timeout=300000)
    draft = page.evaluate("location.pathname").rsplit("/", 1)[-1]
    with db.transaction(stack.admin) as conn:
        files = conn.execute("select files from agent_drafts where id = %s::uuid", (draft,)).fetchone()["files"]
    [saved] = yaml.safe_load(files["tests/tried.yaml"])
    assert (saved["name"], saved["as"]) == (case, person), saved
    [step] = saved["steps"]
    assert step["say"] == question and tool in step["uses"], saved
    page.click(".wb-bar .modes button:has-text('Design')")
    page.wait_for_selector("#problem-count >> text=No problems", timeout=30000)


def waiting(stack: Any) -> int:
    """How many changes wait for a decision."""
    with db.transaction(stack.admin) as conn:
        return conn.execute("select count(*) as n from proposals where status = 'waiting'").fetchone()["n"]


def confirms(page: Any, stack: Any, agent: str, before: int = 0) -> None:
    """At night, a real model may ask the person to confirm a change before it asks for it, though
    a5s holds the change for its decider anyway: if no more waits than `before`, they say yes, once."""
    if LIVE and waiting(stack) <= before:
        says(page, agent, "Yes, please ask for it.", "")


def says(page: Any, agent: str, text: str, words: str) -> None:
    """Someone says `text` to `agent` in the web chat, and it answers: with `words`, as the script
    has it, or, on a real model, with whatever it says."""
    page.wait_for_selector(f"#agent option[value='{agent}']", state="attached", timeout=30000)
    page.select_option("#agent", agent)
    page.fill("#text", text)
    page.keyboard.press("Enter")
    if LIVE:  # an answer after what they said, however much of the conversation had loaded
        page.wait_for_function(ANSWERED, arg=text, timeout=180000)
    else:
        page.wait_for_selector(f"li.agent >> text={words}", timeout=30000)


# Whether the agent has answered since someone last said `text` in the chat
ANSWERED = """text => {
  const said = [...document.querySelectorAll('#conversation li.you')]
    .filter(li => li.textContent.includes(text));
  for (let next = said.at(-1)?.nextElementSibling; next; next = next.nextElementSibling) {
    if (next.classList.contains('agent')) return true;
  }
  return false;
}"""


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
    pages: list[Any] = field(default_factory=list)  # those it opened, the newest last

    def as_(self, person: str, url: str, width: int = 1440, height: int = 900) -> Any:
        """A browser of `person`'s own at `url`, signing in as them when the page asks. The
        oldest of its pages close as it opens more, as people close tabs, so a long walk-through
        holds no more than a few."""
        self.signs_in(person)
        for done in self.pages[:-3]:
            if not done.is_closed():
                done.close()
        page = self.browser.new_page(viewport={"width": width, "height": height})
        self.pages = [*self.pages[-3:], page]
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


# What every walk-through does outside a5s's pages, as the people and systems there do it

def deployed(stack: Any, forge: Any) -> None:
    """The stack as an organisation runs it: not in development, so its release must be
    approved, and publishing to the team's repository on the forge."""
    stack.gateway.cfg = replace(stack.gateway.cfg, development=False)
    stack.gateway.releases = Releases(running(stack.cfg.root, stack.cfg.scenario_dir, stack.cfg.agents_dir))
    stack.cfg = replace(stack.cfg, github_client_id=GITHUB, github_repo=forge.repo,
                        github_url=forge.url, github_api_url=forge.url)


def released(stack: Any, folder: Path, monkeypatch: Any, capsys: Any) -> str:
    """What `a5s release status` says of the release here, before anyone has signed it: who it
    needs, and the release it follows, as its approvers read it, from the deployment's own
    configuration."""
    for name, value in (("A5S_ROOT", stack.cfg.root), ("A5S_DATABASE_URL", stack.admin),
                        ("A5S_SCENARIO", stack.cfg.scenario), ("A5S_SCENARIO_DIR", stack.cfg.scenario_dir),
                        ("A5S_AGENTS_DIR", stack.cfg.agents_dir)):
        monkeypatch.setenv(name, str(value))
    folder.mkdir(exist_ok=True)
    monkeypatch.chdir(folder)
    cli.main(["release", "show"])
    Path("release.yaml").write_bytes(capsys.readouterr().out.encode())
    try:
        cli.main(["release", "status"])
    except SystemExit as stopped:  # not approved here yet, as it says
        return capsys.readouterr().out + str(stopped.code)
    return capsys.readouterr().out


def signed_and_recorded(said: str, capsys: Any, *people: str) -> str:
    """The release, signed by `people` with `a5s release sign`, each as on their own machine, as
    following the release `said` names, and recorded with `a5s release approve`: what
    `a5s release status` says of it then."""
    follows = re.search(r"--follows (\w+)", said)
    for person in people:
        cli.main(["release", "sign", "--as", person, *(["--follows", follows[1]] if follows else [])])
    cli.main(["release", "approve"])
    capsys.readouterr()
    cli.main(["release", "status"])
    return capsys.readouterr().out


def merged(stack: Any, files: dict[str, str], agent: str) -> None:
    """The agent's folder as its pull request has it, merged where the deployment keeps its
    agents, as its reviewers' approval and the forge's merge would."""
    where = publishing.folder(stack.cfg, agent) + "/"
    for path, text in files.items():
        if path.startswith(where):
            target = stack.cfg.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)


def owned(scenario_dir: Path, person: str, agent: str) -> None:
    """`person` owns the new agent, as the scenario's directory says: in a deployment, its
    identity provider, whose administrator names them."""
    path = scenario_dir / "data.yaml"
    data = yaml.safe_load(path.read_text())
    [them] = [p for p in data["people"] if p["id"] == person]
    them["roles"] = [*them.get("roles", []), f"agent-owner:{agent}"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))


@contextmanager
def answering(stack: Any) -> Iterator[None]:
    """a5s's scheduler, answering messages as they arrive, as it does deployed."""
    stop = threading.Event()
    listener = threading.Thread(target=stack.scheduler().listen, args=(stop,),
                                kwargs={"sweep_every": 3600}, daemon=True)
    listener.start()
    try:
        yield
    finally:
        stop.set()
        listener.join(10)
