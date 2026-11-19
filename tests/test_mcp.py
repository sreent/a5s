"""Tools from MCP servers, governed as a5s's own (connectors/mcp.py): a scenario declares, in
its folder's mcp.yaml, each tool of a server's its agents may use, in a5s's words, with its
flags and the fields a5s passes on, and nothing else of the server's is offered. Before each
call, a5s checks the server still offers the tool as declared, its arguments by their shape and
its annotations never more than declared, and what comes back goes through a5s's own checks.
The server here is a real one, the MCP SDK's own, over Streamable HTTP."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from a5s.connectors import mcp
from a5s.connectors.rest import ConnectorError
from a5s.contract import ToolCall
from conftest import FAKE_MODELS, FakeModel, Stack, build_root, free_port, running, serve

server_sdk = pytest.importorskip("mcp.server.mcpserver")
mcp_types = pytest.importorskip("mcp.types")

TICKETS = {
    "Q-1002": {"key": "Q-1002", "title": "Duplicate payment refund", "status": "open",
               "requester_email": "ben@northwind.test"},
    "Q-1003": {"key": "Q-1003", "title": "Order arrived damaged", "status": "open",
               "requester_email": "chen@northwind.test"},
}
SEARCH = {"type": "object", "required": ["query"],
          "properties": {"query": {"type": "string", "description": "words a ticket holds"}}}


def tickets_server(**changed: Any) -> Any:
    """A records system's MCP server: searching tickets, reading one, and what it says of each."""
    server = server_sdk.MCPServer("tickets")
    hints = mcp_types.ToolAnnotations

    @server.tool(annotations=changed.get("search_hints", hints(readOnlyHint=True)))
    def search(query: str) -> dict:
        """Search the tickets."""
        found = [t for t in TICKETS.values() if query.lower() in json.dumps(t).lower()]
        return {"items": changed.get("items", found), "total": len(found)}

    @server.tool(annotations=hints(readOnlyHint=True, openWorldHint=True))
    def browse(url: str) -> str:
        """Fetch a page from the web."""
        return f"the page at {url}"

    @server.tool()
    def wipe(key: str) -> str:
        """Not declared: a5s never offers it."""
        return f"wiped {key}"

    return server


@pytest.fixture
def tickets() -> Iterator[str]:
    with serve(tickets_server().streamable_http_app(), free_port()) as url:
        yield f"{url}/mcp"


def declaration(url: str, **tool: Any) -> mcp.Declaration:
    return mcp.Declaration.model_validate({
        "servers": {"tickets": {"url": url}},
        "tools": {"search_tickets": {
            "server": "tickets", "calls": "search", "description": "Search the questions' tickets",
            "arguments": SEARCH, "returns": ["items", "key", "title", "status"],
            "record_field": "key", **tool}}})


def call(tool: Any, **args: Any) -> Any:
    return tool.run(ToolCall(args=args, instance="assistant-finance", run="r-1", acts_for=("ana",)))


def test_a_declared_tool_says_a5s_s_words_and_returns_only_what_s_declared(tickets):
    [tool] = mcp.tools(declaration(tickets)).values()
    assert (tool.description, tool.schema) == ("Search the questions' tickets", SEARCH)
    assert tool.risk == {"reads": True, "writes": False, "destructive": False,
                         "sends_outside": False}
    found = call(tool, query="refund")
    assert found == {"items": [{"key": "Q-1002", "title": "Duplicate payment refund",
                                "status": "open"}]}  # no email, nor the total: not declared


def test_a_tool_the_server_changed_isnt_called(tickets):
    takes_more = {**SEARCH, "required": ["query", "limit"],
                  "properties": {**SEARCH["properties"], "limit": {"type": "integer"}}}
    [tool] = mcp.tools(declaration(tickets, arguments=takes_more)).values()
    with pytest.raises(ConnectorError, match="takes other arguments than declared"):
        call(tool, query="refund", limit=1)
    [renamed] = mcp.tools(declaration(tickets, calls="find")).values()
    with pytest.raises(ConnectorError, match="no longer offers find"):
        call(renamed, query="refund")


def test_a_server_saying_more_than_declared_is_refused():
    changes = mcp_types.ToolAnnotations(readOnlyHint=False, destructiveHint=True)
    with serve(tickets_server(search_hints=changes).streamable_http_app(), free_port()) as url:
        [tool] = mcp.tools(declaration(f"{url}/mcp")).values()
        with pytest.raises(ConnectorError, match="says it changes things"):
            call(tool, query="refund")
        [changing] = mcp.tools(declaration(f"{url}/mcp", writes=True)).values()
        with pytest.raises(ConnectorError, match="may destroy what it changes"):
            call(changing, query="refund")
        [destructive] = mcp.tools(declaration(f"{url}/mcp", writes=True,
                                              destructive=True)).values()
        assert call(destructive, query="refund")["items"]  # declared as all it says


def test_a_tool_that_reaches_outside_is_declared_so(tickets):
    browsing = {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}}
    [tool] = mcp.tools(declaration(tickets, calls="browse", arguments=browsing,
                                   returns=["result"], record_field=None)).values()
    with pytest.raises(ConnectorError, match="reaches outside the organisation"):
        call(tool, url="https://example.com")
    [sending] = mcp.tools(declaration(tickets, calls="browse", arguments=browsing,
                                      returns=["result"], record_field=None,
                                      sends_outside=True)).values()
    assert call(sending, url="https://example.com") == {"result": "the page at https://example.com"}


def test_what_names_no_record_isnt_passed_on():
    unkeyed = [{"title": "Duplicate payment refund", "status": "open"}]
    with serve(tickets_server(items=unkeyed).streamable_http_app(), free_port()) as url:
        [tool] = mcp.tools(declaration(f"{url}/mcp")).values()
        with pytest.raises(ConnectorError, match="names no record by key"):
            call(tool, query="refund")


def test_a_declaration_says_everything_it_relies_on():
    def problem(**tool: Any) -> str:
        with pytest.raises(ValueError) as e:
            declaration("http://127.0.0.1:1/mcp", **tool)
        return str(e.value)

    assert "isn't among the servers" in problem(server="other")
    assert "aren't among the fields it returns" in problem(record_field="id")
    assert "names it, by record_arg" in problem(action="close-ticket")
    assert "returns" in problem(returns=[])
    with pytest.raises(ValueError, match="over HTTPS alone"):
        mcp.Declaration.model_validate({"servers": {"t": {"url": "http://tickets.example/mcp"}},
                                        "tools": {}})
    with pytest.raises(ValueError, match="A5S_MCP_<SERVER>_TOKEN"):
        mcp.Declaration.model_validate({"servers": {"t": {"url": "https://t.example/mcp",
                                                          "token_env": "TICKETS_KEY"}},
                                        "tools": {}})
    twice = {"server": "tickets", "calls": "search", "description": "d", "arguments": SEARCH,
             "returns": ["items"]}
    with pytest.raises(ValueError, match="declared once"):
        mcp.Declaration.model_validate({"servers": {"tickets": {"url": "https://t.example/mcp"}},
                                        "tools": {"one": twice, "two": twice}})


def test_its_hash_covers_the_server_s_name_for_it_and_what_s_passed_on():
    base = mcp.tools(declaration("http://127.0.0.1:1/mcp"))["search_tickets"].schema_hash
    for change in ({"calls": "find"}, {"returns": ["items", "key", "title"]}):
        assert mcp.tools(declaration("http://127.0.0.1:1/mcp", **change)
                         )["search_tickets"].schema_hash != base


def test_shape_leaves_out_only_words():
    theirs = {"type": "object", "title": "searchArguments", "required": ["b", "a"],
              "properties": {"a": {"type": "string", "title": "A"},
                             "b": {"type": ["null", "integer"], "default": 3}}}
    ours = {"type": "object", "required": ["a", "b"],
            "properties": {"a": {"type": "string", "description": "what a5s says"},
                           "b": {"type": ["integer", "null"], "default": 3}}}
    assert mcp.shape(theirs) == mcp.shape(ours)
    assert mcp.shape(ours) != mcp.shape({**ours, "properties": {
        **ours["properties"], "b": {"type": ["integer", "null"], "default": 4}}})  # a default


class Recorded:
    """A server, as httpx's mock transport, that answers as told, and keeps what it was sent."""

    def __init__(self, *answers: Any):
        self.answers = list(answers)
        self.sent: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        message = json.loads(request.content)
        answer = self.answers.pop(0) if self.answers else None
        if callable(answer):
            return answer(request, message)
        if answer is not None:
            return answer
        if message.get("method") == "initialize":
            return httpx.Response(200, headers={"Mcp-Session-Id": f"s{len(self.sent)}"}, json={
                "jsonrpc": "2.0", "id": message["id"],
                "result": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "serverInfo": {"name": "fake", "version": "1"}}})
        if "id" not in message:
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"],
                                         "result": {"tools": []}})


def session(fake: Recorded, **kwargs: Any) -> mcp.Session:
    return mcp.Session("tickets", "https://tickets.example/mcp", kwargs.pop("token_env", None),
                       http=httpx.Client(transport=httpx.MockTransport(fake)), **kwargs)


def test_it_sends_its_token_and_follows_no_redirect(monkeypatch):
    monkeypatch.setenv("A5S_MCP_TICKETS_TOKEN", "t0ken")
    fake = Recorded()
    session(fake, token_env="A5S_MCP_TICKETS_TOKEN").tools()
    assert {r.headers["Authorization"] for r in fake.sent} == {"Bearer t0ken"}
    assert fake.sent[-1].headers["MCP-Protocol-Version"] == "2025-06-18"
    assert fake.sent[-1].headers["Mcp-Session-Id"] == "s1"
    moved = Recorded(None, None, httpx.Response(302, headers={"Location": "https://evil.example"}))
    with pytest.raises(ConnectorError, match="redirect, which a5s doesn't follow"):
        session(moved).tools()
    monkeypatch.delenv("A5S_MCP_TICKETS_TOKEN")
    with pytest.raises(ConnectorError, match="A5S_MCP_TICKETS_TOKEN isn't set"):
        session(Recorded(), token_env="A5S_MCP_TICKETS_TOKEN").tools()


def test_an_answer_too_big_is_refused_and_an_ended_session_begun_again():
    big = Recorded(None, None, lambda request, message: httpx.Response(200, json={
        "jsonrpc": "2.0", "id": message["id"], "result": {"tools": [], "x": "y" * mcp.MAX_BYTES}}))
    with pytest.raises(ConnectorError, match="more than 1,000,000 bytes"):
        session(big).tools()
    ended = Recorded(None, None, httpx.Response(404))  # the server forgot a5s's session
    s = session(ended)
    assert s.tools() == {}
    assert [json.loads(r.content).get("method") for r in ended.sent] == [
        "initialize", "notifications/initialized", "tools/list",
        "initialize", "notifications/initialized", "tools/list"]


def test_in_the_sandbox_the_stand_in_answers_with_no_token(tickets, monkeypatch):
    monkeypatch.setenv("A5S_MCP_TICKETS_TOKEN", "t0ken")
    declared = mcp.Declaration.model_validate({
        "servers": {"tickets": {"url": "https://tickets.example/mcp", "sandbox": tickets,
                                "token_env": "A5S_MCP_TICKETS_TOKEN"},
                    "crm": {"url": "https://crm.example/mcp"}},
        "tools": {"search_tickets": declaration(tickets).tools["search_tickets"].model_dump(),
                  "search_crm": {**declaration(tickets).tools["search_tickets"].model_dump(),
                                 "server": "crm"}}})
    made = mcp.tools(declared, sandboxed=True)
    assert call(made["search_tickets"], query="damaged")["items"][0]["key"] == "Q-1003"
    with pytest.raises(ConnectorError, match="no stand-in in the sandbox"):
        call(made["search_crm"], query="damaged")


def test_a_scenario_gains_only_what_it_declares_and_never_a_name_it_has(tickets, tmp_path):
    class Scenario:
        def tools(self) -> dict:
            return {"search_records": object()}

    folder = tmp_path / "scenario"
    folder.mkdir()
    assert mcp.served(Scenario(), folder) is not None  # no mcp.yaml: as it was
    spec = {"servers": {"tickets": {"url": tickets}},
            "tools": {"search_tickets": declaration(tickets).tools["search_tickets"].model_dump()}}
    (folder / mcp.FILE).write_text(yaml.safe_dump(spec), encoding="utf-8")
    found = mcp.served(Scenario(), folder).tools()
    assert sorted(found) == ["search_records", "search_tickets"]  # never `wipe`, nor `browse`
    spec["tools"] = {"search_records": spec["tools"]["search_tickets"]}
    (folder / mcp.FILE).write_text(yaml.safe_dump(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="which the scenario or a5s has already"):
        mcp.served(Scenario(), folder)
    (folder / mcp.FILE).write_text(yaml.safe_dump(spec).replace("servers:", "servers:\nservers:"), encoding="utf-8")
    with pytest.raises(ValueError):
        mcp.served(Scenario(), folder)  # each key once, as agent.yaml


@pytest.fixture
def ticketed(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
             tickets: str) -> Iterator[Stack]:
    """The sample, with its tickets searched through an MCP server, which the assistant uses."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    (root / "scenarios" / "sample" / mcp.FILE).write_text(yaml.safe_dump({
        "servers": {"tickets": {"url": tickets}},
        "tools": {"search_tickets": declaration(tickets).tools["search_tickets"].model_dump()}}), encoding="utf-8")
    spec = root / "agents" / "assistant" / "agent.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace(
        "records: [search_records, get_record, get_messages]",
        "records: [search_records, get_record, get_messages, search_tickets]"))
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def test_an_mcp_servers_answer_goes_through_a5s_s_need_to_know(ticketed):
    ticketed.model.reply(None, ("search_tickets", {"query": "open"}))
    ticketed.model.reply("One ticket is open for you: Q-1002.")
    ticketed.say("Which tickets are open?", person="ana")  # Ana sees billing's, not orders'
    answer = json.loads(ticketed.model.requests[-1]["body"]["messages"][-1]["content"])
    assert [t["key"] for t in answer["items"]] == ["Q-1002"]  # Q-1003 is orders': withheld
    assert "requester_email" not in json.dumps(answer)
    allowed, done = [e for e in ticketed.ledger() if e["kind"] == "tool"
                     and e["action"] == "search_tickets"]  # the policy's decision, then what came
    assert allowed["decision"] == "allow" and done["outcome"]["withheld"] == 1
    assert done["outcome"]["status"] == "ok" and done["of"] == allowed["seq"]


def test_a_call_sends_its_key_and_nothing_else_of_a5s_s():
    def answer(request: httpx.Request, message: dict) -> httpx.Response:
        result = ({"tools": [{"name": "search", "inputSchema": SEARCH}]}
                  if message["method"] == "tools/list"
                  else {"content": [{"type": "text", "text": '{"items": []}'}]})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})

    fake = Recorded(None, None, answer, answer)
    tool = mcp.tools(declaration("https://tickets.example/mcp", idempotent=True),
                     http=httpx.Client(transport=httpx.MockTransport(fake)))["search_tickets"]
    assert tool.run(ToolCall(args={"query": "refund"}, instance="assistant-finance", run="r-1",
                             acts_for=("ana",), key="k-1")) == {"items": []}
    sent = fake.sent[-1].content.decode()
    assert json.loads(sent)["params"] == {"name": "search", "arguments": {"query": "refund"},
                                          "_meta": {"a5s/key": "k-1"}}
    assert "ana" not in sent and "r-1" not in sent and "assistant-finance" not in sent
