-- The sample records system honors effect keys, as an idempotent external connector must.
create schema if not exists sample;
create table if not exists sample.drafts (
  id bigserial primary key,
  title text not null,
  body text not null,
  created_for text not null,
  at timestamptz not null default now(),
  record text
);
alter table sample.drafts add column if not exists effect_key text;
create unique index if not exists sample_drafts_effect_key on sample.drafts (effect_key);
