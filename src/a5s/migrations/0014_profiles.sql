-- Profiles and recall. Each run that acts for one person is given their profile, with a
-- short note, in their own words, on how they like to work: an agent offers it, and a5s
-- keeps it once they say yes in a later message. Agents can search their conversation with
-- the person they act for, from the original turns.

create table if not exists profile_notes (
  id bigserial primary key,
  person text not null,
  agent text not null,  -- the agent that offered it
  text text not null,
  offered_at timestamptz not null,
  offered_run uuid not null,
  asked_at timestamptz not null,  -- when the core received the message the offer answered
  confirmed_at timestamptz,
  confirmed_run uuid,
  ended_at timestamptz  -- replaced by a newer note, forgotten, or never confirmed
);
create index if not exists profile_notes_person on profile_notes (person, confirmed_at);

-- The conversation's words, for searching it
create index if not exists turns_words on turns using gin (to_tsvector('simple', content));

alter table profile_notes owner to a5s_owner;

grant select, insert, update on profile_notes to a5s_gateway;
grant usage on sequence profile_notes_id_seq to a5s_gateway;
grant select on turns to a5s_gateway;  -- it searches them, and the scheduler writes them
