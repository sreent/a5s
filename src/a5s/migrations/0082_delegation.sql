-- Acting with someone's own permissions (core/delegation.py): the accounts people connect in
-- systems such as ServiceNow or GitHub, so agents act there as them. Someone starts on their
-- own page, in the channels app, which sends them to the system to say a5s may, and keeps the
-- code it sends them back with; the core alone exchanges it, and keeps their tokens, sealed with
-- a key the channels app hasn't. Neither table holds a token in the clear.
create table if not exists delegation_starts (
  state text primary key,  -- what the system sends back, so a5s knows whose start it is
  person text not null,
  system text not null,
  verifier text not null,  -- PKCE's, so the code is no use without it
  started_at timestamptz not null default now(),
  code text,  -- the system's, once they come back, until the core exchanges it
  coded_at timestamptz
);
create index if not exists delegation_starts_coded on delegation_starts (coded_at) where code is not null;
alter table delegation_starts owner to a5s_owner;
grant select, insert, delete, update (code, coded_at) on delegation_starts to a5s_channels;
grant select, delete, update (code, coded_at) on delegation_starts to a5s_gateway;

create table if not exists delegations (
  person text not null,
  system text not null,
  sealed bytea not null,  -- their tokens, sealed by the core for them and the system alone
  scopes text[] not null default '{}',  -- what the system says a5s may do as them
  expires_at timestamptz,  -- when the access token lapses, by the system's word
  connected_at timestamptz not null default now(),
  used_at timestamptz,  -- when a5s last acted as them there
  primary key (person, system)
);
alter table delegations owner to a5s_owner;
-- what someone's page shows them, never their tokens; and forgetting them, at their word
grant select (person, system, scopes, connected_at, used_at), delete on delegations to a5s_channels;
grant select, insert, update, delete on delegations to a5s_gateway;  -- and retention, leaving, erasure
