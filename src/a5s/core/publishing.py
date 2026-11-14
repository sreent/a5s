"""Publishing a draft (docs/studio.md, step 2): a pull request to the agents' repository on
GitHub, opened as the person publishing, through GitHub's own sign-in, with no token or secret
of a5s's.

The person signs in to GitHub there and then, by GitHub's device flow, which needs only the
client id of a5s's GitHub App, a public thing, and lets the App act as them on the agents'
repository, as far as both may. The channels app asks GitHub for the token it gives them,
holds it in memory for that one publish, and forgets it once the pull request is open, or the
sign-in is refused or lapses. It never writes it anywhere: not to the database, the ledger or
a log. The pull request carries the draft's folder, its tools pinned by a5s, on a branch of its
own, and says who must sign the release it makes, and why. CI and those people take it from
there, as for a change made in an editor. Published again, a draft adds a commit to its
branch, and its pull request shows it.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from a5s.config import Config

GRANT = "urn:ietf:params:oauth:grant-type:device_code"
KEEP = 60 * 60  # seconds a publish that ended is kept, in memory, to be asked after
MODE = "100644"  # each of an agent's files: text, never run
STATUSES = ("signing in", "opened", "refused", "lapsed")


class Refused(ValueError):
    """Why a draft wasn't published, in words: a5s's reason, or GitHub's."""


@dataclass
class Publish:
    """One publish, from the person's sign-in to GitHub to its pull request: never their token."""

    id: str
    person: str
    draft: str
    agent: str
    based_on: str  # the template, or the agent's release, it began as
    files: dict[str, str]  # the draft's folder, as it was when they asked
    title: str
    body: str
    message: str
    branch: str
    device_code: str
    user_code: str
    verify_at: str
    interval: float
    expires: float
    next_poll: float
    status: str = "signing in"
    pull: str | None = None  # its pull request, once open
    problem: str | None = None
    ended: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def shown(self) -> dict:
        return {"id": self.id, "status": self.status, "agent": self.agent,
                "user_code": self.user_code if self.status == "signing in" else None,
                "verify_at": self.verify_at if self.status == "signing in" else None,
                "interval": self.interval, "expires_in": max(0, round(self.expires - time.time())),
                "pull": self.pull, "problem": self.problem, "branch": self.branch}


def configured(cfg: Config) -> bool:
    return bool(cfg.github_client_id and cfg.github_repo)


def branch(agent: str, draft: str) -> str:
    """A draft's own branch: each publish of it adds a commit there."""
    return f"a5s/{agent}-{draft.replace('-', '')[:8]}"


def described(draft: dict, person: Any, signers: list[dict], new: bool) -> tuple[str, str, str]:
    """A publish's pull request, its title and body, and its commit's message: who drafted it,
    from what, and who must sign the release it makes, and why."""
    title = f"{'Add' if new else 'Change'} {draft['agent']}"
    by = f"Drafted in the a5s studio by {person.name} ({person.id}), from {draft['based_on']}."
    lines = [by, "", "## Who must sign its release", ""]
    lines += [f"- **{s['who']}**, because {s['why']}" for s in signers] or [
        "- Nobody more than for any release: it changes nothing a person must sign for."]
    checks = ("As `a5s release` works it out, from what it changes of the agents released where "
              "it was drafted. Nothing a5s checks there would stop its release: its definition "
              "loads as the core loads it, its tools are the scenario's, pinned as it has them, "
              "and its model is approved.")
    lines += ["", checks, "",
              "CI runs its checks, and its test cases on its model, as for any change to an agent."]
    return title, "\n".join(lines), f"{title}\n\n{by}"


class Publishing:
    """The publishes under way in this channels app, in its memory alone."""

    def __init__(self, cfg: Config, http: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=30)
        self.under_way: dict[str, Publish] = {}
        self.lock = threading.Lock()

    def _login(self, path: str, data: dict) -> dict:
        try:
            answer = self.http.post(f"{self.cfg.github_url.rstrip('/')}{path}", data=data,
                                    headers={"Accept": "application/json"})
        except httpx.HTTPError:
            raise Refused("GitHub didn't answer: try again in a moment") from None
        try:
            found = answer.json()
        except ValueError:
            found = {}
        if answer.status_code != 200 or not isinstance(found, dict):
            raise Refused(f"GitHub's sign-in said {answer.status_code}")
        return found

    def start(self, person: str, draft: dict, title: str, body: str, message: str) -> Publish:
        """Ask GitHub for a code the person enters there, as themselves, to let a5s's App
        publish the draft as them."""
        self._forget()
        asked = self._login("/login/device/code", {"client_id": self.cfg.github_client_id})
        if "device_code" not in asked:
            raise Refused(f"GitHub wouldn't sign anyone in for a5s: {_said(asked)}")
        now = time.time()
        interval = float(asked["interval"]) if asked.get("interval") is not None else 5.0
        publish = Publish(
            id=secrets.token_urlsafe(16), person=person, draft=draft["id"], agent=draft["agent"],
            based_on=draft["based_on"], files=dict(draft["files"]), title=title, body=body,
            message=message,
            branch=branch(draft["agent"], draft["id"]), device_code=asked["device_code"],
            user_code=asked["user_code"], verify_at=asked["verification_uri"], interval=interval,
            expires=now + float(asked.get("expires_in") or 900), next_poll=now + interval)
        with self.lock:
            self.under_way[publish.id] = publish
        return publish

    def poll(self, person: str, publish_id: str) -> tuple[Publish, bool]:
        """A publish as it stands, and whether this asking opened its pull request: once the
        person has let a5s in, GitHub hands over their token, a5s publishes the draft with
        it, and forgets it."""
        with self.lock:
            publish = self.under_way.get(publish_id)
        if publish is None or publish.person != person:
            raise KeyError(publish_id)
        with publish.lock:
            now = time.time()
            if publish.status != "signing in" or now < publish.next_poll:
                return publish, False
            if now > publish.expires:
                return self._end(publish, "lapsed", "the sign-in to GitHub lapsed: publish it again"), False
            try:
                got = self._login("/login/oauth/access_token", {
                    "client_id": self.cfg.github_client_id, "device_code": publish.device_code,
                    "grant_type": GRANT})
            except Refused:
                publish.next_poll = now + publish.interval  # GitHub may answer next time
                return publish, False
            error = got.get("error")
            if error == "authorization_pending":
                publish.next_poll = now + publish.interval
                return publish, False
            if error == "slow_down":  # as GitHub asks, five seconds more between asks
                publish.interval = float(got.get("interval") or publish.interval + 5)
                publish.next_poll = now + publish.interval
                return publish, False
            if error == "expired_token":
                return self._end(publish, "lapsed", "the sign-in to GitHub lapsed: publish it again"), False
            if error == "access_denied":
                return self._end(publish, "refused", "you didn't let a5s publish as you on GitHub"), False
            token = got.pop("access_token", None)  # for this publish alone, and kept nowhere
            if not isinstance(token, str) or not token:
                return self._end(publish, "refused", f"GitHub wouldn't sign you in: {_said(got)}"), False
            try:
                pull = self._open(token, publish)
            except Refused as e:
                return self._end(publish, "refused", str(e)), False
            except (KeyError, TypeError, ValueError, IndexError):  # never with the token
                return self._end(publish, "refused", "GitHub answered as a5s didn't expect: "
                                 "publish it again, or download its folder"), False
            publish.pull = pull
            self._end(publish, "opened", None)
            return publish, True

    def _end(self, publish: Publish, status: str, problem: str | None) -> Publish:
        publish.status, publish.problem, publish.ended = status, problem, time.time()
        publish.device_code = ""  # good for nothing more
        return publish

    def _forget(self) -> None:
        """Let go of publishes that ended an hour ago, or lapsed without anyone asking after."""
        now = time.time()
        with self.lock:
            for key, publish in list(self.under_way.items()):
                if (publish.ended and now - publish.ended > KEEP) or now - publish.expires > KEEP:
                    del self.under_way[key]

    def _open(self, token: str, publish: Publish) -> str:
        """The draft's folder as a commit on its own branch, from the agents' repository's
        branch, and the pull request from it, opened as whoever the token is: its address."""
        repo, base = self.cfg.github_repo, self.cfg.github_base
        api = f"{self.cfg.github_api_url.rstrip('/')}/repos/{repo}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}

        def call(method: str, path: str, ok: tuple[int, ...] = (200, 201), **kwargs: Any) -> httpx.Response:
            try:
                answer = self.http.request(method, f"{api}{path}", headers=headers, **kwargs)
            except httpx.HTTPError:
                raise Refused("GitHub didn't answer: publish it again in a moment") from None
            if answer.status_code not in ok:
                raise Refused(_refusal(answer, repo))
            return answer

        start = call("GET", f"/git/ref/heads/{quote(base)}").json()["object"]["sha"]
        mine = call("GET", f"/git/ref/heads/{quote(publish.branch)}", ok=(200, 404))
        parent = mine.json()["object"]["sha"] if mine.status_code == 200 else start
        tree = call("GET", f"/git/commits/{parent}").json()["tree"]["sha"]
        folder = [p for p in self.cfg.github_agents_path.strip("/").split("/") if p] + [publish.agent]
        there = self._files(call, tree, folder)
        prefix = "/".join(folder) + "/"
        entries = [{"path": prefix + path, "mode": MODE, "type": "blob", "content": text}
                   for path, text in sorted(publish.files.items())]
        entries += [{"path": prefix + path, "mode": MODE, "type": "blob", "sha": None}
                    for path in sorted(there - set(publish.files))]  # what the draft let go
        made = call("POST", "/git/trees", json={"base_tree": tree, "tree": entries}).json()["sha"]
        commit = call("POST", "/git/commits", json={"message": publish.message, "tree": made,
                                                     "parents": [parent]}).json()["sha"]
        if mine.status_code == 200:  # on from its last publish: never over anyone's commits
            call("PATCH", f"/git/refs/heads/{quote(publish.branch)}", json={"sha": commit, "force": False})
        else:
            call("POST", "/git/refs", json={"ref": f"refs/heads/{publish.branch}", "sha": commit})
        owner = repo.split("/", 1)[0]
        found = call("GET", "/pulls", params={"head": f"{owner}:{publish.branch}", "state": "open"}).json()
        if found:
            return found[0]["html_url"]
        opened = call("POST", "/pulls", json={"title": publish.title, "head": publish.branch,
                                              "base": base, "body": publish.body})
        return opened.json()["html_url"]

    @staticmethod
    def _files(call: Any, tree: str, folder: list[str]) -> set[str]:
        """The files of an agent's folder in a tree, by their paths in the folder, read down
        to it a folder at a time, so a large repository's whole tree is never asked for."""
        for name in folder:
            entries = call("GET", f"/git/trees/{tree}").json()["tree"]
            found = next((e for e in entries if e["path"] == name and e["type"] == "tree"), None)
            if found is None:
                return set()  # a new agent's
            tree = found["sha"]
        listing = call("GET", f"/git/trees/{tree}", params={"recursive": "1"}).json()
        if listing.get("truncated"):
            raise Refused("its folder on GitHub is too big to read whole")
        return {e["path"] for e in listing["tree"] if e["type"] == "blob"}


def _said(found: dict) -> str:
    return str(found.get("error_description") or found.get("error") or "it gave no reason")


def _refusal(answer: httpx.Response, repo: str) -> str:
    """What GitHub refused, in words, as it said it: never with the token."""
    try:
        said = str(answer.json().get("message") or "")
    except ValueError:
        said = ""
    if answer.status_code in (401, 403, 404):
        return (f"GitHub won't let a5s publish to {repo} as you ({answer.status_code}"
                f"{': ' + said if said else ''}): you need to be able to push to it, and a5s's "
                "GitHub App to be installed on it")
    return f"GitHub said {answer.status_code}{': ' + said if said else ''}"
