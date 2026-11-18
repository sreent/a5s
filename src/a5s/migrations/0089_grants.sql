-- Whose grade of an answer said to be wrong each is (core/feedback.py): erasure leaves the
-- grade without whose it was, and a departure puts it under the grader's archive's name, as
-- for a shadow's grades
grant update (graded_by) on answer_feedback to a5s_gateway;
-- The channels app keeps the files sent with a message and never reads one back: the core
-- gives them to the run that answers it (core/files.py), so the channels app reads none
revoke select on inbound_files from a5s_channels;
