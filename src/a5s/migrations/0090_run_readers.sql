-- Round 14 (docs/critique.md): who may read what a run read, beside the records it handled.
-- A document names its readers, and what a run reads with someone's own permissions, or a file
-- they sent, is theirs alone: the studio shows a run, its answer and its words to someone only
-- if they may read each of these (core/studio.py). A run given another's turns, or its
-- question's or answer's words, takes these from that run, and its records too.
create table if not exists run_readers (
  run_id uuid not null,
  rule text not null,  -- canonical JSON: {"alone": true}, or a document's people, teams, roles
  -- and parts, any of which may read it
  primary key (run_id, rule)
);
alter table run_readers owner to a5s_owner;
grant select, insert on run_readers to a5s_gateway;
grant select on run_readers to a5s_channels;
