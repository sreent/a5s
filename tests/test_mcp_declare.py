"""`a5s mcp declare`: the first draft of an MCP server's declaration, from what it lists of its
tools (connectors/declaring.py). What the server says starts the draft and is never taken as
a5s's word: its descriptions are marked for rewording, its hints set at least the flags they
say, a tool saying nothing of itself is drafted as writing, and the fields a5s passes on are
left for its author, so a5s refuses the draft until someone has chosen them. The server here is
the MCP SDK's own, as tests/test_mcp.py serves it."""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from pydantic import ValidationError

from a5s import cli
from a5s.connectors import declaring, mcp
from conftest import ROOT
from test_mcp import tickets  # noqa: F401  # the fixture: a tickets system's MCP server

CLOSE = {"name": "closeTicket", "description": "Close a ticket.\n  It can't be reopened.",
         "inputSchema": {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}},
         "outputSchema": {"type": "object", "properties": {"status": {"type": "string"},
                                                           "key": {"type": "string"}}},
         "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}}


def test_a_draft_starts_from_what_the_server_says_and_leaves_its_author_the_rest(tickets):  # noqa: F811
    listed = mcp.Session("tickets", tickets, None).tools()
    said = declaring.draft("tickets", tickets, listed, None, day=date(2026, 11, 27))
    assert said.startswith("# A first draft of tickets's MCP declaration, from the tools "
                           f"{tickets} listed on 2026-11-27")
    drafted = yaml.safe_load(said)
    assert drafted["servers"] == {"tickets": {"url": tickets}}  # no token it wasn't given
    search, browse, wipe = (drafted["tools"][name] for name in ("search", "browse", "wipe"))
    assert (search["server"], search["calls"], search["description"]) == ("tickets", "search",
                                                                          "Search the tickets.")
    assert search["arguments"] == listed["search"]["inputSchema"]  # in shape, as a5s checks it
    assert "writes" not in search  # it says it only reads
    assert browse["sends_outside"] is True  # it says it reaches outside
    assert wipe["writes"] is True  # it says nothing of itself
    assert "# the server's own words: say what it's for in a5s's" in said
    assert not any("returns" in tool for tool in drafted["tools"].values())
    with pytest.raises(ValidationError, match="returns"):  # until its author chooses them
        mcp.Declaration.model_validate(drafted)
    for tool in drafted["tools"].values():
        tool["returns"] = ["items"]
    assert set(mcp.Declaration.model_validate(drafted).tools) == {"search", "browse", "wipe"}


def test_a_changes_hints_set_at_least_its_flags_and_its_name_is_as_a5s_names_one():
    said = declaring.draft("desk", "https://desk.example/mcp", {"closeTicket": CLOSE},
                           "A5S_MCP_DESK_TOKEN")
    drafted = yaml.safe_load(said)
    assert drafted["servers"]["desk"]["token_env"] == "A5S_MCP_DESK_TOKEN"
    close = drafted["tools"]["close_ticket"]
    assert close["calls"] == "closeTicket" and close["description"] == "Close a ticket. It can't be reopened."
    assert (close["writes"], close["destructive"], close["idempotent"]) == (True, True, True)
    assert "it says it returns key, status" in said  # which its author chooses among
    assert "say the action it is, with record_arg" in said
    assert declaring.agents_name("get-ticket.v2") == "get_ticket_v2"
    with pytest.raises(ValueError, match="lists no tool openTicket: it lists closeTicket"):
        declaring.draft("desk", "https://desk.example/mcp", {"closeTicket": CLOSE}, None, ["openTicket"])


def test_the_command_line_prints_the_draft_or_writes_a_file_of_its_own(tickets, tmp_path, monkeypatch,  # noqa: F811
                                                                      capsys):
    monkeypatch.setenv("A5S_ROOT", str(ROOT))
    cli.main(["mcp", "declare", tickets, "--server", "tickets", "--tool", "search"])
    drafted = yaml.safe_load(capsys.readouterr().out)
    assert list(drafted["tools"]) == ["search"]
    out = tmp_path / "tickets.draft.yaml"
    cli.main(["mcp", "declare", tickets, "--server", "tickets", "--out", str(out)])
    assert set(yaml.safe_load(out.read_text(encoding="utf-8"))["tools"]) == {"search", "browse", "wipe"}
    for argv, says in [(["--out", str(out)], "a new file of its own"),
                       (["--out", str(tmp_path / "mcp.yaml")], "a new file of its own"),
                       (["--tool", "nothing"], "lists no tool nothing")]:
        with pytest.raises(SystemExit, match=says):
            cli.main(["mcp", "declare", tickets, "--server", "tickets", *argv])
    with pytest.raises(SystemExit, match="lowercase letters, digits and _"):
        cli.main(["mcp", "declare", tickets, "--server", "Tickets"])
