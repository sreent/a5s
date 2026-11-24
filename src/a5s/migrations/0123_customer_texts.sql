-- The texts a customer's address may be in, which their erasure puts a stand-in for: what was
-- written while a conversation was handed over, and what shadows were asked and answered
-- (round 16, C5)
grant update (text) on handover_replies to a5s_gateway;
grant update (asked, sent, answer) on shadow_answers to a5s_gateway;
