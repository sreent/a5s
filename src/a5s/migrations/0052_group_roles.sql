-- Roles from the identity provider's groups (core/memberships.py).
--
-- Of the groups each person's latest sign-in showed, those the settings in force name, and when
-- that sign-in was made. They stand until a later sign-in shows otherwise, and go with the rest
-- of what a5s keeps of someone when they're archived or erased.
create table if not exists sign_in_groups (
  person text primary key,
  groups text[] not null default '{}',
  seen_at timestamptz not null
);
grant select, insert, update, delete on sign_in_groups to a5s_gateway, a5s_channels;

-- The core's seal on a version of the settings it checked while it was in force, with a key only
-- the core holds. The roles a version gives groups count towards approving the next version
-- only once the core sealed it, so a version someone wrote into the database gives nothing.
alter table settings_versions add column if not exists sealed text;
grant update (sealed) on settings_versions to a5s_gateway;
