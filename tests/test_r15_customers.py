"""Round 15's gap, customers in mail: someone outside the directory, such as a customer who
writes to a shared mailbox, couldn't be exported or erased. Now the officer asks by their
address, as for anyone: the export says where a5s keeps it and how much, and an erasure puts a
stand-in for it in each text, lets go of its handles and documents, and keeps what's evidence,
as for anyone. The ledger keeps their address by a digest alone."""

from __future__ import annotations

import json

from a5s import db
from a5s.connectors import mailboxes
from a5s.core import customers
from test_erase import erase
from test_export import export
from test_mailboxes import exchange, mailbox_part, readers, stack, swept  # noqa: F401

PAT = "pat@customer.example"


def wrote(stack, found) -> None:  # noqa: F811
    """Pat's mail, which a mail run reads; and Ana, who asks after Pat by their address."""
    assert swept(stack) == 0
    message = found.arrives(PAT, "Refund on Q-1002", "Please refund the duplicate payment.")
    stack.model.reply(None, ("read_requests", {"key": mailboxes.key_of("requests", message)}))
    stack.model.reply('{"record": "Q-1002", "amount": null, "asks": "refund"}')  # a5s's reader
    stack.model.reply("Read it.")
    assert swept(stack) == 1
    stack.model.reply(f"Yes: {PAT} asked for a refund on Q-1002.")
    stack.say(f"Did {PAT.upper()} write about Q-1002?", person="ana")


def named(stack) -> list[str]:  # noqa: F811
    """Every row of a5s's that still names Pat, by its table."""
    with db.transaction(stack.admin) as conn:
        return [table for table in ("outbox", "inbound", "turns", "run_handles", "run_documents")
                for row in conn.execute(f"select * from {table}")
                if PAT in json.dumps(row, default=str).lower()]


def documents(stack) -> int:  # noqa: F811
    with db.transaction(stack.admin) as conn:
        return conn.execute("select count(*) as n from run_documents").fetchone()["n"]


def test_the_officer_exports_where_a5s_keeps_a_customers_address(stack, exchange):  # noqa: F811
    found, _ = exchange
    wrote(stack, found)
    answer = export(stack, PAT)
    assert answer.status_code == 200, answer.text
    got = answer.json()
    assert (got["address"], got["runs"]["n"], got["changes"]) == (PAT, 1, [])  # as a handle
    assert got["documents"] == 1  # what a5s's reader read of their mail, for an hour
    texts = {kind: t["n"] for kind, t in got["texts"].items()}
    assert texts == {"messages a5s sent people": 1, "messages people sent agents": 1,
                     "what people and agents said in conversations": 2}
    [entry] = [e for e in stack.ledger() if (e["kind"], e["action"]) == ("admin", "export")]
    assert PAT not in json.dumps(entry) and entry["args"]["person"] == customers.subject(PAT)
    assert export(stack, "nobody@nowhere.example").status_code == 404


def test_the_officer_erases_a_customers_address_where_a5s_keeps_it(stack, exchange):  # noqa: F811
    found, _ = exchange
    wrote(stack, found)
    assert set(named(stack)) == {"outbox", "inbound", "turns", "run_handles"}
    assert documents(stack) == 1  # their mail, as a5s's reader read it, which names them not
    done = erase(stack, PAT)
    assert done.status_code == 200, done.text
    assert done.json()["gone"] == {
        "documents a5s's reader read for runs": 1, "handles runs held it as": 1,
        "messages a5s sent people": 1, "messages people sent agents": 1,
        "what people and agents said in conversations": 2}
    assert named(stack) == [] and documents(stack) == 0
    with db.transaction(stack.admin) as conn:
        [sent] = conn.execute("select text from outbox where person = 'ana'").fetchall()
    assert sent["text"] == f"Yes: {customers.STAND_IN} asked for a refund on Q-1002."
    [entry] = [e for e in stack.ledger() if (e["kind"], e["action"]) == ("admin", "erase")]
    assert PAT not in json.dumps(entry)
    assert erase(stack, PAT).status_code == 404  # nothing names them now


def test_an_erasure_waits_while_a_run_holds_their_address(stack, exchange):  # noqa: F811
    found, _ = exchange
    wrote(stack, found)
    with db.transaction(stack.admin) as conn:  # as if the mail run were still at work
        conn.execute("update runs set closed_at = null where id in (select run_id from "
                     "run_handles)")
    refused = erase(stack, PAT)
    assert refused.status_code == 409 and "try again in a minute" in refused.json()["detail"]
    assert "run_handles" in named(stack)


def test_an_address_and_a_directory_id_are_told_apart():
    assert customers.is_address(PAT) and not customers.is_address("ana")
    assert customers.subject("ana") == "ana"
    assert customers.subject(PAT) == customers.subject(PAT.upper()) != PAT
