-- Answers people said were wrong (core/feedback.py): a "that's wrong" on an agent's answer, in
-- any chat, which its owners grade. Each chat's own id for what a5s sent, so a reaction to it,
-- or Teams' button on it, is known for the answer it is.
alter table outbox add column if not exists sent_as text;  -- Slack's time, Matrix's event, Teams' activity
create index if not exists outbox_sent_as on outbox (channel, sent_as) where sent_as is not null;
grant update (sent_as) on outbox to a5s_gateway;

create table if not exists answer_feedback (
  id bigserial primary key,
  outbox_id bigint not null references outbox (id) on delete cascade,  -- goes with the answer
  run_id uuid,
  instance_id text,
  agent text not null,
  person text not null,  -- who said it was wrong: whom it answered, or someone in the chat then
  said text,  -- why, in their words, for its owners, if they said
  channel text not null,
  at timestamptz not null default now(),
  grade text check (grade in ('right', 'wrong', 'critical')),  -- its owner's, once they check it
  graded_by text,
  graded_at timestamptz,
  unique (outbox_id, person)
);
create index if not exists answer_feedback_waiting on answer_feedback (agent) where grade is null;
alter table answer_feedback owner to a5s_owner;
grant select, insert, update (grade, graded_by, graded_at) on answer_feedback to a5s_channels;
grant usage on sequence answer_feedback_id_seq to a5s_channels;
grant select, delete, update (person) on answer_feedback to a5s_gateway;  -- retention, leaving, erasure
