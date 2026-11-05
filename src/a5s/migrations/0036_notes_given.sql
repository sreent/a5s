-- What the pilot's last stage shows of the notebook (core/measures.py, docs/pilot.md): how many
-- notes each run was given, beside those the ledger says were kept, refused and let go.

alter table runs add column if not exists notes_given int not null default 0;
grant update (notes_given) on runs to a5s_gateway;
