-- Round 5 of the critique (docs/critique.md).

-- The gateway records a version of the settings and adds signatures to it, but can't change
-- which serial or version a row is, so it can't put an older, wider version back in force.
revoke update on settings_versions from a5s_gateway;
grant update (raw, signatures) on settings_versions to a5s_gateway;

-- An approval made on a card keeps the sign-in that made it by its hash, which the core's
-- seal covers, never as a token that would still work for its last few minutes.
update settings_approvals set token = 'sha256:' || encode(sha256(convert_to(token, 'UTF8')), 'hex')
  where token not like 'sha256:%';

-- Once a report has reached its person, what it told them lives in report_seen alone.
grant update (records) on report_fires to a5s_gateway;
grant delete on report_fires to a5s_gateway;  -- a year on, by retention
