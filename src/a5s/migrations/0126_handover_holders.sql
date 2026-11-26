-- Who answered a conversation handed over to their team, and who wrote what a5s sent for them,
-- go under an archive's name when they leave, as their turns do, so whoever holds their id next
-- isn't named for it; and erasing them erases those words (round 17, D1).
grant update (by_person) on handover_replies to a5s_gateway;
grant update (written_by) on outbox to a5s_gateway;
