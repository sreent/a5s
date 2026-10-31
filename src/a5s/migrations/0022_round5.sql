-- Round 5 of the critique (docs/critique.md).

-- The gateway records a version of the settings and adds signatures to it, but can't change
-- which serial or version a row is, so it can't put an older, wider version back in force.
revoke update on settings_versions from a5s_gateway;
grant update (raw, signatures) on settings_versions to a5s_gateway;
