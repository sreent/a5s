"""Acting with someone's own permissions (core/delegation.py, docs/connectors.md#acting-as-the-person):
a person connects their account in a system on their own page, the system asks them, as itself,
whether a5s may act for them, and the core keeps their tokens, sealed; an MCP server declared as
acting as the person then gets their token, for a run acting for them alone, so the system's own
rules decide what they see there. The system here is a real OAuth server of the test's own, with
PKCE, and the MCP server the SDK's, which reads whose token each call carries."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from a5s import build, config, db
from a5s.config import Config
from a5s.connectors import mcp
from a5s.connectors.rest import ConnectorError
from a5s.contract import ToolCall
from a5s.core import delegation, departures, erasure, export, retention
from conftest import (
    FAKE_MODELS,
    PROVIDER_KEY,
    SERVICE_TOKEN,
    FakeModel,
    Stack,
    accessible,
    build_root,
    free_port,
    running,
    serve,
)

server_sdk = pytest.importorskip("mcp.server.mcpserver")
mcp_types = pytest.importorskip("mcp.types")

SECRET = "desk-client-secret"
# Each ticket, and whose it is in the desk's own rules: its requester sees it, and nobody else
TICKETS = {"Q-1001": "ana", "Q-1004": "ana", "Q-1002": "ben"}
SEARCH = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}


def challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


class Desk:
    """An IT service desk people connect their accounts in: it asks whoever is signed in to it
    whether a5s may act for them, sends them back with a code, and gives a5s their tokens for
    it, with PKCE and a5s's client secret; and its MCP server answers each as themselves."""

    def __init__(self) -> None:
        self.person = "ana"  # who is signed in to the desk, in their browser
        self.codes: dict[str, tuple[str, str, str]] = {}  # each code: whose, its challenge, its way back
        self.access: dict[str, str] = {}  # each token, whose it is
        self.refresh: dict[str, str] = {}
        self.issued = 0
        self.lifetime = 3600
        self.asked: list[dict[str, str]] = []  # each time someone was sent to it
        self.grants: list[str] = []  # each grant a5s asked for
        self.called: list[str] = []  # the token each MCP request came with

    def oauth(self) -> FastAPI:
        app = FastAPI()

        @app.get("/authorize")
        def authorize(request: Request) -> RedirectResponse:
            asked = dict(request.query_params)
            self.asked.append(asked)
            code = secrets.token_urlsafe(12)
            self.codes[code] = (self.person, asked["code_challenge"], asked["redirect_uri"])
            back = urlencode({"code": code, "state": asked["state"]})
            return RedirectResponse(f"{asked['redirect_uri']}?{back}", status_code=302)

        @app.post("/token")
        async def token(request: Request) -> Any:
            form = {k: str(v) for k, v in (await request.form()).items()}
            if form.get("client_id") != "a5s-desk" or form.get("client_secret") != SECRET:
                return JSONResponse({"error": "invalid_client"}, 401)
            self.grants.append(form["grant_type"])
            if form["grant_type"] == "authorization_code":
                found = self.codes.pop(form.get("code", ""), None)
                if found is None or found[2] != form.get("redirect_uri") \
                        or found[1] != challenge(form.get("code_verifier", "")):
                    return JSONResponse({"error": "invalid_grant"}, 400)
                person = found[0]
            elif form["grant_type"] == "refresh_token":
                person = self.refresh.pop(form.get("refresh_token", ""), None)
                if person is None:
                    return JSONResponse({"error": "invalid_grant"}, 400)
            else:
                return JSONResponse({"error": "unsupported_grant_type"}, 400)
            self.issued += 1
            access, refresh = f"at-{person}-{self.issued}", f"rt-{person}-{self.issued}"
            self.access[access], self.refresh[refresh] = person, person
            return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer",
                    "expires_in": self.lifetime, "scope": "tickets.read"}

        @app.get("/me")
        def me(request: Request) -> Any:
            whose = self.access.get(request.headers.get("authorization", "")
                                    .removeprefix("Bearer "))
            return {"user": {"name": whose}} if whose else JSONResponse({"error": "who?"}, 401)

        return app

    def server(self) -> Any:
        server = server_sdk.MCPServer("desk")

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True))
        def search(query: str, ctx: server_sdk.Context) -> dict:
            """Search the tickets the caller may see, by the desk's own rules."""
            given = (ctx.headers or {}).get("authorization", "")
            whose = self.access.get(given.removeprefix("Bearer "))
            return {"items": [{"key": k, "requester": p} for k, p in TICKETS.items()
                              if whose and p == whose and query.lower() in "open tickets"]}

        app = server.streamable_http_app()

        async def recording(scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] == "http":
                self.called.append(dict(scope["headers"]).get(b"authorization", b"").decode())
            await app(scope, receive, send)

        return recording


def declared(url: str, **server: Any) -> dict:
    return {"servers": {"desk": {"url": url, "as_person": "desk", **server}},
            "tools": {"search_tickets": {
                "server": "desk", "calls": "search", "description": "Search your desk tickets",
                "arguments": SEARCH, "returns": ["items", "key", "requester"],
                "record_field": "key"}}}


def systems(url: str) -> str:
    return json.dumps([{"name": "desk", "title": "Service desk", "authorize": f"{url}/authorize",
                        "token": f"{url}/token", "client_id": "a5s-desk",
                        "whoami": f"{url}/me", "whose": "user.name",
                        "scopes": ["tickets.read", "offline_access"]}])


@pytest.fixture
def desk() -> Iterator[tuple[Desk, str, str]]:
    found = Desk()
    with serve(found.oauth(), free_port()) as oauth, serve(found.server(), free_port()) as server:
        yield found, oauth, f"{server}/mcp"


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
          desk: tuple[Desk, str, str]) -> Iterator[Stack]:
    """The sample, with the assistant searching the desk's tickets as whoever it acts for."""
    _, oauth, url = desk
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    monkeypatch.setenv("A5S_DELEGATION", systems(oauth))
    monkeypatch.setenv("A5S_DELEGATION_DESK_SECRET", SECRET)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    (root / "scenarios" / "sample" / mcp.FILE).write_text(yaml.safe_dump(declared(url)))
    spec = root / "agents" / "assistant" / "agent.yaml"
    spec.write_text(spec.read_text().replace(
        "records: [search_records, get_record, get_messages]",
        "records: [search_records, get_record, get_messages, search_tickets]"))
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def as_person(approving: str, provider: Any, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})


def swept(stack: Stack) -> dict:
    """The core takes the codes people came back with, as the scheduler has it do."""
    answer = httpx.post(f"{stack.cfg.gateway_url}/delegation/sweep", timeout=30,
                        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"})
    answer.raise_for_status()
    return answer.json()


def connect(stack: Stack, approving: str, provider: Any, desk: Desk, person: str) -> None:
    """Someone connects their desk account: sent to the desk, which asks them, and back."""
    desk.person = person
    go = as_person(approving, provider, person, "POST", "/studio/api/you/connections/desk/start")
    assert go.status_code == 200, go.text
    there = httpx.get(go.json()["go"], follow_redirects=False, timeout=30)
    back = parse_qs(urlsplit(there.headers["location"]).query)
    came = as_person(approving, provider, person, "POST", "/studio/api/you/connections/back",
                     {"state": back["state"][0], "code": back["code"][0]})
    assert came.status_code == 200 and came.json()["connecting"], came.text
    assert swept(stack)["connected"] == 1


def tickets(stack: Stack, person: str) -> Any:
    """What the agent hears back, searching the desk's open tickets for someone."""
    stack.model.reply(None, ("search_tickets", {"query": "open"}))
    stack.model.reply("Here they are.")
    stack.say("Which of my desk tickets are open?", person=person)
    return json.loads(stack.model.requests[-1]["body"]["messages"][-1]["content"])


def test_tokens_are_sealed_for_one_person_in_one_system():
    sealed = delegation.seal(("k1",), "ana", "desk", {"access": "at-ana-1", "refresh": "rt"})
    assert b"at-ana-1" not in sealed and b"ana" not in sealed
    assert delegation.unseal(("k1",), "ana", "desk", sealed)["access"] == "at-ana-1"
    assert delegation.unseal(("k2", "k1"), "ana", "desk", sealed)["access"] == "at-ana-1"  # moving keys
    for person, system, keys in (("ben", "desk", ("k1",)), ("ana", "forge", ("k1",)),
                                 ("ana", "desk", ("k2",))):
        with pytest.raises(delegation.NotConnected, match="connect it again"):
            delegation.unseal(keys, person, system, sealed)  # bound to them both, and the key
    with pytest.raises(delegation.Refused, match="no seal key"):
        delegation.seal((), "ana", "desk", {})


def test_someone_connects_their_account_and_agents_act_there_as_them(stack, approving, provider,
                                                                     desk):
    found, oauth, _ = desk
    listed = as_person(approving, provider, "ana", "GET", "/studio/api/you/connections").json()
    [never] = listed["connections"]
    assert {k: v for k, v in never.items() if v is not None} == {
        "system": "desk", "title": "Service desk", "connected": False, "connecting": False,
        "scopes": ["tickets.read", "offline_access"], "reads": []}
    start = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/desk/start")
    go = urlsplit(start.json()["go"])
    asked = {k: v[0] for k, v in parse_qs(go.query).items()}
    assert f"{go.scheme}://{go.netloc}{go.path}" == f"{oauth}/authorize"
    assert asked["client_id"] == "a5s-desk" and asked["scope"] == "tickets.read offline_access"
    assert asked["redirect_uri"] == f"{approving}/studio/connections"
    assert asked["code_challenge_method"] == "S256" and "code_verifier" not in asked
    there = httpx.get(start.json()["go"], follow_redirects=False, timeout=30)
    back = {k: v[0] for k, v in parse_qs(urlsplit(there.headers["location"]).query).items()}
    # Someone else's way back isn't theirs to use, nor a made-up one
    for person, state in (("ben", back["state"]), ("ana", "made-up")):
        stolen = as_person(approving, provider, person, "POST", "/studio/api/you/connections/back",
                           {"state": state, "code": back["code"]})
        assert stolen.status_code == 400 and "connect it again" in stolen.json()["detail"]
    came = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/back", back)
    assert came.json() == {"system": "desk", "title": "Service desk", "connecting": True}
    [now] = as_person(approving, provider, "ana", "GET", "/studio/api/you/connections").json()["connections"]
    assert now["connecting"] and not now["connected"]
    assert swept(stack) == {"connected": 1, "failed": 0}
    assert found.grants == ["authorization_code"]  # with the verifier only the core had
    [now] = as_person(approving, provider, "ana", "GET", "/studio/api/you/connections").json()["connections"]
    assert now["connected"] and now["scopes"] == ["tickets.read"] and now["used_at"] is None
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select * from delegations").fetchall()
        assert conn.execute("select count(*) as n from delegation_starts").fetchone()["n"] == 0
    assert row["person"] == "ana" and b"at-ana" not in bytes(row["sealed"])
    # The agent searches the desk as Ana, with her token, and the desk shows her hers alone
    answer = tickets(stack, "ana")
    assert sorted(t["key"] for t in answer["items"]) == ["Q-1001", "Q-1004"]
    assert found.called and set(found.called) == {"Bearer at-ana-1"}
    entries = stack.ledger()
    connected = [e for e in entries if e["kind"] == "admin" and e["action"] == "connect"]
    assert connected and connected[0]["acts_for"] == ["ana"] and connected[0]["args"] == {"system": "desk"}
    assert "at-ana-1" not in json.dumps(entries) and "rt-ana-1" not in json.dumps(entries)
    [now] = as_person(approving, provider, "ana", "GET", "/studio/api/you/connections").json()["connections"]
    assert now["used_at"]


def test_someone_who_hasnt_connected_hears_how_to(stack, approving, provider, desk):
    found, _, _ = desk
    connect(stack, approving, provider, found, "ana")
    before = len(found.called)
    stack.model.reply(None, ("search_tickets", {"query": "open"}))
    stack.model.reply("You haven't connected it.")
    stack.say("Which of my desk tickets are open?", person="ben")
    said = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert "ben hasn't connected their Service desk account" in said
    assert "on their own page in the studio" in said
    assert len(found.called) == before  # nothing went to the desk for Ben, not even Ana's token


def test_a_token_about_to_lapse_is_renewed_and_one_the_system_refuses_is_forgotten(
        stack, approving, provider, desk):
    found, _, _ = desk
    connect(stack, approving, provider, found, "ana")
    with db.transaction(stack.admin) as conn:  # its hour is nearly up
        conn.execute("update delegations set expires_at = now() + interval '30 seconds'")
    assert tickets(stack, "ana")["items"]
    assert found.grants == ["authorization_code", "refresh_token"]
    assert found.called[-1] == "Bearer at-ana-2"
    # The desk stops taking it, as when someone ends a5s's access there
    found.refresh.clear()
    with db.transaction(stack.admin) as conn:
        conn.execute("update delegations set expires_at = now()")
    stack.model.reply(None, ("search_tickets", {"query": "open"}))
    stack.model.reply("Connect it again.")
    stack.say("And now?", person="ana")
    said = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert "connects their Service desk account again" in said
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from delegations").fetchone()["n"] == 0
    [ended] = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "disconnect"]
    assert ended["acts_for"] == ["ana"] and "no longer takes it" in ended["args"]["why"]


def test_someone_disconnects_and_a5s_forgets_their_tokens(stack, approving, provider, desk):
    found, _, _ = desk
    connect(stack, approving, provider, found, "ana")
    gone = as_person(approving, provider, "ana", "DELETE", "/studio/api/you/connections/desk")
    assert gone.json() == {"forgotten": True}
    again = as_person(approving, provider, "ana", "DELETE", "/studio/api/you/connections/desk")
    assert again.json() == {"forgotten": False}
    [ended] = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "disconnect"]
    assert ended["args"] == {"system": "desk", "why": "they disconnected it"}
    stack.model.reply(None, ("search_tickets", {"query": "open"}))
    stack.model.reply("You disconnected it.")
    stack.say("Which are open?", person="ana")
    assert "ana hasn't connected" in stack.model.requests[-1]["body"]["messages"][-1]["content"]


def test_a_no_at_the_system_connects_nothing_and_a_code_the_system_wont_take_fails(
        stack, approving, provider):
    start = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/desk/start")
    state = parse_qs(urlsplit(start.json()["go"]).query)["state"][0]
    no = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/back",
                   {"state": state, "error": "access_denied"})
    assert no.json()["connecting"] is False
    assert swept(stack) == {"connected": 0, "failed": 0}
    start = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/desk/start")
    state = parse_qs(urlsplit(start.json()["go"]).query)["state"][0]
    as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/back",
              {"state": state, "code": "not-the-desks"})
    assert swept(stack) == {"connected": 0, "failed": 1}
    [failed] = [e for e in stack.ledger() if e["kind"] == "admin" and e["action"] == "connect"]
    assert failed["outcome"]["status"] == "error" and "invalid_grant" in failed["outcome"]["error"]
    unknown = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/forge/start")
    assert unknown.status_code == 404


def test_a_tool_acting_as_the_person_does_so_for_one_person_alone(desk):
    found, _, url = desk
    asked: list[tuple[str, str]] = []

    def supply(person: str, system: str) -> str:
        asked.append((person, system))
        if person != "ana":
            raise delegation.NotConnected(f"{person} hasn't connected their account")
        found.access["at-ana-x"] = "ana"
        return "at-ana-x"

    tool = mcp.tools(mcp.Declaration.model_validate(declared(url)), delegated=supply)["search_tickets"]

    def call(*people: str) -> Any:
        return tool.run(ToolCall(args={"query": "open"}, instance="assistant-finance", run="r-1",
                                 acts_for=people))

    for people, said in (((), "acts for no one"), (("ana", "ben"), "acts for 2 people")):
        with pytest.raises(ConnectorError, match=said):
            call(*people)
    assert asked == []  # nobody's token was asked for
    assert sorted(t["key"] for t in call("ana")["items"]) == ["Q-1001", "Q-1004"]
    with pytest.raises(ConnectorError, match="ben hasn't connected"):
        call("ben")
    assert {a for a in asked} == {("ana", "desk"), ("ben", "desk")}
    # Where nothing supplies people's tokens, such as the channels app, it acts as nobody
    with pytest.raises(ConnectorError, match="only the core, with its seal keys, acts as anyone"):
        mcp.tools(mcp.Declaration.model_validate(declared(url)))["search_tickets"].run(
            ToolCall(args={"query": "open"}, instance="assistant-finance", run="r-1",
                     acts_for=("ana",)))
    # In the sandbox, its stand-in answers, with no token
    stand_in = mcp.tools(mcp.Declaration.model_validate(declared("https://desk.example/mcp",
                                                                 sandbox=url)),
                         sandboxed=True)["search_tickets"]
    before = len(found.called)
    assert stand_in.run(ToolCall(args={"query": "open"}, instance="i", run="r",
                                 acts_for=())) == {"items": []}
    assert set(found.called[before:]) == {""}


def test_a_declaration_says_whose_access_a_server_calls_with():
    def problem(**server: Any) -> str:
        with pytest.raises(ValueError) as e:
            mcp.Declaration.model_validate(declared("https://desk.example/mcp", **server))
        return str(e.value)

    assert "as_person or token_env" in problem(token_env="A5S_MCP_DESK_TOKEN")
    assert "in lowercase" in problem(as_person="Service Desk")
    theirs = mcp.tools(mcp.Declaration.model_validate(declared("https://desk.example/mcp")))
    ours = mcp.tools(mcp.Declaration.model_validate({
        **declared("https://desk.example/mcp"), "servers": {"desk": {"url": "https://desk.example/mcp"}}}))
    # whose access it calls with is in what its approvers pinned
    assert theirs["search_tickets"].schema_hash != ours["search_tickets"].schema_hash


def test_the_core_starts_only_with_what_acting_as_people_needs(tmp_path, monkeypatch):
    folder = tmp_path / "scenario"
    folder.mkdir()
    (folder / mcp.FILE).write_text(yaml.safe_dump(declared("https://desk.example/mcp")))
    core = Config(database_url="postgresql://unused", gateway_url="http://unused",
                  service_token="t", root=tmp_path, scenario_folder=folder, seal_keys=("k",))
    monkeypatch.delenv("A5S_DELEGATION", raising=False)
    with pytest.raises(RuntimeError, match="acts as the person in desk, which A5S_DELEGATION "
                                           "doesn't name"):
        build.delegating(core)
    monkeypatch.setenv("A5S_DELEGATION", systems("https://desk.example"))
    with pytest.raises(RuntimeError, match="set a5s's client secret there"):
        build.delegating(core)
    channels = replace(core, seal_keys=())  # which never holds the secret, nor acts as anyone
    found, delegated = build.delegating(channels)
    assert found and found.system("desk") and found.system("desk").secret is None and delegated is None
    monkeypatch.setenv("A5S_DELEGATION_DESK_SECRET", "s")
    found, delegated = build.delegating(core)
    assert found.system("desk").secret == "s" and delegated is not None
    assert config.known("A5S_DELEGATION_DESK_SECRET")
    bad = {"A5S_DELEGATION": json.dumps([{"name": "Desk"}, {"name": "forge", "authorize": ""}])}
    problems, _ = config.check(bad)
    assert any("each is named in lowercase" in p for p in problems)
    assert any("gives forge no token" in p for p in problems)
    plain = {"A5S_DELEGATION": json.dumps([{"name": "desk", "authorize": "http://desk.example/a",
                                            "token": "https://desk.example/t", "client_id": "c"}])}
    with pytest.raises(config.ConfigError, match="isn't an HTTPS address"):
        delegation.Delegation.from_env(env=plain)


def test_what_a5s_keeps_of_a_connection_is_in_their_export_and_goes_with_them(
        stack, approving, provider, desk):
    found, _, _ = desk
    connect(stack, approving, provider, found, "ana")
    connect(stack, approving, provider, found, "ben")
    with db.transaction(stack.admin) as conn:
        kept = export.gather(conn, "ana")
    [theirs] = kept["connections"]
    assert theirs["system"] == "desk" and theirs["scopes"] == ["tickets.read"]
    assert "sealed" not in theirs and "at-ana" not in json.dumps(kept, default=str)
    with db.transaction(stack.admin) as conn:
        gone, _ = erasure.erase(conn, "ana", datetime.now(UTC), here=True)
        assert gone["delegations"] == 1 and erasure.WORDS["delegations"]
        left = [r["person"] for r in conn.execute("select person from delegations")]
    assert left == ["ben"]
    assert "delegations" in departures.LET_GO  # and it goes when they leave
    with db.transaction(stack.admin) as conn:  # unused for 90 days, it goes
        conn.execute("update delegations set used_at = now() - interval '91 days'")
        assert retention.sweep(conn, datetime.now(UTC), stack.gateway.scenario.name)["connections"] == 1


def test_someone_connects_from_their_own_page_in_the_studio(stack, approving, provider, desk,
                                                          browser):
    found, _, _ = desk
    provider.person = found.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/you")
    page.wait_for_selector("#connections button.primary", timeout=30000)
    assert "Service desk" in page.inner_text("#connections")
    assert "Not connected" in page.inner_text("#connections")
    accessible(page)
    page.click("#connections button.primary")  # to the desk, which asks, and back, signed in
    page.wait_for_url(re.compile(r".*/studio/connections$"), timeout=30000)
    page.wait_for_selector("h1 >> text=Connecting your Service desk account", timeout=30000)
    for _ in range(100):  # the scheduler's sweep, here the test's, once the code is in
        with db.transaction(stack.admin) as conn:
            if conn.execute("select 1 from delegation_starts where code is not null").fetchone():
                break
        page.wait_for_timeout(100)
    assert swept(stack)["connected"] == 1
    page.wait_for_url(re.compile(r".*/studio/you$"), timeout=30000)
    page.wait_for_selector("#connections >> text=Connected", timeout=30000)
    assert "tickets.read" in page.inner_text("#connections")
    accessible(page)
    page.click("#connections button.danger")  # asks first
    page.click("dialog[open] button.primary")
    page.wait_for_selector("#connections >> text=Not connected", timeout=30000)
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from delegations").fetchone()["n"] == 0


def test_a_code_recorded_for_someone_else_connects_nothing(stack, approving, provider, desk):
    """Round 14 (B-H2): the part people reach records where they come back to, and whatever it
    records, the core keeps a token only for the account the desk says it is, as the directory
    knows its person: Ana's way back, recorded as Ben's, connects nobody."""
    found, _, _ = desk
    start = as_person(approving, provider, "ana", "POST", "/studio/api/you/connections/desk/start")
    assert start.status_code == 200, start.text
    found.person = "ana"
    there = httpx.get(start.json()["go"], follow_redirects=False, timeout=30)
    back = {k: v[0] for k, v in parse_qs(urlsplit(there.headers["location"]).query).items()}
    with db.transaction(db.as_role(stack.admin, "channels")) as conn:
        row = conn.execute("select * from delegation_starts where state = %s",
                           (back["state"],)).fetchone()
        conn.execute("delete from delegation_starts where state = %s", (back["state"],))
        conn.execute("insert into delegation_starts (state, person, system, verifier, code, "
                     "coded_at) values ('elsewhere', 'ben', 'desk', %s, %s, now())",
                     (row["verifier"], back["code"]))
    assert swept(stack) == {"connected": 0, "failed": 1}
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select * from delegations").fetchall() == []
    [refused] = [e for e in stack.ledger() if e.get("action") == "connect"]
    assert refused["acts_for"] == ["ben"] and "isn't theirs" in refused["outcome"]["error"]



def test_a_run_nobody_asked_for_never_acts_as_anyone(stack, approving, provider, desk):
    """Round 14 (A-M1): an event names someone, but they never asked for its run, and whoever
    holds the system's secret, or poses as them to it, can start one: so it never acts as them
    in another system, with the account they connected, nor reads what they may read there."""
    from dataclasses import replace

    from a5s.core import inbox
    from a5s.core.events import EventsConfig, Source
    from a5s.definitions import Event
    from conftest import free_port, serve
    from test_events import OPENED, SECRET, SOURCE, TASK, send

    found, _, _ = desk
    connect(stack, approving, provider, found, "ana")
    found.called.clear()
    assistant = stack.gateway.definitions["assistant"]
    stack.gateway.definitions["assistant"] = assistant.model_copy(update={"events": [
        Event(type="question-opened", source=SOURCE, task=TASK)]})
    stack.gateway.events = EventsConfig((Source(SOURCE, SECRET),))
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))
    with serve(inbox.create_app(endpoint), free_port()) as url:
        assert send(f"{url}/channels/events/{SOURCE}", {
            **OPENED, "records": ["Q-1001"], "person": "ana"}).status_code == 202
    stack.model.reply(None, ("search_tickets", {"query": "open"}))
    stack.model.reply("Done.")
    assert stack.scheduler().work_due() == 1
    assert found.called == []  # never as Ana
    [denied] = [e for e in stack.ledger() if e.get("action") == "search_tickets"]
    assert denied["decision"] == "deny" and denied["reasons"] == ["acts-as-nobody-unasked"]
    tickets(stack, "ana")  # her own message does
    assert set(found.called) == {"Bearer at-ana-1"}
