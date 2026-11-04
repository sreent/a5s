-- The core seals what people approve, decide and grade in the gateway, which nobody outside
-- reaches, not in the channels app, which people do. The channels app records each with the
-- sign-in that made it, and no seal; the gateway checks the sign-in again, seals it, and lets
-- the sign-in go, keeping its hash. What doesn't check out is refused, and never counts.

alter table settings_approvals add column if not exists proof text;  -- the sign-in, until it's sealed
alter table settings_approvals add column if not exists refused text;  -- why the gateway didn't seal it
alter table settings_approvals alter column seal drop not null;
grant update (seal, proof, refused) on settings_approvals to a5s_gateway;

alter table proposal_decisions add column if not exists proof text;
alter table proposal_decisions add column if not exists refused text;
alter table proposal_decisions alter column seal drop not null;
grant update (seal, proof, refused) on proposal_decisions to a5s_gateway;

alter table samples add column if not exists grade_proof text;
grant update (grade_proof) on samples to a5s_channels;
grant update (grade, graded_by, graded_at, grade_token, grade_nonce, grade_salt, grade_issuer,
              grade_subject, grade_seal, grade_proof) on samples to a5s_gateway;

create index if not exists settings_approvals_to_seal on settings_approvals (id)
  where seal is null and refused is null;
create index if not exists proposal_decisions_to_seal on proposal_decisions (id)
  where seal is null and refused is null;
create index if not exists samples_to_seal on samples (id)
  where grade_proof is not null and grade_seal is null;
