"""Round 6, reviewer b: the proposals' sweep reads every waiting change every minute.

Each minute the sweep opens a transaction, and so a new connection to Postgres, for each
change waiting for a decision, to see whether anything about it falls due: a decision, a
reminder, an escalation or its lapse. Nearly always nothing does. With 2,000 changes waiting,
that's about 16 seconds of every minute here, on the scheduler's one thread for sweeps, which
also sends the digests and tries the chats again; past about 7,500 the sweep can't finish in
its minute.
"""

import time

from a5s import db
from test_proposals import asked, sweep

WAITING = 2_000


def test_a_sweep_with_nothing_due_is_quick_however_many_changes_wait(stack, approving):
    asked(stack)  # P-1, waiting for Ana, then as many more, held the same way
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into proposals (scenario, digest, run_id, instance_id, definition, release, "
            "tool, schema_hash, action, args, records, parts, acts_for, deciders, said, flags, "
            "sensitive, read_outside, seq, proposed_at, lapses_at) select scenario, "
            "encode(sha256(convert_to(digest || n::text, 'UTF8')), 'hex'), run_id, instance_id, "
            "definition, release, tool, schema_hash, action, args, records, parts, acts_for, "
            "deciders, said, flags, sensitive, read_outside, seq, proposed_at, lapses_at "
            "from proposals, generate_series(1, %s) n where id = 1", (WAITING,))
    sweep(stack)  # once, so the second is as the minutes after are
    started = time.monotonic()
    sweep(stack)
    took = time.monotonic() - started
    assert took < 4.0, f"{took:.1f}s to find nothing due among {WAITING + 1} waiting changes"
