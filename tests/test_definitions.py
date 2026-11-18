import shutil

import pytest
from pydantic import ValidationError

from a5s import definitions, levels
from conftest import ROOT


def test_the_assistant_loads_with_its_instructions_and_pins():
    d = definitions.load(ROOT / "agents" / "assistant")
    assert d.id == "assistant" and d.autonomy.max == levels.ASKS_FIRST  # for the pilot
    assert d.tool_names == ["search_records", "get_record", "get_messages", "create_draft",
                            "change_due_date", "close_question"]
    assert set(d.pins) == set(d.tool_names)
    assert "only your last message" in d.instructions
    assert d.release_id.startswith("0.1.0+")


def test_any_change_to_the_folder_is_a_new_release(tmp_path):
    folder = tmp_path / "assistant"
    shutil.copytree(ROOT / "agents" / "assistant", folder)
    before = definitions.load(folder).release_id
    (folder / "AGENTS.md").write_text((folder / "AGENTS.md").read_text() + "\n- One more rule.\n")
    assert definitions.load(folder).release_id != before


def test_unknown_fields_are_refused(tmp_path):
    folder = tmp_path / "assistant"
    shutil.copytree(ROOT / "agents" / "assistant", folder)
    (folder / "agent.yaml").write_text((folder / "agent.yaml").read_text() + "autonomous: true\n")
    with pytest.raises(ValidationError):
        definitions.load(folder)


@pytest.mark.parametrize("starts", ["acts on its own", "2"])  # by name, or as before by number
def test_acting_on_its_own_never_comes_from_the_release(tmp_path, starts):
    folder = tmp_path / "assistant"
    shutil.copytree(ROOT / "agents" / "assistant", folder)
    spec = (folder / "agent.yaml").read_text().replace("start: asks first", f"start: {starts}")
    assert f"start: {starts}" in spec
    (folder / "agent.yaml").write_text(spec)
    with pytest.raises(ValidationError):
        definitions.load(folder)


def test_a5s_serves_whichever_scenario_its_configuration_names(tmp_path):
    from a5s import build
    from a5s.config import Config

    cfg = Config(database_url="postgresql://unused", gateway_url="http://unused", service_token="",
                 root=tmp_path, scenario="other_scenario:ServiceDesk",
                 scenario_folder=ROOT / "scenarios" / "sample")
    scenario = build.scenario(cfg)
    assert scenario.name == "service-desk" and scenario.person("ana").name == "Ana Ortiz"
