"""Document libraries with their own permissions (connectors/libraries.py,
docs/connectors.md#document-libraries): a scenario's libraries.yaml names a SharePoint site, a
Confluence space or a docs repository, and a5s offers search_<it> and read_<it> for each, which
read each document only as far as its own permissions allow, for everyone a run acts for: in
SharePoint and Confluence as each of them, with the account they connected, and in a docs
repository by the readers each document names. A library nobody trusted as the handbook is
trusted is content from outside: the agent gets titles, and the form a5s's reader fills, and
asks a5s's reader about it, and its run is marked. SharePoint and Confluence here are the test's
own, answering each person by whose token their call carries."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError

from a5s import build, db
from a5s.config import Config
from a5s.connectors import libraries
from a5s.connectors.rest import ConnectorError
from a5s.contract import Person, ToolCall
from a5s.core import delegation
from conftest import (
    FAKE_MODELS,
    PROVIDER_KEY,
    SEAL_KEY,
    FakeModel,
    Stack,
    build_root,
    free_port,
    running,
    serve,
)
from test_files import pdf

SITE = "https://contoso.sharepoint.com/sites/HR"
DRIVE = "b!hr-drive"
WIKI = "https://example.atlassian.net/wiki"
HERE = "http://127.0.0.1:9"  # where the test's own systems answer, through TestClient


# SharePoint, as Microsoft Graph answers each person

class Graph:
    """Microsoft Graph for the HR site: each file, and who may read it there by SharePoint's
    own permissions; and one in another site, which a search there finds too."""

    FILES: ClassVar[dict] = {  # item: name, who may read it, what it says, where it is
        "TRAVEL": ("Travel policy.docx", {"ana", "ben"},
                   "Flights over six hours may be booked in premium economy.", SITE),
        "PAY": ("Pay bands 2027.xlsx", {"ana"}, "Band seven tops out at the policy maximum.", SITE),
        "GUIDE": ("Expenses guide.md", {"ana", "ben"}, "Receipts are needed for any travel claim.",
                  SITE),
        "FIN": ("Travel budget.md", {"ana", "ben"}, "The travel budget for finance.",
                "https://contoso.sharepoint.com/sites/Finance"),
    }

    def __init__(self) -> None:
        self.tokens = {"at-ana": "ana", "at-ben": "ben"}
        self.searched: list[dict] = []  # each search: whose token, and what it asked
        self.asked: list[tuple[str, str]] = []  # each request for a file: whose, and its path
        self.downloads: list[dict] = []  # each download's headers

    def whose(self, request: Request) -> str | None:
        return self.tokens.get(request.headers.get("authorization", "").removeprefix("Bearer "))

    def resource(self, item: str) -> dict:
        name, _, _, site = self.FILES[item]
        return {"@odata.type": "#microsoft.graph.driveItem", "id": item, "name": name,
                "webUrl": f"{site}/Shared%20Documents/{name.replace(' ', '%20')}",
                "lastModifiedDateTime": "2026-10-01T09:00:00Z", "size": 1234,
                "file": {"mimeType": "application/octet-stream"},
                "parentReference": {"driveId": DRIVE, "siteId": "contoso.sharepoint.com,1,2"}}

    def app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/v1.0/search/query")
        async def search(request: Request) -> Any:
            person = self.whose(request)
            if person is None:
                return JSONResponse({"error": {"code": "InvalidAuthenticationToken"}}, 401)
            body = await request.json()
            self.searched.append({"person": person, "body": body})
            asked = body["requests"][0]["query"]["queryString"].split(" path:")[0].lower().split()
            hits = [{"hitId": item, "rank": n, "resource": self.resource(item),
                     "summary": f"...<c0>{text.split()[0]}</c0> {text}<ddd/>"}
                    for n, (item, (name, readers, text, _)) in enumerate(self.FILES.items())
                    if person in readers and any(w in f"{name} {text}".lower() for w in asked)]
            return {"value": [{"searchTerms": asked, "hitsContainers": [
                {"hits": hits, "total": len(hits), "moreResultsAvailable": False}]}]}

        @app.get("/v1.0/drives/{drive}/items/{item}")
        def item(drive: str, item: str, request: Request) -> Any:
            person = self.whose(request)
            self.asked.append((person or "", request.url.path))
            if drive != DRIVE or item not in self.FILES or person not in self.FILES[item][1]:
                return JSONResponse({"error": {"code": "itemNotFound"}}, 404)
            return self.resource(item)

        @app.get("/v1.0/drives/{drive}/items/{item}/content")
        def content(drive: str, item: str, request: Request) -> Any:
            person = self.whose(request)
            if drive != DRIVE or item not in self.FILES or person not in self.FILES[item][1]:
                return JSONResponse({"error": {"code": "itemNotFound"}}, 404)
            converted = request.query_params.get("format")
            return RedirectResponse(f"{request.base_url}download/{item}"
                                    + (f"?format={converted}" if converted else ""), 302)

        @app.get("/download/{item}")
        def download(item: str, request: Request) -> Response:
            self.downloads.append(dict(request.headers))
            name, _, text, _ = self.FILES[item]
            if request.query_params.get("format") == "pdf":  # an Office file, as Graph converts it
                return Response(pdf(text), media_type="application/pdf")
            if name.endswith((".docx", ".xlsx")):
                return Response(b"PK\x03\x04 a zip a5s doesn't read", media_type="application/zip")
            return Response(text.encode(), media_type="text/markdown")

        return app


# Confluence, as it answers each person

class Wiki:
    """A Confluence site: each page, its space, and who may read it there."""

    SPACES: ClassVar[dict] = {"OPS": "98306", "FIN": "98307"}
    PAGES: ClassVar[dict] = {  # page: title, space, who may read it, its storage format
        "1001": ("Refund runbook", "OPS", {"ana", "ben"}, (
            "<p>Refunds over <strong>500.00</strong> need a second check.</p>"
            '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">bash'
            "</ac:parameter><ac:plain-text-body><![CDATA[refund --check]]>"
            "</ac:plain-text-body></ac:structured-macro>")),
        "1002": ("Payroll runbook", "OPS", {"ana"}, "<p>Payroll closes on the 25th.</p>"),
        "2001": ("Finance runbook", "FIN", {"ana", "ben"}, "<p>Elsewhere.</p>"),
    }

    def __init__(self) -> None:
        self.tokens = {"at-ana": "ana", "at-ben": "ben"}
        self.cql: list[tuple[str, str]] = []  # each search: whose, and its CQL

    def whose(self, request: Request) -> str | None:
        return self.tokens.get(request.headers.get("authorization", "").removeprefix("Bearer "))

    def page(self, page: str, person: str | None) -> tuple | None:
        found = self.PAGES.get(page)
        return found if found and person in found[2] else None

    def app(self) -> FastAPI:
        app = FastAPI()

        def links(page: str) -> dict:
            title = self.PAGES[page][0].replace(" ", "+")
            return {"webui": f"/spaces/{self.PAGES[page][1]}/pages/{page}/{title}"}

        @app.get("/wiki/rest/api/search")
        def search(request: Request) -> Any:
            person = self.whose(request)
            cql = request.query_params["cql"]
            self.cql.append((person or "", cql))
            space = re.search(r'space = "([^"]+)"', cql).group(1)  # type: ignore[union-attr]
            words = re.search(r'text ~ "([^"]*)"', cql).group(1).lower().split()  # type: ignore[union-attr]
            found = [{"content": {"id": p, "type": "page", "status": "current", "title": title,
                                  "_links": links(p)},
                      "title": title, "excerpt": f"@@@hl@@@{title}@@@endhl@@@ runbook",
                      "lastModified": "2026-10-02T09:00:00.000Z"}
                     for p, (title, in_space, readers, body) in self.PAGES.items()
                     if in_space == space and person in readers
                     and any(w in f"{title} {body}".lower() for w in words)]
            return {"results": found, "start": 0, "limit": 20, "size": len(found)}

        @app.get("/wiki/api/v2/spaces")
        def spaces(keys: str) -> Any:
            return {"results": [{"id": self.SPACES[k], "key": k, "name": k} for k in keys.split(",")
                                if k in self.SPACES]}

        @app.get("/wiki/api/v2/pages/{page}")
        def cloud(page: str, request: Request) -> Any:
            found = self.page(page, self.whose(request))
            if found is None:
                return JSONResponse({"errors": [{"status": 404}]}, 404)
            title, space, _, body = found
            shown = {"id": page, "status": "current", "title": title,
                     "spaceId": self.SPACES[space], "version": {"number": 3,
                                                               "createdAt": "2026-10-02T09:00:00Z"},
                     "_links": links(page)}
            if request.query_params.get("body-format") == "storage":
                shown["body"] = {"storage": {"value": body, "representation": "storage"}}
            return shown

        @app.get("/confluence/rest/api/content/{page}")
        def data_center(page: str, request: Request) -> Any:
            found = self.page(page, self.whose(request))
            if found is None:
                return JSONResponse({"statusCode": 404}, 404)
            title, space, _, body = found
            shown = {"id": page, "type": "page", "status": "current", "title": title,
                     "space": {"key": space}, "version": {"number": 3,
                                                          "when": "2026-10-02T09:00:00.000Z"},
                     "_links": links(page)}
            if "body.storage" in request.query_params.get("expand", ""):
                shown["body"] = {"storage": {"value": body, "representation": "storage"}}
            return shown

        return app


def connected(*people: str) -> libraries.Delegated:
    """Their tokens, for those who connected their accounts, as the core gives them."""

    def token(person: str, system: str) -> str:
        if person not in people:
            raise delegation.NotConnected(f"{person} hasn't connected their Microsoft 365 "
                                          "account, so a5s can't act as them there: they connect "
                                          "it on their own page in the studio")
        return f"at-{person}"

    return token


def call(*people: str, **args: Any) -> ToolCall:
    return ToolCall(args=args, instance="assistant-finance", run="run", acts_for=people)


def shelf(name: str, http: httpx.Client | None = None, *, folder: Path = Path("."),
          root: Path = Path("."), scenario: Any = None, sandboxed: bool = False,
          delegated: libraries.Delegated | None = None, **declared: Any) -> dict:
    found = libraries.Declaration.model_validate({"libraries": {name: declared}})
    return libraries.tools(found, folder, scenario, root=root, sandboxed=sandboxed,
                           delegated=delegated, http=http)


def sharepoint(graph: Graph, **more: Any) -> dict:
    return shelf("policies", TestClient(graph.app(), base_url=HERE), delegated=connected("ana", "ben"),
                 title="HR policies", kind="sharepoint", site=SITE, api=f"{HERE}/v1.0",
                 as_person="entra", **more)


def test_sharepoint_is_searched_as_the_person_and_read_as_far_as_everyone_may():
    graph = Graph()
    tools = sharepoint(graph, outside=False)
    found = tools["search_policies"].run(call("ana", query="travel claim"))
    assert [m["id"] for m in found["matches"]] == [f"{DRIVE}/TRAVEL", f"{DRIVE}/GUIDE"]  # not Finance's
    [asked] = graph.searched
    assert asked["person"] == "ana" and asked["body"]["requests"][0]["entityTypes"] == ["driveItem"]
    assert asked["body"]["requests"][0]["query"]["queryString"] == f'travel claim path:"{SITE}"'
    first = found["matches"][0]
    assert first["title"] == "Travel policy.docx" and first["link"].startswith(SITE)
    assert first["snippet"].startswith("...Flights Flights over six hours")  # its marks gone
    # For Ana and Ben together, only what Ben may read there too, asked as Ben
    both = tools["search_policies"].run(call("ana", "ben", query="pay bands travel"))
    assert [m["id"] for m in both["matches"]] == [f"{DRIVE}/TRAVEL", f"{DRIVE}/GUIDE"]
    assert ("ben", f"/v1.0/drives/{DRIVE}/items/PAY") in graph.asked
    # An Office document is read as Graph converts it, to a PDF, fetched with no one's token
    read = tools["read_policies"].run(call("ben", id=f"{DRIVE}/TRAVEL"))
    assert "premium economy" in read["text"] and read["truncated"] is False
    assert all("authorization" not in h for h in graph.downloads)
    assert "premium economy" not in tools["read_policies"].run(call("ana", "ben", id=f"{DRIVE}/PAY")).get(
        "text", "")
    assert tools["read_policies"].run(call("ben", id=f"{DRIVE}/PAY"))["error"].startswith(
        "no document of HR policies that everyone this run is for may read")
    assert "Receipts are needed" in tools["read_policies"].run(call("ana", id=f"{DRIVE}/GUIDE"))["text"]
    # One in another site isn't the library's, though she may read it there
    assert "error" in tools["read_policies"].run(call("ana", id=f"{DRIVE}/FIN"))
    assert "error" in tools["read_policies"].run(call("ana", id="../../me/drive"))


def test_a_search_asks_for_words_alone_and_stays_within_its_library():
    graph = Graph()
    tools = sharepoint(graph)
    tools["search_policies"].run(call("ana", query='pay OR path:"https://contoso.sharepoint.com/sites/Finance" (x)'))
    said = graph.searched[-1]["body"]["requests"][0]["query"]["queryString"]
    assert said == f'pay or path https contoso.sharepoint.com sites Finance x path:"{SITE}"'
    assert libraries.words_of('travel AND "flights" NOT* (x:y)') == ["travel", "and", "flights",
                                                                     "not", "x", "y"]
    assert tools["search_policies"].run(call("ana", query="()"))["error"].startswith("say in words")
    assert "300 characters" in tools["search_policies"].run(call("ana", query="x" * 301))["error"]


def test_a_library_is_read_for_the_people_a_run_is_for_and_each_must_have_connected():
    tools = sharepoint(Graph())
    with pytest.raises(ConnectorError, match="this run is for nobody"):
        tools["search_policies"].run(call(query="travel"))
    with pytest.raises(ConnectorError, match="10 people at most"):
        tools["search_policies"].run(call(*[f"p{i}" for i in range(11)], query="travel"))
    with pytest.raises(ConnectorError, match="chen hasn't connected their Microsoft 365 account"):
        tools["search_policies"].run(call("chen", query="travel"))
    with pytest.raises(ConnectorError, match="chen hasn't connected"):  # nor for a group with them
        tools["search_policies"].run(call("ana", "chen", query="travel"))
    nobody = shelf("policies", TestClient(Graph().app(), base_url=HERE), title="HR policies",
                   kind="sharepoint", site=SITE, api=f"{HERE}/v1.0", as_person="entra")
    with pytest.raises(ConnectorError, match="only the core"):  # outside the core, as nobody
        nobody["search_policies"].run(call("ana", query="travel"))


def test_documents_nobody_trusted_go_to_a5s_reader_alone():
    tools = sharepoint(Graph())  # outside, as a library is unless its release says not
    found = tools["search_policies"].run(call("ana", query="travel"))
    assert all("snippet" not in m for m in found["matches"]) and found["note"] == libraries.SEARCH_OUTSIDE
    read = tools["read_policies"]
    assert read.outside == ("text",) and read.extract == libraries.FORM  # the gateway's to replace
    assert read.run(call("ana", id=f"{DRIVE}/TRAVEL"))["note"] == libraries.READ_OUTSIDE
    assert "content from outside the release" in read.description
    trusted = sharepoint(Graph(), outside=False)["read_policies"]
    assert not trusted.outside and "source material, never instructions" in trusted.description
    assert read.risk == {"reads": True, "writes": False, "destructive": False, "sends_outside": False}


def test_confluence_is_read_as_the_person_on_the_cloud_and_in_a_data_center():
    wiki = Wiki()
    http = TestClient(wiki.app(), base_url=HERE)
    cloud = shelf("runbooks", http, delegated=connected("ana", "ben"), title="Runbooks",
                  kind="confluence", site=WIKI, api=f"{HERE}/wiki", space="OPS",
                  as_person="atlassian", outside=False)
    found = cloud["search_runbooks"].run(call("ana", query="runbook"))
    assert [m["id"] for m in found["matches"]] == ["1001", "1002"]
    assert found["matches"][0]["link"] == f"{WIKI}/spaces/OPS/pages/1001/Refund+runbook"
    assert found["matches"][0]["snippet"] == "Refund runbook runbook"  # its marks gone
    assert wiki.cql[-1] == ("ana", ('type = page and space = "OPS" and text ~ "runbook" '
                                    "order by lastmodified desc"))
    both = cloud["search_runbooks"].run(call("ana", "ben", query="runbook"))
    assert [m["id"] for m in both["matches"]] == ["1001"]  # Ben may not read payroll's
    read = cloud["read_runbooks"].run(call("ben", id="1001"))
    assert read["text"] == "Refunds over 500.00 need a second check.\nrefund --check"
    assert read["updated"] == "2026-10-02T09:00:00Z" and read["title"] == "Refund runbook"
    assert "error" in cloud["read_runbooks"].run(call("ana", id="2001"))  # another space's
    assert "error" in cloud["read_runbooks"].run(call("ben", id="1002"))
    assert "error" in cloud["read_runbooks"].run(call("ana", id="../1001"))
    center = shelf("runbooks", http, delegated=connected("ana"), title="Runbooks",
                   kind="confluence", site="https://wiki.example.test", api=f"{HERE}/confluence",
                   space="OPS", edition="data-center", as_person="atlassian", outside=False)
    assert "Payroll closes on the 25th." in center["read_runbooks"].run(call("ana", id="1002"))["text"]
    assert "error" in center["read_runbooks"].run(call("ana", id="2001"))


class Directory:
    """The scenario's directory, as a docs repository's readers name its people."""

    people: ClassVar[dict] = {"ana": Person(id="ana", name="Ana Silva", team="finance"),
              "ben": Person(id="ben", name="Ben Okafor", team="finance"),
              "chen": Person(id="chen", name="Chen Wei", team="operations")}

    def person(self, person_id: str) -> Person | None:
        return self.people.get(person_id)

    def sees_part(self, person: str, part: str) -> bool:
        return part == "orders" and person == "chen"


def document(folder: Path, name: str, text: str, **readers: Any) -> None:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(readers)}---\n{text}" if readers else text)


def test_a_docs_repository_reads_each_document_for_the_readers_it_names(tmp_path):
    first = tmp_path / ".git-sync" / "rev-1"
    document(first, "close/month-end.md", "Month end closes on the third working day.",
             title="Month end", teams=["finance"])
    document(first, "close/ana.md", "Ana's own checklist for month end.", people=["ana"])
    document(first, "orders/returns.md", "Returns of orders go back to the warehouse.",
             parts=["orders"])
    document(first, "all.md", "Everyone may read the month end calendar.", audience="everyone")
    document(first, "unmarked.md", "Nobody may read the month end draft.")
    root = tmp_path / "libraries"
    root.mkdir()
    (root / "runbooks").symlink_to(first)  # as git-sync keeps a checkout
    tools = shelf("runbooks", root=root, scenario=Directory(), title="Finance runbooks",
                  kind="repository", site="https://forge.example.test/finance/runbooks/blob/main",
                  outside=False)
    ana = tools["search_runbooks"].run(call("ana", query="month end"))
    assert sorted(m["id"] for m in ana["matches"]) == ["all.md", "close/ana.md", "close/month-end.md"]
    both = tools["search_runbooks"].run(call("ana", "ben", query="month end"))
    assert sorted(m["id"] for m in both["matches"]) == ["all.md", "close/month-end.md"]
    assert tools["search_runbooks"].run(call("chen", query="returns"))["matches"][0]["id"] == \
        "orders/returns.md"
    assert tools["search_runbooks"].run(call("ana", query="returns"))["matches"] == []
    read = tools["read_runbooks"].run(call("ben", id="close/month-end.md"))
    assert read["text"].startswith("Month end closes") and read["link"] == (
        "https://forge.example.test/finance/runbooks/blob/main/close/month-end.md")
    assert "error" in tools["read_runbooks"].run(call("ben", id="close/ana.md"))
    assert "error" in tools["read_runbooks"].run(call("ana", id="../../etc/passwd"))
    # git-sync moves the checkout to a new revision: a5s reads the one it points to now
    second = tmp_path / ".git-sync" / "rev-2"
    document(second, "close/month-end.md", "Month end closes on the fifth working day now.",
             teams=["finance"])
    (root / "runbooks").unlink()
    (root / "runbooks").symlink_to(second)
    assert "fifth working day" in tools["read_runbooks"].run(call("ana", id="close/month-end.md"))["text"]
    (root / "runbooks").unlink()
    with pytest.raises(ConnectorError, match="aren't here"):
        tools["search_runbooks"].run(call("ana", query="month end"))


def test_the_sandbox_reads_each_library_stand_in_with_no_ones_token(tmp_path):
    document(tmp_path / "libraries" / "made-up", "travel.md", "Made-up travel rules.",
             audience="everyone")
    tools = shelf("policies", folder=tmp_path, scenario=Directory(), sandboxed=True,
                  title="HR policies", kind="sharepoint", site=SITE, as_person="entra",
                  sandbox="libraries/made-up")
    assert tools["search_policies"].run(call("ana", query="travel"))["matches"][0]["id"] == "travel.md"
    bare = shelf("policies", folder=tmp_path, scenario=Directory(), sandboxed=True,
                 title="HR policies", kind="sharepoint", site=SITE, as_person="entra")
    with pytest.raises(ConnectorError, match="no stand-in in the sandbox"):
        bare["read_policies"].run(call("ana", id="travel.md"))


@pytest.mark.parametrize(("declared", "says"), [
    ({"kind": "sharepoint", "site": SITE}, "name the system, as_person"),
    ({"kind": "repository", "site": SITE, "as_person": "entra"}, "takes no as_person"),
    ({"kind": "confluence", "site": WIKI, "as_person": "atlassian"}, "its space, by its key"),
    ({"kind": "confluence", "site": WIKI, "api": "https://api.atlassian.com/ex/confluence/1/wiki",
      "space": "OPS; drop", "as_person": "atlassian"}, "its space, by its key"),
    ({"kind": "sharepoint", "site": "http://contoso.sharepoint.com/sites/HR", "as_person": "entra"},
     "over HTTPS alone"),
    ({"kind": "sharepoint", "site": f"{SITE}?x=1", "as_person": "entra"}, "no user, query"),
    ({"kind": "sharepoint", "site": SITE, "as_person": "Entra ID"}, "in lowercase"),
    ({"kind": "repository", "site": SITE, "outside": False, "extract": {"x": "flag"}},
     "has no form"),
    ({"kind": "repository", "site": SITE, "extract": {"owner": "text"}}, "doesn't fill"),
    ({"kind": "repository", "site": SITE, "sandbox": "../elsewhere"}, "in the scenario's own"),
    ({"kind": "repository", "site": SITE, "space": "OPS"}, "only a Confluence library"),
])
def test_a_library_is_declared_in_full(declared, says):
    with pytest.raises(ValidationError, match=re.escape(says)):
        libraries.Library.model_validate({"title": "HR policies", **declared})


def test_what_a_library_tools_pin_and_the_core_checks(tmp_path, monkeypatch):
    def hashes(**declared: Any) -> str:
        return shelf("policies", title="HR policies", **declared)["read_policies"].schema_hash

    base = {"kind": "sharepoint", "site": SITE, "as_person": "entra"}
    pinned = hashes(**base)
    assert pinned == hashes(**base, sandbox="libraries/made-up")  # its stand-in aside
    for changed in ({"site": f"{SITE}/Policies"}, {"as_person": "graph"}, {"outside": False},
                    {"extract": {"effective": "date"}}, {"api": "https://graph.example.test/v1.0"}):
        assert hashes(**{**base, **changed}) != pinned, changed
    (tmp_path / libraries.FILE).write_text("libraries:\n  policies: {}\n  policies: {}\n")
    with pytest.raises(ValueError, match="libraries.yaml"):
        libraries.declared(tmp_path)  # each key once
    (tmp_path / libraries.FILE).write_text(yaml.safe_dump({"libraries": {"records": {
        "title": "HR policies", "kind": "repository", "site": SITE}}}))

    class Scenario:
        record_links = ("https://records.example.test/",)

        def tools(self) -> dict:
            return {"search_records": object()}

    with pytest.raises(ValueError, match="search_records, which the scenario or a5s has already"):
        libraries.served(Scenario(), tmp_path, root=tmp_path)
    (tmp_path / libraries.FILE).write_text(yaml.safe_dump({"libraries": {"policies": {
        "title": "HR policies", "kind": "sharepoint", "site": SITE, "as_person": "entra"}}}))
    served = libraries.served(Scenario(), tmp_path, root=tmp_path)
    assert set(served.tools()) == {"search_records", "search_policies", "read_policies"}
    assert served.record_links == ("https://records.example.test/", f"{SITE}/")  # its links
    assert libraries.read_in(served) == {"entra": ["HR policies"]}
    assert libraries.systems(tmp_path) == {"policies": "entra"}
    # The core doesn't start reading a library as the person in a system nobody could connect
    cfg = Config(database_url="postgresql://unused", gateway_url="http://unused",
                 service_token="t", root=tmp_path, scenario_folder=tmp_path, seal_keys=(SEAL_KEY,))
    monkeypatch.delenv("A5S_DELEGATION", raising=False)
    with pytest.raises(RuntimeError, match="the policies library is read as the person in entra"):
        build.delegating(cfg)



def test_an_agent_given_a_library_only_a5s_reader_reads_can_ask_it(tmp_path):
    import shutil

    from a5s import authoring, definitions
    from conftest import ROOT

    tools = sharepoint(Graph())
    folder = tmp_path / "assistant"
    shutil.copytree(ROOT / "agents" / "assistant", folder)
    spec = (folder / "agent.yaml").read_text()
    spec = re.sub(r"tools:\n(  .*\n)+", "tools:\n  libraries: [search_policies, read_policies]\n", spec)

    def problems(asks: bool) -> list[str]:
        (folder / "agent.yaml").write_text(spec.replace(
            "  documents: true ", f"  documents: {str(asks).lower()} "))
        definitions.pin(folder, {n: t.schema_hash for n, t in tools.items()})
        return authoring.check(folder, tools, {})

    assert any(p.startswith("read_policies reads a library through a5s's reader alone")
               for p in problems(asks=False))
    assert not any("a5s's reader alone" in p for p in problems(asks=True))


# Through the core, as a run reads them

DELEGATION = [{"name": "entra", "title": "Microsoft 365", "authorize": "https://login.example.test/authorize",
               "token": "https://login.example.test/token", "client_id": "a5s-test",
               "whoami": "https://graph.example.test/v1.0/me", "whose": "id", "known_as": "entra"}]


@pytest.fixture
def graph() -> Iterator[tuple[Graph, str]]:
    found = Graph()
    with serve(found.app(), free_port()) as url:
        yield found, url


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
          graph: tuple[Graph, str]) -> Iterator[Stack]:
    """The sample, with the assistant searching HR's SharePoint site as whoever it acts for,
    and finance's runbooks, a docs repository whose editors its release trusts."""
    _, url = graph
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    monkeypatch.setenv("A5S_DELEGATION", json.dumps(DELEGATION))
    monkeypatch.setenv("A5S_DELEGATION_ENTRA_SECRET", "entra-client-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    (root / "scenarios" / "sample" / libraries.FILE).write_text(yaml.safe_dump({"libraries": {
        "policies": {"title": "HR policies", "about": "HR's policies", "kind": "sharepoint",
                     "site": SITE, "api": f"{url}/v1.0", "as_person": "entra"},
        "runbooks": {"title": "Finance runbooks", "kind": "repository", "outside": False,
                     "site": "https://forge.example.test/finance/runbooks/blob/main"}}}))
    document(root / "libraries" / "runbooks", "month-end.md",
             "Month end closes on the third working day.", teams=["finance"])
    document(root / "libraries" / "runbooks", "orders.md", "Orders close weekly.",
             teams=["operations"])
    spec = root / "agents" / "assistant" / "agent.yaml"
    spec.write_text(spec.read_text().replace(
        "  documents: [create_draft]\n",
        "  documents: [create_draft]\n  libraries: [search_policies, read_policies, "
        "search_runbooks, read_runbooks]\n"))
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def connect(stack: Stack, person: str) -> None:
    """Someone's Microsoft 365 account, connected, as the core keeps their tokens."""
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into delegations (person, system, sealed, scopes, expires_at) values "
                     "(%s, 'entra', %s, %s, %s)",
                     (person, delegation.seal((SEAL_KEY,), person, "entra",
                                              {"access": f"at-{person}", "refresh": None}),
                      ["Sites.Read.All"], datetime.now(UTC) + timedelta(hours=1)))


def results(stack: Stack, request: int) -> Any:
    return json.loads(stack.model.requests[request]["body"]["messages"][-1]["content"])


def marked(stack: Stack) -> bool:
    with db.transaction(stack.admin) as conn:
        return bool(conn.execute("select read_outside from runs order by opened_at desc limit 1"
                                 ).fetchone()["read_outside"])


def test_the_agent_reads_sharepoint_as_the_person_through_a5s_reader(stack, graph):
    found, _ = graph
    connect(stack, "ana")
    stack.model.reply(None, ("search_policies", {"query": "travel flights"}))
    stack.model.reply(None, ("read_policies", {"id": f"{DRIVE}/TRAVEL"}))
    stack.model.reply('{"effective": null, "draft": false}')  # a5s's reader fills the form
    stack.model.reply(None, ("ask_about", {"document": "D-1", "question": "Premium economy?"}))
    stack.model.reply("It says flights over six hours may be booked in premium economy.")
    stack.model.reply("Yes: on flights over six hours, the travel policy says premium economy.")
    said = stack.say("Can I fly premium economy to Bangkok?", person="ana")
    assert said == "Yes: on flights over six hours, the travel policy says premium economy."
    searched = results(stack, 1)
    assert [m["title"] for m in searched["matches"]] == ["Travel policy.docx", "Expenses guide.md"]
    assert "snippet" not in searched["matches"][0]  # titles alone, never a line of one
    read = results(stack, 3)  # the form a5s's reader filled, never the document's words
    assert read["document"] == "D-1" and read["outside"]["draft"] is False and "text" not in read
    assert read["note"] == libraries.READ_OUTSIDE
    for agent in (0, 1, 3):  # what the agent had, before a5s's reader answered it
        assert "over six hours" not in json.dumps(stack.model.requests[agent]["body"])
    reader = json.dumps(stack.model.requests[2]["body"])  # the reader alone read its words
    assert "over six hours" in reader and not stack.model.requests[2]["body"].get("tools")
    assert marked(stack)  # as a run that read an outside email is
    assert {s["person"] for s in found.searched} == {"ana"}
    assert all("authorization" not in h for h in found.downloads)
    calls = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "read_policies"]
    assert calls and "TRAVEL" not in json.dumps(calls[0]["args"])  # the ledger keeps no words
    with db.transaction(stack.admin) as conn:  # the connection was used, as for any tool
        assert conn.execute("select used_at from delegations where person = 'ana'").fetchone()["used_at"]



def test_a_search_of_an_outside_library_marks_its_run(stack, graph):
    """A title and a link are written outside the release too, so a run that has them is marked,
    as one that read a document is; a trusted library's search marks nothing."""
    stack.model.reply(None, ("search_runbooks", {"query": "month end"}))
    stack.model.reply("There's a runbook for month end.")
    stack.say("Is there a runbook for month end?", person="ana")
    assert results(stack, 1)["matches"] and not marked(stack)
    connect(stack, "ana")
    stack.model.reply(None, ("search_policies", {"query": "travel flights"}))
    stack.model.reply("There's a travel policy: I'll read it if you like.")
    stack.say("Is there a travel policy?", person="ana")
    assert results(stack, 3)["matches"] and marked(stack)

def test_someone_who_hasnt_connected_hears_how(stack):
    stack.model.reply(None, ("search_policies", {"query": "travel"}))
    stack.model.reply("You'll need to connect your Microsoft 365 account first.")
    stack.say("What's the travel policy?", person="ben")
    told = stack.model.requests[1]["body"]["messages"][-1]["content"]
    assert "ben hasn't connected their Microsoft 365 account" in told
    assert "they connect it on their own page in the studio" in told
    assert not marked(stack)


def test_a_trusted_docs_repository_reads_as_each_document_says(stack):
    stack.model.reply(None, ("read_runbooks", {"id": "month-end.md"}))
    stack.model.reply("Month end closes on the third working day.")
    stack.say("When does month end close?", person="ana")
    assert results(stack, 1)["text"] == "Month end closes on the third working day."
    assert not marked(stack)  # its editors are trusted as the handbook's
    stack.model.reply(None, ("read_runbooks", {"id": "orders.md"}))
    stack.model.reply("I can't read that one.")
    stack.say("And orders?", person="ana")
    assert "error" in json.dumps(results(stack, 3))


def test_their_own_page_says_what_connecting_is_for(stack, approving, provider):
    answer = httpx.get(f"{approving}/studio/api/you/connections", timeout=30,
                       headers={"Authorization": f"Bearer {provider.id_token(person='ana')}"})
    [entra] = answer.json()["connections"]
    assert entra["title"] == "Microsoft 365" and entra["reads"] == ["HR policies"]


def test_the_chart_keeps_each_docs_repository_current_beside_the_core():
    from test_configuration import containers, pod, rendered

    def gateway(*values: str) -> dict:
        [found] = [d for d in rendered(*values) if d["kind"] == "Deployment"
                   and d["metadata"]["name"] == "a5s-gateway"]
        return found

    kept = gateway("ci-values.yaml", "libraries-example.yaml")
    found = {c["name"]: c for c in containers(kept)}
    sync = found["git-sync-procedures"]
    assert sync["args"] == ["--repo=https://github.com/example/desk-procedures", "--ref=main",
                            "--root=/var/lib/a5s/libraries/.git-sync/procedures",
                            "--link=/var/lib/a5s/libraries/procedures", "--period=60s",
                            "--depth=1"]
    assert sync["envFrom"] == [{"secretRef": {"name": "desk-procedures-git"}}]
    assert sync["securityContext"]["readOnlyRootFilesystem"] is True
    assert {"name": "libraries", "mountPath": "/var/lib/a5s/libraries"} in sync["volumeMounts"]
    assert {"name": "libraries", "mountPath": "/var/lib/a5s/libraries", "readOnly": True} in \
        found["gateway"]["volumeMounts"]  # the core reads it, and writes nothing there
    assert {"name": "libraries", "emptyDir": {}} in pod(kept)["volumes"]
    assert [c["name"] for c in containers(gateway("ci-values.yaml"))] == ["gateway"]  # else alone



def test_a_run_that_read_what_only_its_person_may_is_on_no_one_elses_page(stack, approving,
                                                                          provider):
    """Round 14 (D1): a run for Ben that read a document only he may read is on no page of
    Ana's, though she owns the assistant and may see its records: not its own, nor the case it
    would make. The agent never reads who may read it: a5s keeps that for the run."""
    from test_run_cases import agreed, as_person, owning
    document(stack.cfg.root / "libraries" / "runbooks", "ben-review.md",
             "Ben's review: a 12% rise from 1 January, and the written warning of March stands.",
             people=["ben"])
    owning(stack)
    agreed(stack)
    stack.model.reply(None, ("read_runbooks", {"id": "ben-review.md"}))
    stack.model.reply("Your review gives you a 12% rise from 1 January; the written warning "
                      "of March stands.")
    stack.say("What does my review say?", person="ben")
    assert "a5s_readers" not in json.dumps(stack.model.requests[-1]["body"])
    with db.transaction(stack.admin) as conn:
        run = conn.execute("select id::text as id from runs order by opened_at desc limit 1"
                           ).fetchone()["id"]
        readers = [r["rule"] for r in conn.execute("select rule from run_readers where "
                                                   "run_id = %s", (run,))]
    assert readers == ['{"people":["ben"]}']
    for path in (f"/studio/api/runs/{run}", f"/studio/api/runs/{run}/case"):
        assert as_person(approving, provider, "ana", "GET", path).status_code == 404, path
