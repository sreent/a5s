"""A stand-in for GitHub, as a5s publishes drafts to it (core/publishing.py): its device flow,
by which someone lets a5s's App act as them, and as much of its API as puts an agent's folder on
a branch and opens a pull request from it, each call as whoever's token it carries."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

CLIENT = "a5s-app"  # a5s's App's client id, a public thing


class FakeGitHub:
    def __init__(self, files: dict[str, str], repo: str = "acme/agents", base: str = "main") -> None:
        self.repo, self.base = repo, base
        self.url = ""  # once it's served
        self.trees: dict[str, dict[str, str]] = {}  # each commit's whole tree: path -> text
        self.subtrees: dict[str, tuple[str, str]] = {}  # a folder's tree: its root's, and where
        self.commits: dict[str, dict] = {}
        self.refs: dict[str, str] = {}
        self.pulls: list[dict] = []
        self.codes: dict[str, dict] = {}  # each device code: its user code, and how it stands
        self.tokens: dict[str, str] = {}  # each token GitHub gave, and whose it is
        self.cannot_push: set[str] = set()  # those who may read the repository, not push to it
        self.calls: list[tuple[str, str, str | None]] = []  # method, path, as whom
        self.refs[f"heads/{base}"] = self._commit(self._tree(files), [], "The agents as released",
                                                  "release-bot")

    # What it holds

    @staticmethod
    def _sha(*parts: Any) -> str:
        return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    def _tree(self, files: dict[str, str]) -> str:
        sha = self._sha("tree", files)
        self.trees[sha] = dict(files)
        return sha

    def _commit(self, tree: str, parents: list[str], message: str, author: str) -> str:
        sha = self._sha("commit", tree, parents, message, secrets.token_hex(4))
        self.commits[sha] = {"tree": tree, "parents": parents, "message": message, "author": author}
        return sha

    def files(self, branch: str) -> dict[str, str]:
        return self.trees[self.commits[self.refs[f"heads/{branch}"]]["tree"]]

    def head(self, branch: str) -> dict:
        return self.commits[self.refs[f"heads/{branch}"]]

    # Someone at GitHub's sign-in page, with the code a5s showed them

    def _code(self, user_code: str) -> dict:
        return next(c for c in self.codes.values() if c["user_code"] == user_code)

    def grant(self, user_code: str, login: str) -> None:
        self._code(user_code).update(state="granted", login=login)

    def deny(self, user_code: str) -> None:
        self._code(user_code)["state"] = "denied"

    def lapse(self, user_code: str) -> None:
        self._code(user_code)["state"] = "expired"

    def app(self) -> FastAPI:  # one route each, as GitHub has them
        app = FastAPI()
        repo = f"/repos/{self.repo}"

        async def form(request: Request) -> dict[str, str]:
            """What a5s posted, as GitHub's sign-in takes it: a form, answered in JSON."""
            assert request.headers.get("accept") == "application/json"
            return {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}

        @app.post("/login/device/code")
        async def device(request: Request) -> dict:
            client_id = (await form(request)).get("client_id")
            if client_id != CLIENT:
                return {"error": "unauthorized_client"}
            code, user = secrets.token_hex(10), f"{secrets.token_hex(2)}-{secrets.token_hex(2)}".upper()
            self.codes[code] = {"user_code": user, "state": "pending"}
            return {"device_code": code, "user_code": user, "expires_in": 900, "interval": 0,
                    "verification_uri": "https://github.test/login/device"}

        @app.post("/login/oauth/access_token")
        async def token(request: Request) -> dict:
            asked = await form(request)
            code = self.codes.get(asked.get("device_code", ""))
            if asked.get("client_id") != CLIENT or code is None:
                return {"error": "incorrect_device_code"}
            assert asked.get("grant_type") == "urn:ietf:params:oauth:grant-type:device_code"
            if code["state"] == "pending":
                return {"error": "authorization_pending"}
            if code["state"] == "denied":
                return {"error": "access_denied"}
            if code["state"] != "granted":
                return {"error": "expired_token"}
            code["state"] = "used"  # a device code gives one token
            given = f"ghu_{secrets.token_hex(12)}"
            self.tokens[given] = code["login"]
            return {"access_token": given, "token_type": "bearer", "scope": ""}

        def who(authorization: str | None, request: Request) -> str:
            login = self.tokens.get((authorization or "").removeprefix("Bearer "))
            self.calls.append((request.method, request.url.path, login))
            if login is None:
                raise HTTPException(401, "Bad credentials")
            return login

        def refused(status: int, message: str) -> JSONResponse:
            return JSONResponse(status_code=status, content={"message": message})

        @app.get(repo + "/git/ref/heads/{branch:path}")
        def ref(branch: str, request: Request, authorization: str | None = Header(default=None)) -> Any:
            who(authorization, request)
            sha = self.refs.get(f"heads/{branch}")
            return {"object": {"sha": sha, "type": "commit"}} if sha else refused(404, "Not Found")

        @app.get(repo + "/git/commits/{sha}")
        def commit(sha: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
            who(authorization, request)
            return {"sha": sha, "tree": {"sha": self.commits[sha]["tree"]}}

        @app.get(repo + "/git/trees/{sha}")
        def tree(sha: str, request: Request, recursive: str | None = None,
                 authorization: str | None = Header(default=None)) -> dict:
            who(authorization, request)
            root, at = (sha, "") if sha in self.trees else self.subtrees[sha]
            under = {path[len(at):]: text for path, text in self.trees[root].items() if path.startswith(at)}
            if recursive:
                return {"sha": sha, "truncated": False,
                        "tree": [{"path": p, "type": "blob", "mode": "100644"} for p in sorted(under)]}
            entries, folders = [], sorted({p.split("/", 1)[0] for p in under if "/" in p})
            for name in folders:
                sub = self._sha("subtree", root, at + name + "/")
                self.subtrees[sub] = (root, at + name + "/")
                entries.append({"path": name, "type": "tree", "mode": "040000", "sha": sub})
            entries += [{"path": p, "type": "blob", "mode": "100644"} for p in sorted(under) if "/" not in p]
            return {"sha": sha, "truncated": False, "tree": entries}

        @app.post(repo + "/git/trees", status_code=201)
        async def new_tree(request: Request, authorization: str | None = Header(default=None)) -> dict:
            who(authorization, request)
            body = await request.json()
            files = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                assert entry["mode"] == "100644" and entry["type"] == "blob"
                if entry.get("sha", "") is None:
                    files.pop(entry["path"], None)
                else:
                    files[entry["path"]] = entry["content"]
            return {"sha": self._tree(files)}

        @app.post(repo + "/git/commits", status_code=201)
        async def new_commit(request: Request, authorization: str | None = Header(default=None)) -> dict:
            login = who(authorization, request)
            body = await request.json()
            return {"sha": self._commit(body["tree"], body["parents"], body["message"], login)}

        @app.post(repo + "/git/refs", status_code=201)
        async def new_ref(request: Request, authorization: str | None = Header(default=None)) -> Any:
            login = who(authorization, request)
            if login in self.cannot_push:
                return refused(403, "Resource not accessible by integration")
            body = await request.json()
            name = body["ref"].removeprefix("refs/")
            if name in self.refs:
                return refused(422, "Reference already exists")
            self.refs[name] = body["sha"]
            return {"ref": body["ref"], "object": {"sha": body["sha"]}}

        @app.patch(repo + "/git/refs/heads/{branch:path}")
        async def move_ref(branch: str, request: Request,
                           authorization: str | None = Header(default=None)) -> Any:
            login = who(authorization, request)
            if login in self.cannot_push:
                return refused(403, "Resource not accessible by integration")
            body = await request.json()
            now = self.refs[f"heads/{branch}"]
            if not body.get("force") and now not in self.commits[body["sha"]]["parents"]:
                return refused(422, "Update is not a fast forward")
            self.refs[f"heads/{branch}"] = body["sha"]
            return {"object": {"sha": body["sha"]}}

        @app.get(repo + "/pulls")
        def pulls(request: Request, head: str = "", state: str = "open",
                  authorization: str | None = Header(default=None)) -> list:
            who(authorization, request)
            return [p for p in self.pulls if p["state"] == state
                    and f"{self.repo.split('/')[0]}:{p['head']}" == head]

        @app.post(repo + "/pulls", status_code=201)
        async def new_pull(request: Request, authorization: str | None = Header(default=None)) -> Any:
            login = who(authorization, request)
            body = await request.json()
            if any(p["head"] == body["head"] and p["state"] == "open" for p in self.pulls):
                return refused(422, "A pull request already exists")
            number = len(self.pulls) + 1
            self.pulls.append({**body, "number": number, "state": "open", "user": login,
                               "html_url": f"https://github.test/{self.repo}/pull/{number}"})
            return self.pulls[-1]

        return app
