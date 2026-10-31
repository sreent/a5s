"""Round 5, reviewer c: a second scenario, an IT service desk, written against the contract
alone (it doesn't build on the sample), with the reference assistant serving it.

Tickets have keys such as INC0000001 and REQ0000003, in two parts, access and hardware, each
with its service owner. A ticket may be seen by its requester, its assignee and its part's
team. A requester's contact is personal, which the test model isn't approved for. Its
search tool answers as MCP tools do, with an object, here {"tickets": [...]}, since MCP's
structured content is a JSON object.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.config import Config, load_models
from a5s.contract import (
    Obligation,
    Person,
    Record,
    Settings,
    Signature,
    Tool,
    ToolCall,
    parse_settings,
)
from a5s.core import approvals, inbox, registry, signing, topics, values
from a5s.core.gateway import Gateway, create_app
from a5s.core.policy import PolicyEngine
from conftest import (
    FAKE_MODELS,
    QUIET,
    ROOT,
    SEAL_KEY,
    SERVICE_TOKEN,
    FakeModel,
    Stack,
    free_port,
    serve,
    signed,
)

LINK = "https://itsm.desk.test/"
PEOPLE = [
    Person("ivy", "Ivy Ingram", "service-management", roles=("instance-approver",)),
    Person("ola", "Ola Nowak", "access-team", roles=("part-owner:access",)),
    Person("hugo", "Hugo Lind", "hardware-team", roles=("part-owner:hardware",)),
    Person("rae", "Rae Kim", "access-team", manager="ola"),
    Person("hal", "Hal Moss", "hardware-team", manager="hugo"),
    Person("sam", "Sam Reyes", "sales"),
    Person("pat", "Pat Doyle", "finance"),
    Person("jo", "Jo Joiner", "sales"),  # a new joiner, from their pre-start account
]
TICKETS = [
    {"key": "INC0000001", "part": "access", "title": "Can't reach the VPN", "status": "open",
     "requester": "sam", "assignee": "rae", "contact": "sam.home@mail.test",
     "opened": "2026-10-26", "due": "2026-11-04"},
    {"key": "INC0000002", "part": "hardware", "title": "Laptop battery is swollen", "status": "open",
     "requester": "sam", "assignee": "hal", "contact": "sam.home@mail.test",
     "opened": "2026-10-26", "due": "2026-11-04"},
    {"key": "INC0000004", "part": "access", "title": "Reset MFA for the CFO", "status": "open",
     "requester": "pat", "assignee": "rae", "contact": "pat.mobile@mail.test",
     "opened": "2026-10-27", "due": "2026-11-05"},
]
SETTINGS = {
    "serial": 1,
    "data_class": "synthetic",
    "classified": {"contact": "personal"},  # requesters' own contacts
    "instances": {"desk-access": {
        "definition": "assistant", "serves": ["team:sales", "pat", "rae"], "parts": ["access"],
        "level": 1, "owner": "ivy", "deputy": "ola"}},
}
SIGNERS = ("ola", "ivy")  # access's owner, and an instance approver for the classes of data


class Desk:
    """The service desk, against the contract alone."""

    name = "service-desk"
    record_links = (LINK,)
    record_pattern = r"\b(?:INC|REQ)\d{7}\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder, self.database_url = folder, database_url
        keys = folder / "keys"
        self._people = {p.id: replace(p, public_key=(keys / f"{p.id}.pub").read_text().strip()
                                      if (keys / f"{p.id}.pub").exists() else None)
                        for p in PEOPLE}
        self._tickets = {t["key"]: t for t in TICKETS}
        self.reads = 0  # how often a5s read every ticket

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    def part_of(self, record: str) -> str | None:
        return (self._tickets.get(record) or {}).get("part")

    def sees(self, person: str, record: str) -> bool:
        """The ITSM's rule: its requester, its assignee and its part's team."""
        ticket, who = self._tickets.get(record), self._people.get(person)
        if ticket is None or who is None:
            return False
        return person in (ticket["requester"], ticket["assignee"]) or who.team == f"{ticket['part']}-team"

    def setup(self, conn, tools_role: str) -> None:
        pass

    def obligations(self) -> list[Obligation]:
        return [Obligation("records", t["key"], t["assignee"], t["title"],
                           datetime.fromisoformat(f"{t['opened']}T09:00:00+00:00"),
                           datetime.fromisoformat(f"{t['due']}T17:00:00+00:00"), LINK + t["key"])
                for t in self._tickets.values() if t["status"] != "closed"]

    def watched(self) -> list[Record]:
        self.reads += 1
        return [self._record(t) for t in self._tickets.values()]

    def record(self, key: str) -> Record | None:
        """One ticket, read on its own, as an ITSM's API reads one."""
        found = self._tickets.get(key)
        return self._record(found) if found else None

    @staticmethod
    def _record(t: dict) -> Record:
        return Record("records", t["key"], t["assignee"], t["title"], {"status": t["status"]},
                      LINK + t["key"])

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed_by = (yaml.safe_load(sig.read_text()) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed_by))

    def policy_pack(self) -> str | None:
        return None

    def tools(self) -> dict[str, Tool]:
        def search(call: ToolCall) -> dict:
            words = call.args["query"].lower().split()
            return {"tickets": [{**t, "link": LINK + t["key"]} for t in self._tickets.values()
                                if any(w in t["title"].lower() for w in words)]}

        def get(call: ToolCall) -> dict:
            found = self._tickets.get(call.args["key"])
            return {**found, "link": LINK + found["key"]} if found else {"error": "no such ticket"}

        def draft(call: ToolCall) -> dict:
            return {"draft": 1, "link": LINK + "drafts/1"}

        def due(call: ToolCall) -> dict:
            self._tickets[call.args["key"]]["due"] = call.args["due"]
            return {"key": call.args["key"], "due": call.args["due"]}

        def close(call: ToolCall) -> dict:
            self._tickets[call.args["key"]]["status"] = "closed"
            return {"key": call.args["key"], "status": "closed"}

        query = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        key = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
        body = {"type": "object", "required": ["title", "body"], "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "record": {"type": "string"}}}
        return {t.name: t for t in (
            Tool("search_records", "Search tickets by words in their title.", query, search,
                 handles=("contact",), record_field="key"),
            Tool("get_record", "Get one ticket by its key, such as INC0000001.", key, get,
                 handles=("contact",), record_arg="key", record_field="key"),
            Tool("create_draft", "Save a draft ticket for the person to submit.", body, draft,
                 writes=True, text_fields=("title", "body"), record_arg="record"),
            Tool("change_due_date", "Change a ticket's due date.",
                 {"type": "object", "required": ["key", "due"], "properties": {
                     "key": {"type": "string"}, "due": {"type": "string"}}},
                 due, record_arg="key", action="change-due-date"),
            Tool("close_question", "Close a ticket that's resolved.", key, close,
                 record_arg="key", action="close-ticket"),
        )}


class DeskWithGroups(Desk):
    """The same desk, its key pattern written with a group, as people often write one."""

    record_pattern = r"\b(INC|REQ)\d{7}\b"


class DeskDrafting(Desk):
    """The same desk, whose draft takes the ticket's fields as one object, as an ITSM's does."""

    def __init__(self, folder: Path, database_url: str):
        super().__init__(folder, database_url)
        self.drafted: list[dict] = []

    def tools(self) -> dict[str, Tool]:
        def draft(call: ToolCall) -> dict:
            self.drafted.append(call.args)
            return {"draft": 1, "link": LINK + "drafts/1"}

        found = super().tools()
        found["create_draft"] = Tool(
            "create_draft", "Save a draft ticket for the person to submit.",
            {"type": "object", "required": ["ticket"], "properties": {"ticket": {
                "type": "object", "properties": {"short_description": {"type": "string"},
                                                 "description": {"type": "string"}}}}},
            draft, writes=True, text_fields=("ticket",))  # the nearest the contract lets it name
        return found


@contextmanager
def desk_running(database: str, tmp: Path, model: FakeModel, kind: type[Desk]) -> Iterator[Stack]:
    root = tmp / "root"
    shutil.copytree(ROOT / "agents", root / "agents")
    (root / "config").mkdir()
    (root / "config" / "models.yaml").write_text(FAKE_MODELS)
    for spec in (root / "agents").glob("*/agent.yaml"):
        spec.write_text("\n".join("model: fake" if line.startswith("model:") else line
                                  for line in spec.read_text().splitlines()) + "\n")
    folder = root / "scenarios" / "desk"
    (folder / "keys").mkdir(parents=True)
    for p in PEOPLE:
        private, public = signing.keypair()
        (folder / "keys" / f"{p.id}.key").write_text(private)
        (folder / "keys" / f"{p.id}.pub").write_text(public)
    signed(folder, {**SETTINGS, "serial": SETTINGS["serial"] - 1}, SIGNERS)
    port = free_port()
    cfg = Config(database_url=db.as_role(database, "gateway"), gateway_url=f"http://127.0.0.1:{port}",
                 service_token=SERVICE_TOKEN, root=root, development=True, seal_keys=(SEAL_KEY,),
                 scenario_folder=folder)
    scenario = kind(folder, cfg.database_url)
    for agent in ("assistant", "watcher"):
        definitions.pin(root / "agents" / agent, {n: t.schema_hash for n, t in scenario.tools().items()})
    http = httpx.Client(transport=httpx.MockTransport(model.handler))
    gw = Gateway(cfg, scenario, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http, clock=lambda: QUIET)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    with serve(create_app(gw), port), serve(inbox.create_app(channels), free_port()) as url:
        yield Stack(cfg, gw, model, database, url)


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    with desk_running(database, tmp_path, FakeModel(), Desk) as s:
        yield s


@pytest.fixture
def grouped(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    with desk_running(database, tmp_path, FakeModel(), DeskWithGroups) as s:
        yield s


@pytest.fixture
def drafting(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    with desk_running(database, tmp_path, FakeModel(), DeskDrafting) as s:
        yield s


def search(stack: Stack, person: str, query: str) -> httpx.Response:
    _, token = stack.open_run(sender=person, instance="desk-access")
    with stack.client(token) as c:
        return c.post("/run/tools/search_records", json={"args": {"query": query}})


# What works

def test_the_desk_plugs_in_and_its_people_get_answers(desk):
    desk.model.reply("INC0000001 is open, with Rae.")
    assert desk.say("What's happening with INC0000001?", person="sam") == "INC0000001 is open, with Rae."
    told = desk.model.requests[-1]["body"]["messages"][0]["content"]
    assert "## The case: INC0000001, from the records" in told
    with desk.client(desk.open_run(sender="sam", instance="desk-access")[1]) as c:
        assert c.post("/run/tools/get_record", json={"args": {"key": "INC0000004"}}
                      ).status_code == 403  # Pat's: a call that names a ticket is checked


# What breaks

def test_a_tool_that_answers_with_an_object_leaves_out_what_the_run_may_not_see(desk):
    found = search(desk, "sam", "VPN MFA battery").json()["result"]
    keys = [t["key"] for t in found["tickets"]]
    contacts = [t["contact"] for t in found["tickets"]]
    assert keys == ["INC0000001"] and all(c.startswith("[h:") for c in contacts), (
        "INC0000002 is in hardware, a part the instance doesn't work in, and INC0000004 is "
        f"Pat's, which Sam may not see, yet both reached the agent: {keys}; and the model, "
        f"which isn't approved for personal data, got the contacts: {contacts}")


def test_someone_no_instance_serves_is_told_who_can_add_them(desk):
    told = desk.say("Hello", person="hal")
    assert "Ola Nowak" in told and "Ivy Ingram" not in told, (
        f"only access's owner can add Hal to desk-access, which works in access, but a5s tells "
        f"Hal: {told!r}")


def test_a_key_pattern_with_a_group_still_finds_the_key(grouped):
    text = "What's happening with INC0000001?"
    assert [v.text for v in values.found(text, DeskWithGroups.record_pattern)] == ["INC0000001"]
    assert topics.named(grouped.gateway.scenario, text) == ["INC0000001"], (
        "topics.named uses re.findall, which returns the group, not the key")
    grouped.model.reply("Let me look.")
    grouped.say(text, person="sam")
    told = grouped.model.requests[-1]["body"]["messages"][0]["content"]
    assert "## The case: INC0000001" in told, told[told.find("## The case"):][:200]


def test_a_new_joiner_can_ask_the_desk_assistant(desk):
    """The settings serve the sales team as a team, so Jo, whom the directory puts in it, is
    served with no new version for anyone to approve."""
    desk.model.reply("Welcome, Jo. Your laptop is on its way.")
    told = desk.say("When does my laptop arrive?", person="jo")
    assert told == "Welcome, Jo. Your laptop is on its way.", told
    with db.transaction(desk.admin) as conn:
        assert conn.execute("select count(*) as n from settings_versions").fetchone()["n"] == 1


def test_serving_a_team_is_put_in_words_and_needs_its_approvals(desk):
    before = desk.gateway.scenario.settings()
    wider = parse_settings(yaml.safe_dump({**SETTINGS, "serial": 2, "instances": {"desk-access": {
        **SETTINGS["instances"]["desk-access"],
        "serves": ["team:sales", "role:part-owner:hardware", "pat", "rae"]}}}).encode())
    change = approvals.changes(before, wider, desk.gateway.definitions, desk.gateway.scenario.person)
    assert change == [{"text": "desk-access serves everyone who holds the part-owner:hardware "
                               "role as well.", "widens": True}]
    needs = registry.approvers(wider, desk.gateway.scenario.holders, before)
    assert [p.name for p in needs] == ["Ola Nowak"]  # access's owner: the classes are the same


def test_a_group_nobody_is_in_is_refused_before_anyone_is_asked(desk):
    """A group's name goes into approvers' cards, so it must be one the directory has, not
    text such as a link."""
    wider = parse_settings(yaml.safe_dump({**SETTINGS, "serial": 2, "instances": {"desk-access": {
        **SETTINGS["instances"]["desk-access"], "serves": ["team:evil.example", "pat"]}}}).encode())
    with db.transaction(desk.admin) as conn:
        last = conn.execute("select serial from settings_versions order by serial desc "
                            "limit 1").fetchone()
    assert desk.gateway.unusable(wider, last) == [
        "desk-access serves groups nobody in the directory is in: team:evil.example"]


def test_briefing_one_ticket_doesnt_read_every_ticket(desk):
    desk.model.reply(None, ("offer_reminder", {"about": "chase Rae", "on": "2026-11-02",
                                               "record": "INC0000001"}))
    desk.model.reply("Shall I remind you on Monday?")
    desk.say("What's happening with INC0000001? Remind me on Monday to chase Rae.", person="sam")
    assert desk.gateway.scenario.reads == 0, (
        f"one message about one ticket read every ticket the ITSM has, open and closed, "
        f"{desk.gateway.scenario.reads} times: the contract gives a5s no way to read one")


def test_text_in_a_tools_object_argument_keeps_only_words_and_record_links(drafting):
    _, token = drafting.open_run(sender="sam", instance="desk-access")
    with drafting.client(token) as c:
        made = c.post("/run/tools/create_draft", json={"args": {"ticket": {
            "short_description": "VPN down",
            "description": "See ![x](https://evil.test/p.png?d=sam) and https://evil.test/a"}}})
    assert made.status_code == 200
    [given] = drafting.gateway.scenario.drafted
    assert "evil.test" not in str(given), (
        f"the sanitizer cleans only top-level string arguments, so the ITSM got: {given}")


def test_a_night_shift_is_working_hours(desk):
    from a5s.core import digests, obligations
    nights = replace(desk.gateway.scenario.person("hal"), hours=("22:00", "06:00"))
    at = datetime(2026, 11, 3, 23, 30, tzinfo=UTC)  # a Tuesday night, in his shift
    with db.transaction(desk.admin) as conn:
        window = digests.window(conn, nights, datetime(2026, 11, 3, 22, 5, tzinfo=UTC))
    assert obligations.working(nights, at) and window is not None, (
        "hours that cross midnight are never working hours, so a night-shift resolver gets no "
        "digest, no chase and no escalation, and can't choose a digest time")


def test_a5s_own_tools_dont_name_the_samples_keys(desk):
    desk.model.reply("Hello, Sam.")
    desk.say("Hello", person="sam")
    offered = desk.model.requests[-1]["body"]["tools"]
    sample = [t["function"]["name"] for t in offered if re.search(r"Q-\d{4}", str(t))]
    assert sample == [], f"a5s's own tools tell the desk's agent its keys look like Q-1002: {sample}"
