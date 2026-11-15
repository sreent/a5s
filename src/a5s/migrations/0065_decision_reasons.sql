-- A rejection's reason is recorded as the decider wrote it, which their sign-in covers, and the
-- core, having checked that, keeps it as whoever asked is told it, under its seal
-- (core/proposals.py, round 11, E-6).
grant update (seal, proof, refused, reason) on proposal_decisions to a5s_gateway;
