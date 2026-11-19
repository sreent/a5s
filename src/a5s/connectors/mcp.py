"""Tools from MCP servers, governed as a5s's own (docs/connectors.md#mcp-servers).

A scenario names, in its folder's mcp.yaml, each tool of an MCP server's that its agents may
use, in a5s's own words: what it's called, what it does and the arguments it takes, the flags
any of the scenario's tools has, what it reads and changes, whether it sends outside, the
record it names, the field that names each record it returns, a type of action for a change,
outside content and the form a5s's extractor fills from it, and the fields of what it returns
that a5s passes on. Nothing else of a server's is offered: deny by default. The release covers
the file, so a change to it needs the release's signatures, and agents pin each tool they use
by a hash that covers the server's name for it and what's passed on, as for any other tool.

Before each call, a5s checks the server still offers the tool as declared: the arguments it
takes, by their shape, and what it says of itself, its annotations, never more than declared.
A server that changed either is refused until a release declares it again. What a tool
returns comes back as JSON, its structured content if it has some, with only the fields
declared, and, for a tool that names its records, each record in a list named, so a5s's
need-to-know checks every one: what a5s can't check, it doesn't pass on.

It speaks MCP's Streamable HTTP, through the initialize handshake (2025-03-26 to 2025-11-25),
over HTTPS unless the server is on this machine, with no redirects, an answer of 1 MB at
most, and a bearer token from the environment, A5S_MCP_<SERVER>_TOKEN. A server that acts as
the person (`as_person`, docs/connectors.md#acting-as-the-person) takes theirs instead, from the
account they connected in its system (core/delegation.py), for a run acting for them alone, with
a session of its own for each person. In the studio's sandbox, a server's declared stand-in
answers instead, and no token goes there.
"""

from __future__ import annotations

import ipaddress
import itertools
import json
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from a5s import definitions, reach
from a5s.connectors.rest import ConnectorError
from a5s.contract import Tool, ToolCall, Undo
from a5s.core.ledger import canonical

FILE = "mcp.yaml"
PROTOCOL = "2025-11-25"  # what a5s asks for; a server may answer with another it speaks
SPOKEN = ("2025-03-26", "2025-06-18", "2025-11-25")
MAX_BYTES = 1_000_000  # of one answer, as it comes, never compressed
DEADLINE = 120.0  # seconds a call may take in all, however slowly the server answers
LISTED_FOR = 300.0  # seconds a server's list of its tools serves before a5s asks again
PAGES = 10  # of a server's list of tools, at most
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
CALLS = re.compile(r"[A-Za-z0-9_.\-/]{1,128}")
TOKEN = re.compile(r"A5S_MCP_[A-Z0-9_]+_TOKEN")
SYSTEM = re.compile(r"[a-z][a-z0-9-]{0,31}")  # as A5S_DELEGATION names systems
PEOPLE = 256  # sessions kept for a server that acts as the person, the latest used
Delegated = Callable[[str, str], str]  # (person, system) to their access token there
# What only describes an argument, and never constrains it: a server may change its words
WORDS = frozenset({"title", "description", "examples", "$comment", "$schema", "deprecated"})
SCHEMA_MAPS = frozenset({"properties", "patternProperties", "$defs", "definitions",
                         "dependentSchemas"})  # each value a schema
SCHEMA_IN = frozenset({"items", "additionalProperties", "not", "if", "then", "else", "contains",
                       "propertyNames", "unevaluatedItems", "unevaluatedProperties",
                       "additionalItems", "allOf", "anyOf", "oneOf", "prefixItems"})
UNORDERED = frozenset({"required", "type"})  # lists whose order says nothing


def shape(schema: Any) -> Any:
    """A JSON Schema as it constrains what's given: without the words that only describe it,
    which a5s says in its own, and with what's unordered in order."""
    if isinstance(schema, list):
        return [shape(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    found: dict[str, Any] = {}
    for key, value in schema.items():
        if key in WORDS:
            continue
        if key in SCHEMA_MAPS and isinstance(value, dict):
            found[key] = {name: shape(s) for name, s in value.items()}
        elif key in SCHEMA_IN:
            found[key] = shape(value)
        elif key in UNORDERED and isinstance(value, list):
            found[key] = sorted(value, key=str)
        else:
            found[key] = value
    return found


def _origin(url: str) -> str:
    """A server's address, as a5s may call it: HTTPS, or HTTP on this machine alone."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password
            or parsed.fragment):
        raise ValueError(f"{url} isn't an MCP server's address: HTTP(S), with no user or fragment")
    if parsed.scheme == "http" and not _local(host):
        raise ValueError(f"{url} is a remote MCP server, which a5s calls over HTTPS alone")
    return url


def _local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# The declaration

class Server(BaseModel):
    """An MCP server a scenario's tools come from."""

    model_config = ConfigDict(extra="forbid")
    url: str  # its Streamable HTTP endpoint
    token_env: str | None = None  # the variable that holds its bearer token, if it takes one
    # or the system, as A5S_DELEGATION names it, whose account each person connects, so a5s
    # calls it as them, with their own permissions, never its own
    as_person: str | None = None
    sandbox: str | None = None  # the stand-in the studio's sandbox calls instead, with no token

    @field_validator("url", "sandbox")
    @classmethod
    def _address(cls, url: str | None) -> str | None:
        return None if url is None else _origin(url)

    @field_validator("token_env")
    @classmethod
    def _token(cls, name: str | None) -> str | None:
        if name is not None and not TOKEN.fullmatch(name):
            raise ValueError(f"{name}: a server's token is in A5S_MCP_<SERVER>_TOKEN")
        return name

    @field_validator("as_person")
    @classmethod
    def _system(cls, name: str | None) -> str | None:
        if name is not None and not SYSTEM.fullmatch(name):
            raise ValueError(f"{name}: a server acts as the person in a system A5S_DELEGATION "
                             "names, in lowercase, such as servicenow")
        return name

    @model_validator(mode="after")
    def _one_token(self) -> Server:
        if self.as_person and self.token_env:
            raise ValueError("a server takes a5s's token or the person's, never both: "
                             "as_person or token_env")
        return self


class Undone(BaseModel):
    """How a change a tool makes is undone (core/undoing.py): with which of the scenario's
    tools, each argument from the change's own (args.<name>) or from its record as it stood
    before (before.<field>), for how many hours after it's made."""

    model_config = ConfigDict(extra="forbid")
    tool: str
    args: dict[str, str]
    hours: float = 24

    def contract(self) -> Undo:
        from datetime import timedelta
        return Undo(tool=self.tool, args=tuple(sorted(self.args.items())),
                    within=timedelta(hours=self.hours))


class Declared(BaseModel):
    """One of a server's tools, as a scenario's agents may use it, in a5s's own words."""

    model_config = ConfigDict(extra="forbid")
    server: str
    calls: str  # the server's own name for it
    description: str  # what a5s says it does
    arguments: dict[str, Any]  # the JSON Schema of what it takes: the server's, in shape
    returns: list[str] = Field(min_length=1)  # the fields of what it returns a5s passes on
    reads: bool = True
    writes: bool = False
    destructive: bool = False
    sends_outside: bool = False
    idempotent: bool = False
    record_arg: str | None = None
    record_field: str | None = None
    action: str | None = None
    handles: list[str] = []
    text_fields: list[str] = []
    outside: list[str] = []
    extract: dict[str, str] = {}
    # what a change's answer says once it's made, field by field, such as `locked: true`: an
    # answer naming its record but saying otherwise is the change taken in hand, not made, as a
    # device management queues a lock until the device next connects (round 13, D2)
    made: dict[str, str | int | float | bool] = {}
    undo: Undone | None = None  # how a change it makes is undone, if it can be

    @model_validator(mode="after")
    def _consistent(self) -> Declared:
        if not CALLS.fullmatch(self.calls):
            raise ValueError(f"{self.calls} isn't a name an MCP server's tool has")
        if self.arguments.get("type") != "object":
            raise ValueError("what a tool takes is a JSON Schema of type object")
        given = set(self.arguments.get("properties") or {})
        if self.action and not self.record_arg:
            raise ValueError("a tool that changes a record names it, by record_arg")
        if self.record_arg and self.record_arg not in given:
            raise ValueError(f"record_arg {self.record_arg} isn't among the arguments it takes")
        if missing := [f for f in self.text_fields if f not in given]:
            raise ValueError(f"text_fields {', '.join(missing)} aren't among its arguments")
        returned = set(self.returns)
        named = [f for f in (self.record_field, *self.handles, *self.outside, *self.made) if f]
        if missing := [f for f in named if f not in returned]:
            raise ValueError(f"{', '.join(missing)} aren't among the fields it returns")
        if self.made and not self.action:
            raise ValueError("only a tool that changes a record says what its answer says once made")
        if self.undo is not None:
            if not self.action:
                raise ValueError("only a tool that changes a record says how to undo it")
            self.undo.contract()  # its arguments' sources, and how long, as a5s takes them
        return self


class Declaration(BaseModel):
    """A scenario's mcp.yaml: its MCP servers, and the tools of theirs its agents may use."""

    model_config = ConfigDict(extra="forbid")
    servers: dict[str, Server]
    tools: dict[str, Declared]

    @model_validator(mode="after")
    def _known(self) -> Declaration:
        for name, server in self.servers.items():
            if not NAME.fullmatch(name):
                raise ValueError(f"{name}: a server's name is lowercase letters, digits and _")
            if server.token_env not in (None, f"A5S_MCP_{name.upper()}_TOKEN"):
                raise ValueError(f"{name}'s token is in A5S_MCP_{name.upper()}_TOKEN, its own, and "
                                 f"no other's: not {server.token_env}")
        seen: dict[tuple[str, str], str] = {}
        for name, tool in self.tools.items():
            if not NAME.fullmatch(name):
                raise ValueError(f"{name}: a tool's name is lowercase letters, digits and _")
            if tool.server not in self.servers:
                raise ValueError(f"{name} comes from {tool.server}, which isn't among the servers")
            if (tool.server, tool.calls) in seen:
                raise ValueError(f"{name} and {seen[(tool.server, tool.calls)]} are both "
                                 f"{tool.server}'s {tool.calls}: a server's tool is declared once")
            seen[(tool.server, tool.calls)] = name
        return self


def declared(folder: Path) -> Declaration | None:
    """A scenario folder's MCP declaration, each key once, or None if it has none."""
    path = folder / FILE
    if not path.is_file():
        return None
    try:
        return Declaration.model_validate(definitions.spec_of(path.read_text(encoding="utf-8")) or {})
    except (ValidationError, ValueError, yaml.YAMLError) as e:
        raise ValueError(f"{path}: {e}") from None


# The transport

class _Expired(Exception):
    """The server ended a5s's session: what was sent wasn't taken, so it can go again."""


class Session:
    """a5s's session with one MCP server, over Streamable HTTP, shared by its tools' calls."""

    def __init__(self, name: str, url: str, token_env: str | None, *,
                 http: httpx.Client | None = None, timeout: float = 30,
                 token: Callable[[], str] | None = None):
        self.name, self.url, self.token_env = name, _origin(url), token_env
        self.token = token  # the person's, as it is when each message goes, for one acting as them
        self.http = http or reach.client(timeout=timeout)
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        self.started: tuple[str | None, str] | None = None  # its session id, and the version
        self.listed: tuple[float, dict[str, dict]] | None = None

    def _headers(self, started: tuple[str | None, str] | None) -> dict[str, str]:
        found = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "Accept-Encoding": "identity"}  # so a5s counts what it holds as it comes
        if started is not None:
            session, version = started
            found["MCP-Protocol-Version"] = version
            if session:
                found["Mcp-Session-Id"] = session
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token:
                raise ConnectorError(f"the {self.name} MCP server's {self.token_env} isn't set")
            found["Authorization"] = f"Bearer {token}"
        elif self.token is not None:
            found["Authorization"] = f"Bearer {self.token()}"
        return found

    def _send(self, message: dict, started: tuple[str | None, str] | None
              ) -> tuple[httpx.Headers, dict | None]:
        """One JSON-RPC message, and the answer to it, if it's a request."""
        wants, until = message.get("id"), time.monotonic() + DEADLINE
        try:
            with self.http.stream("POST", self.url, json=message, headers=self._headers(started),
                                  follow_redirects=False) as answer:
                if answer.status_code == 404 and started is not None and started[0]:
                    raise _Expired
                if 300 <= answer.status_code < 400:
                    raise ConnectorError(f"the {self.name} MCP server answered with a redirect, "
                                         "which a5s doesn't follow")
                if answer.status_code >= 400:
                    raise ConnectorError(f"the {self.name} MCP server answered HTTP "
                                         f"{answer.status_code}", status=answer.status_code)
                if wants is None:
                    return answer.headers, None
                kind = answer.headers.get("content-type", "").split(";")[0].strip().lower()
                chunks = _raw(answer, self.name, until)
                if kind == "text/event-stream":
                    return answer.headers, self._from_stream(_lines(chunks), wants)
                body = b"".join(chunks)
        except httpx.HTTPError as exc:
            raise ConnectorError(f"the {self.name} MCP server couldn't be reached: "
                                 f"{type(exc).__name__}") from None
        try:
            found = json.loads(body)
        except ValueError:
            raise ConnectorError(f"the {self.name} MCP server answered invalid JSON") from None
        if (answered := _answering(found, wants)) is None:
            raise ConnectorError(f"the {self.name} MCP server didn't answer what a5s asked")
        return answer.headers, answered

    def _from_stream(self, lines: Iterator[str], wants: Any) -> dict:
        """The answer to a request, from the events the server streams: what else it sends,
        such as its progress, a5s leaves."""
        total, data = 0, []
        for line in itertools.chain(lines, [""]):
            total += len(line) + 1
            if total > MAX_BYTES:
                raise ConnectorError(f"the {self.name} MCP server answered more than "
                                     f"{MAX_BYTES:,} bytes")
            if line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
            elif not line and data:
                try:
                    event = json.loads("\n".join(data))
                except ValueError:
                    event = None
                data = []
                if (answered := _answering(event, wants)) is not None:
                    return answered
        raise ConnectorError(f"the {self.name} MCP server's stream ended without an answer")

    def _start(self) -> tuple[str | None, str]:
        with self.lock:
            if self.started is not None:
                return self.started
            headers, answer = self._send({
                "jsonrpc": "2.0", "id": next(self.ids), "method": "initialize",
                "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                           "clientInfo": {"name": "a5s", "version": _version()}}}, None)
            result = _result(answer, self.name)
            version = result.get("protocolVersion")
            if version not in SPOKEN:
                raise ConnectorError(f"the {self.name} MCP server speaks MCP {version!s:.40}, "
                                     f"which a5s doesn't: it speaks {', '.join(SPOKEN)}")
            started = (headers.get("mcp-session-id"), str(version))
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"}, started)
            self.started = started
            return started

    def request(self, method: str, params: dict) -> dict:
        """A request's result: once more, in a session of its own, if the server ended a5s's."""
        for attempt in (1, 2):
            started = self._start()
            try:
                _, answer = self._send({"jsonrpc": "2.0", "id": next(self.ids), "method": method,
                                        "params": params}, started)
                return _result(answer, self.name)
            except _Expired:
                with self.lock:
                    if self.started == started:
                        self.started = None
                if attempt == 2:
                    break
        raise ConnectorError(f"the {self.name} MCP server keeps ending a5s's session")

    def tools(self) -> dict[str, dict]:
        """The server's tools as it lists them, by name: asked again once LISTED_FOR has passed."""
        now = time.monotonic()
        if self.listed and now - self.listed[0] < LISTED_FOR:
            return self.listed[1]
        found: dict[str, dict] = {}
        cursor = None
        for _ in range(PAGES):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            for listed in result.get("tools") or []:
                if isinstance(listed, dict) and isinstance(listed.get("name"), str):
                    found[listed["name"]] = listed
            cursor = result.get("nextCursor")
            if not isinstance(cursor, str) or not cursor:
                break
        self.listed = (now, found)
        return found


def _raw(answer: httpx.Response, name: str, until: float) -> Iterator[bytes]:
    """An answer's bytes as they come, never decompressed, counted as they come, within the
    call's deadline: a5s holds no more of it than MAX_BYTES, however it's sent."""
    if answer.headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
        raise ConnectorError(f"the {name} MCP server answered compressed, which a5s asked it not to")
    total = 0
    # one built whole, such as by a stand-in transport, is already in memory: counted all the same
    for chunk in [answer.content] if answer.is_stream_consumed else answer.iter_raw():
        total += len(chunk)
        if total > MAX_BYTES:
            raise ConnectorError(f"the {name} MCP server answered more than {MAX_BYTES:,} bytes")
        if time.monotonic() > until:
            raise ConnectorError(f"the {name} MCP server took more than {DEADLINE:g} seconds to "
                                 "answer")
        yield chunk


def _lines(chunks: Iterator[bytes]) -> Iterator[str]:
    """The lines of an event stream, from its bytes as they come."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *whole, pending = pending.split(b"\n")
        for line in whole:
            yield line.removesuffix(b"\r").decode("utf-8", "replace")
    if pending:
        yield pending.removesuffix(b"\r").decode("utf-8", "replace")


def _answering(message: Any, wants: Any) -> dict | None:
    """The answer to request `wants` in what came back, if it's there."""
    for one in message if isinstance(message, list) else [message]:
        if (isinstance(one, dict) and one.get("id") == wants
                and ("result" in one or "error" in one)):
            return one
    return None


def _result(answer: dict | None, name: str) -> dict:
    if answer is None:
        raise ConnectorError(f"the {name} MCP server didn't answer")
    if "error" in answer:
        said = answer["error"].get("message") if isinstance(answer["error"], dict) else None
        raise ConnectorError(f"the {name} MCP server refused it: {said or 'no reason'!s:.200}")
    if not isinstance(answer.get("result"), dict):
        raise ConnectorError(f"the {name} MCP server's answer has no result")
    return answer["result"]


def _version() -> str:
    import importlib.metadata
    try:
        return importlib.metadata.version("a5s")
    except importlib.metadata.PackageNotFoundError:
        return "0"


# The tools

def contradicts(annotations: Any, tool: Served) -> str | None:
    """Why what the server says of its tool contradicts the declaration, if it does: only what
    it says outright counts, never MCP's defaults, and a declaration may say more than a
    server, never less."""
    said = annotations if isinstance(annotations, dict) else {}
    changes = tool.writes or bool(tool.action) or tool.destructive
    if said.get("readOnlyHint") is False and not changes:
        return "the server says it changes things, and it's declared as only reading"
    if (said.get("destructiveHint") is True and said.get("readOnlyHint") is not True
            and not tool.destructive):
        return "the server says it may destroy what it changes, and it isn't declared destructive"
    if said.get("idempotentHint") is False and tool.idempotent:
        return "the server says asking again does it again, and it's declared as doing it once"
    if said.get("openWorldHint") is True and not (tool.outside or tool.sends_outside):
        return ("the server says it reaches outside the organisation, and it's declared as "
                "neither reading outside content nor sending outside")
    return None


def kept(value: Any, names: frozenset[str]) -> Any:
    """What a tool returned, with only the fields declared, at any depth."""
    if isinstance(value, dict):
        return {k: kept(v, names) for k, v in value.items() if k in names}
    if isinstance(value, list):
        return [kept(v, names) for v in value]
    return value


def unnamed(value: Any, field: str, within: bool = False) -> bool:
    """Whether what a server answered holds something outside any record that a5s's
    need-to-know can't check, by the record each names in `field`: in a list, anything but an
    object naming its record, such as a row or a line of text; and an object naming none that
    holds values of its own, not only lists and objects. Inside a record, what it holds is its."""
    if isinstance(value, dict):
        inside = within or field in value
        if not inside and any(not isinstance(v, (dict, list)) and v is not None
                              for v in value.values()):
            return True
        return any(unnamed(v, field, inside) for v in value.values())
    if isinstance(value, list):
        return any((not within and not (isinstance(v, dict) and field in v))
                   or unnamed(v, field, within) for v in value)
    return False


def loose(value: Any) -> bool:
    """Whether a list anywhere in what a server answered holds anything but objects, such as
    lines of text: from a tool that reads outside content, a5s can't tell those apart from it."""
    if isinstance(value, dict):
        return any(loose(v) for v in value.values())
    if isinstance(value, list):
        return any(not isinstance(v, dict) or loose(v) for v in value)
    return False


def answered(result: dict, tool: Served) -> Any:
    """What a tool's call returns to a5s: its structured content, or its text as JSON, with
    only the fields declared. What a5s can't pass on as JSON, such as an image, it leaves."""
    content = [b for b in result.get("content") or [] if isinstance(b, dict)]
    texts = [b["text"] for b in content if b.get("type") == "text" and isinstance(b.get("text"), str)]
    left = sorted({str(b.get("type"))[:20] for b in content if b.get("type") != "text"})
    if result.get("isError"):
        if tool.outside:  # its words may be the outside content itself
            raise ConnectorError(f"the {tool.server} MCP server's {tool.calls} failed")
        return {"error": " ".join(texts)[:300] or f"the {tool.server} MCP server's tool failed"}
    found = result.get("structuredContent")
    if not isinstance(found, (dict, list)):
        text = "\n".join(texts)
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        found = parsed if isinstance(parsed, (dict, list)) else {"text": text}
    passed = kept(found, frozenset(tool.returns))
    if tool.record_field and unnamed(passed, tool.record_field):
        raise ConnectorError(f"the {tool.server} MCP server's {tool.calls} returned something that "
                             f"names no record by {tool.record_field}, which a5s can't check, so "
                             "it passes none of it on")
    if tool.outside and loose(passed):
        raise ConnectorError(f"the {tool.server} MCP server's {tool.calls} returned lines a5s can't "
                             "tell apart from outside content, so it passes none of it on")
    if tool.action and not (isinstance(passed, dict) and passed.get(tool.record_field or "")):
        # a change is made only as the server says, naming what it changed: anything else, such
        # as words saying why it didn't, is a refusal, never counted, reported or sampled as made
        said = " ".join(texts)[:300]
        return {"error": f"the {tool.server} MCP server didn't say it made the change"
                         + (f": {said}" if said else "")}
    if tool.action and (unmade := [f"{name} is {json.dumps(passed.get(name))}, not {json.dumps(value)}"
                                   for name, value in tool.made if passed.get(name) != value]):
        # taken in hand, not made, such as a lock queued until the device next connects: never
        # counted, reported or sampled as made, and the agent says what the server answered
        return {"error": f"the {tool.server} MCP server has the change in hand, but hasn't made it "
                         f"yet: {'; '.join(unmade)}"}
    if left and isinstance(passed, dict):
        passed = {**passed, "a5s_left_out": f"what a5s doesn't pass on: {', '.join(left)}"}
    return passed


@dataclass(frozen=True)
class Served(Tool):
    """A scenario's tool that an MCP server serves: what its hash covers includes the server's
    name for it, and the fields a5s passes on."""

    server: str = ""
    calls: str = ""
    returns: tuple[str, ...] = ()
    made: tuple[tuple[str, str | int | float | bool], ...] = ()
    as_person: str = ""  # the system it acts as the person in, with their own permissions

    @property
    def schema_hash(self) -> str:
        import hashlib
        mcp: dict[str, Any] = {"server": self.server, "calls": self.calls, "returns": sorted(self.returns)}
        if self.made:  # what counts as made is what its approvers pinned, as what it returns
            mcp["made"] = dict(self.made)
        if self.as_person:  # whose access it calls with, as its approvers pinned it
            mcp["as_person"] = self.as_person
        return hashlib.sha256(canonical({"tool": super().schema_hash, "mcp": mcp}).encode()).hexdigest()


class People:
    """The sessions of a server that acts as the person: one for each person a run acts for,
    with their own token as each message goes, so the server sees each as themselves and lists
    what it offers them. The latest PEOPLE used are kept."""

    def __init__(self, name: str, url: str, system: str, delegated: Delegated | None,
                 http: httpx.Client | None):
        self.name, self.url, self.system, self.delegated, self.http = name, url, system, delegated, http
        self.kept: OrderedDict[str, Session] = OrderedDict()
        self.lock = threading.Lock()

    def of(self, person: str) -> Session:
        if self.delegated is None:
            raise ConnectorError(f"the {self.name} MCP server acts as the person, in {self.system}, "
                                 "and only the core, with its seal keys, acts as anyone")
        with self.lock:
            if (found := self.kept.get(person)) is not None:
                self.kept.move_to_end(person)
                return found
            found = Session(self.name, self.url, None, http=self.http,
                            token=lambda: self._token(person))
            self.kept[person] = found
            while len(self.kept) > PEOPLE:
                self.kept.popitem(last=False)
            return found

    def _token(self, person: str) -> str:
        assert self.delegated is not None
        try:
            return self.delegated(person, self.system)
        except ValueError as e:  # not connected, or the system no longer takes it: in words
            raise ConnectorError(str(e)) from None


def tools(declaration: Declaration, *, sandboxed: bool = False, http: httpx.Client | None = None,
          delegated: Delegated | None = None) -> dict[str, Tool]:
    """The tools a declaration offers, each called through its server's session, or, for one
    that acts as the person, theirs (`delegated` gives their token): in the sandbox, through its
    stand-in, and with no token."""
    sessions: dict[str, Session | People | None] = {}
    for name, server in declaration.servers.items():
        url = server.sandbox if sandboxed else server.url
        if not url:
            sessions[name] = None
        elif server.as_person and not sandboxed:
            sessions[name] = People(name, url, server.as_person, delegated, http)
        else:
            sessions[name] = Session(name, url, None if sandboxed else server.token_env, http=http)
    made: dict[str, Tool] = {}
    for name, d in declaration.tools.items():
        made[name] = _tool(name, d, sessions[d.server],
                           declaration.servers[d.server].as_person or "")
    return made


def _tool(name: str, d: Declared, serving: Session | People | None, as_person: str) -> Served:
    holder: list[Served] = []

    def run(call: ToolCall) -> Any:
        tool = holder[0]
        if serving is None:
            raise ConnectorError(f"the {d.server} MCP server has no stand-in in the sandbox, so "
                                 "its tools don't run here")
        if isinstance(serving, People):  # as the one person the run acts for, or not at all
            if len(call.acts_for) != 1:
                whom = "no one" if not call.acts_for else f"{len(call.acts_for)} people"
                raise ConnectorError(f"the {d.server} MCP server acts as the person a run is for, "
                                     f"in their own account, and this run acts for {whom}, so "
                                     "a5s doesn't call it")
            session = serving.of(call.acts_for[0])
        else:
            session = serving
        offered = session.tools().get(d.calls)
        if offered is None:
            raise ConnectorError(f"the {d.server} MCP server no longer offers {d.calls}")
        if shape(offered.get("inputSchema")) != shape(d.arguments):
            raise ConnectorError(f"the {d.server} MCP server's {d.calls} takes other arguments "
                                 "than declared: a release declares it again before a5s calls it")
        if why := contradicts(offered.get("annotations"), tool):
            raise ConnectorError(f"the {d.server} MCP server's {d.calls}: {why}, so a5s doesn't "
                                 "call it until a release declares it again")
        given = set(d.arguments.get("properties") or {})  # only what it declares it takes
        asked = {"name": d.calls, "arguments": {k: v for k, v in call.args.items() if k in given}}
        if call.key:  # so it makes a change once for each key: nothing else of a5s's goes
            asked["_meta"] = {"a5s/key": call.key}
        try:
            result = session.request("tools/call", asked)
        except ConnectorError:
            if tool.outside:  # its words may be the outside content itself
                raise ConnectorError(f"the {d.server} MCP server's {d.calls} failed") from None
            raise
        return answered(result, tool)

    tool = Served(name=name, description=d.description, schema=d.arguments, run=run,
                  reads=d.reads, writes=d.writes, destructive=d.destructive,
                  sends_outside=d.sends_outside, text_fields=tuple(d.text_fields),
                  handles=tuple(d.handles), record_arg=d.record_arg, record_field=d.record_field,
                  action=d.action, idempotent=d.idempotent, outside=tuple(d.outside),
                  extract=dict(d.extract), server=d.server, calls=d.calls,
                  returns=tuple(d.returns), made=tuple(sorted(d.made.items())),
                  as_person=as_person, undo=d.undo.contract() if d.undo else None)
    holder.append(tool)
    return tool


# The scenario, with them

class Serving:
    """A scenario with the tools its MCP servers serve, beside its own."""

    _a5s_mcp: dict[str, Tool]

    def tools(self) -> dict[str, Tool]:
        return {**super().tools(), **self._a5s_mcp}  # type: ignore[misc]


def served(scenario: Any, folder: Path, *, sandboxed: bool = False,
           reserved: frozenset[str] = frozenset(), http: httpx.Client | None = None,
           delegated: Delegated | None = None) -> Any:
    """A scenario, with the tools its folder's mcp.yaml declares mixed into its own class: the
    same object, unchanged if it declares none. A tool named as one of the scenario's own, or
    of a5s's (`reserved`), stops it here, as it starts."""
    declaration = declared(folder)
    if declaration is None:
        return scenario
    own = {name: tool for name, tool in scenario.tools().items()  # its own alone
           if not isinstance(scenario, Serving) or name not in scenario._a5s_mcp}
    clash = sorted(set(declaration.tools) & (set(own) | set(reserved)))
    if clash:
        raise ValueError(f"{folder / FILE} names {', '.join(clash)}, which the scenario or a5s "
                         "has already: an MCP server's tool takes a name of its own")
    made = tools(declaration, sandboxed=sandboxed, http=http, delegated=delegated)
    if not isinstance(scenario, Serving):
        cls = type(scenario)
        scenario.__class__ = type(cls.__name__, (Serving, cls),
                                  {"__module__": cls.__module__, "__qualname__": cls.__qualname__})
    scenario._a5s_mcp = made
    return scenario
