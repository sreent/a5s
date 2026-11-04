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

-- What a5s writes to a chat it writes to itself, such as Teams or Matrix, goes in the outbox
-- too, in the transaction that decides it, and is delivered after: tried again with longer
-- waits while the chat doesn't take it, and in the end left in the person's local inbox.
alter table outbox add column if not exists route jsonb;  -- where in the chat, and how to start it
alter table outbox add column if not exists card jsonb;  -- in Teams, a card in place of the text
alter table outbox add column if not exists attempts int not null default 0;
alter table outbox add column if not exists retry_at timestamptz;
alter table outbox add column if not exists problem text;  -- why the chat didn't take it last
create index if not exists outbox_to_push on outbox (id)
  where delivered_at is null and channel in ('teams', 'matrix');
grant update (channel, inbound_id, attempts, retry_at, problem) on outbox to a5s_gateway;

-- When a5s first found someone's digest waiting for its agents' work, so it waits half an hour
-- at most, from then, and goes with what's ready.
create table if not exists digest_waits (
  person text not null,
  due_at timestamptz not null,
  since timestamptz not null,
  primary key (person, due_at)
);
alter table digest_waits owner to a5s_owner;
grant select, insert, delete on digest_waits to a5s_gateway;

-- What a5s writes in its own words in an agent's chat, such as an escalation, goes in the
-- conversation too, so the agent's next run knows what the person is answering.
grant insert on turns to a5s_gateway;
grant usage on sequence turns_id_seq to a5s_gateway;

-- The status reads the last day's denials newest first: by this index, not the whole ledger.
create index if not exists ledger_denied on ledger (seq) where decision = 'deny';
