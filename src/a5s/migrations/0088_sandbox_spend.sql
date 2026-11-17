-- What each person's tries of drafts in the sandbox took each day, on real models: a draft's
-- test pane, its cases and their judges, comparing models on them, and a new agent described
-- in words. Each case runs as an instance of its own there, so the sandbox's own budget for a
-- person's day restarts at each, and a judge's calls count towards none: the studio holds each
-- person to a day's tokens across them all (core/studio_api.py).
create table if not exists sandbox_spend (
  person text not null,
  day date not null,  -- in their own time zone
  tokens bigint not null default 0,
  primary key (person, day)
);
alter table sandbox_spend owner to a5s_owner;
grant select, insert, update on sandbox_spend to a5s_channels;
grant select, delete on sandbox_spend to a5s_gateway;  -- exports, erasure, departures, retention
