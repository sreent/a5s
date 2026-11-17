"""Round 15, the data protection officer's finding (E3): erasing someone who asked an agent in a
group chat erased what everyone else there said was wrong with its answer. An agent's answer in a
group chat is the group's, as the data protection page says, so it stays, under a name no person
has, with what others said of it; what they said of it goes, as do their own answers."""

from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import erasure


def test_erasing_who_asked_in_a_group_chat_leaves_what_others_said_of_its_answer(database):
    with db.transaction(database) as conn:
        group = conn.execute(
            "insert into outbox (person, channel, text, route, delivered_at) values ('ana', "
            "'teams', 'The refund is on its way.', %s, now()) returning id",
            (Jsonb({"channel": "teams", "reply_to": {}, "members": ["ana", "ben"]}),),
        ).fetchone()["id"]
        own = conn.execute("insert into outbox (person, channel, text, delivered_at) values "
                           "('ana', 'teams', 'Just for you.', now()) returning id").fetchone()["id"]
        for outbox, person, said in ((group, "ben", "It isn't on its way"),
                                     (group, "ana", "Wrong amount"), (own, "ana", "No")):
            conn.execute("insert into answer_feedback (outbox_id, agent, person, said, channel) "
                         "values (%s, 'assistant', %s, %s, 'teams')", (outbox, person, said))
    with db.transaction(db.as_role(database, "gateway")) as conn:
        erasure.erase(conn, "ana", datetime.now(UTC), here=True)
    with db.transaction(database) as conn:
        left = conn.execute("select outbox_id, person, said from answer_feedback").fetchall()
        kept = conn.execute("select id, person from outbox").fetchall()
    assert [(r["outbox_id"], r["person"], r["said"]) for r in left] == [
        (group, "ben", "It isn't on its way")]  # ben's, of the group's answer
    assert [r["id"] for r in kept] == [group]  # the group's answer stays, her own goes,
    assert kept[0]["person"].startswith("former:")  # under a name no person has
