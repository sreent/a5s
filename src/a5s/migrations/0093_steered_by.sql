-- Round 14 (docs/critique.md): someone of a team who answered a person while their conversation
-- was handed over decides nothing their answer may have asked for, as nobody decides what their
-- own words in a group chat asked for: a held change keeps whose answers its run was given
-- (core/handover.py, core/proposals.py).
alter table proposals add column if not exists steered_by text[] not null default '{}';

-- The scheduler answers what someone wrote while their conversation was handed over only once
-- they've been told it's handed back, with what they wrote meanwhile (core/gateway.py)
grant select (back_told_at) on handovers to a5s_scheduler;

-- And what someone of a team wrote a person, which a5s sends as the agent's bot, says whose it
-- is, so a chat shows it as theirs, never under a5s's own mark (core/inbox.py).
alter table outbox add column if not exists written_by text;
