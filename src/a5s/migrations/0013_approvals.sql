-- Approving settings where people work. A version of the settings can be proposed to the
-- instance approvers, who each get a card in their chat. An approval is signed through the
-- organisation's identity provider for that one version, works once, and is sealed by the
-- core, which checks the seal again at every run, so editing the database approves nothing.
-- The gateway applies a version once it's approved; settings signed with keys are still
-- the administrator's to apply.

create table if not exists settings_proposals (
  scenario text not null,
  digest text not null,  -- the SHA-256 of exactly the bytes proposed, in hex
  version text not null,  -- as settings_versions names it
  serial bigint not null,
  raw bytea not null,
  proposed_at timestamptz not null default now(),
  outcome text,  -- once it's decided: applied, superseded, or why it was refused
  decided_at timestamptz,
  primary key (scenario, digest)
);

create table if not exists settings_approvals (
  id bigserial primary key,
  scenario text not null,
  digest text not null,
  person text not null,
  token text not null,  -- the identity provider's signed sign-in, as it came
  nonce text not null unique,  -- binds the sign-in to approving this version: it works once
  salt text not null,
  issuer text not null,
  subject text not null,
  approved_at timestamptz not null default now(),
  seal text not null,  -- the core's, over all of the above
  unique (scenario, digest, person),
  foreign key (scenario, digest) references settings_proposals (scenario, digest)
);

alter table settings_proposals owner to a5s_owner;
alter table settings_approvals owner to a5s_owner;

-- The gateway proposes versions, and applies the approved ones.
grant select, insert, update (outcome, decided_at) on settings_proposals to a5s_gateway;
grant select on settings_approvals to a5s_gateway;
grant insert, update on settings_versions to a5s_gateway;
grant insert, update on instances to a5s_gateway;

-- The channels' endpoint, where approvers review a version and approve it.
grant select on settings_proposals to a5s_channels;
grant select on settings_versions to a5s_channels;
grant select, insert on settings_approvals to a5s_channels;
grant usage on sequence settings_approvals_id_seq to a5s_channels;
