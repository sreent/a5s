-- Budgets: how much model work each run, and each instance for each person each day, has
-- done, in tokens as the providers count them, so the core can stop it at its release's
-- budgets before a run that loops, or a busy day, runs up the bill unseen.

alter table runs add column if not exists tokens bigint not null default 0;

create table if not exists spend (
  instance_id text not null,
  person text not null,  -- whom its runs acted for, or '' for nobody
  day date not null,  -- in the person's own time zone
  tokens bigint not null default 0,
  warned_at timestamptz,  -- when it crossed four fifths of the day's budget
  primary key (instance_id, person, day)
);

alter table spend owner to a5s_owner;

grant update (tokens) on runs to a5s_gateway;
grant select, insert, update on spend to a5s_gateway;
