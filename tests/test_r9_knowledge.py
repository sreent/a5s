"""Round 9 of the critique: the Markdown knowledge adapter (a5s/knowledge.py). An article may
be for everyone the directory names, or for teams or roles, as well as people and parts; and
search ranks by the whole words a question asks with, never by how long an article is
(docs/critique.md, round 9)."""

from __future__ import annotations

from dataclasses import replace

from a5s.contract import ToolCall
from a5s.master_data import MasterDataScenario
from a5s.service_desk import ServiceDeskScenario
from a5s.software_delivery import SoftwareDeliveryScenario
from conftest import ROOT


def read(scenario, who: str, article: str) -> dict:
    return scenario.tools()["read_knowledge"].run(ToolCall(
        args={"id": article}, instance="i", run="r", acts_for=(who,)))


def first(who: str, question: str) -> str:
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    found = scenario.tools()["search_knowledge"].run(ToolCall(
        args={"query": question}, instance="mdg-desk", run="r", acts_for=(who,)))
    return found["matches"][0]["id"]


def test_a_new_joiner_reads_the_employees_vpn_guide():
    desk = ServiceDeskScenario(ROOT / "scenarios" / "service-desk", "postgresql://unused")
    desk._people["kim"] = replace(desk._people["jo"], id="kim", name="Kim Lee",
                                  identities=())  # joined sales today, as Jo did
    assert "text" in read(desk, "jo", "access/vpn-setup.md")
    assert "text" in read(desk, "kim", "access/vpn-setup.md")  # for everyone, as it says
    assert "error" in read(desk, "nobody-here", "access/vpn-setup.md")  # whom nobody names


def test_an_engineer_reads_how_to_handle_a_secret():
    dev = SoftwareDeliveryScenario(ROOT / "scenarios" / "software-delivery", "postgresql://unused")
    assert "text" in read(dev, "raj", "security/secrets-handling.md")


def test_an_article_for_a_team_or_a_role_is_theirs_alone(tmp_path):
    from a5s.contract import Person
    from a5s.knowledge import MarkdownKnowledge
    (tmp_path / "guide.md").write_text("---\ntitle: For finance\nteams: [finance]\n"
                                       "roles: [auditor]\n---\nHow month end works.\n")
    people = {"ana": Person("ana", "Ana", team="finance"), "kofi": Person(
        "kofi", "Kofi", team="audit", roles=("auditor",)), "chen": Person("chen", "Chen",
                                                                        team="operations")}
    tools = MarkdownKnowledge(tmp_path, person=people.get).tools()
    found = {who: "text" in tools["read_knowledge"].run(ToolCall(
        args={"id": "guide.md"}, instance="i", run="r", acts_for=(who,))) for who in people}
    assert found == {"ana": True, "kofi": True, "chen": False}


def test_the_article_that_answers_comes_first():
    assert first("pia", "bank change callback") == "supplier-bank/bank-change-policy.md"
    assert first("pia", "How is a supplier's bank change confirmed?") == (
        "supplier-bank/bank-change-policy.md")
    assert first("raf", "what base unit for a nut") == "material/units-of-measure.md"
