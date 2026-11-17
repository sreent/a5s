-- Round 14 (docs/critique.md): an image's kind is known once a5s has its bytes, as Teams
-- calls one pasted only image/* (core/files.py), so the core keeps the kind it found
grant update (media_type) on run_documents to a5s_gateway;
-- The channels app counts what a person's messages through the web chat hold, unanswered and
-- in bytes a day, by each file's size alone: never its name, its kind or what it says
grant select (inbound_id, size) on inbound_files to a5s_channels;
