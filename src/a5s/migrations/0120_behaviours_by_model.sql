-- A behaviour is what a release does on one model: its own, another an instance's settings put
-- it on, or one it falls back to. What one model earned never counts for another, so a release
-- asks first on a model that earned nothing, whatever its own model earned (round 16, G3).
alter table behaviours add column if not exists model text;  -- null: its own, kept before
alter table behaviours add column if not exists own boolean not null default true;
alter table behaviours drop constraint if exists behaviours_pkey;
create unique index if not exists behaviours_by_model on behaviours (release, action, model);
grant update on behaviours to a5s_gateway;  -- to name the model of the rows kept before

-- The model that answered a sample's run last before its change: what its grade is evidence
-- of. Null for one drawn before: its release's own.
alter table samples add column if not exists model text;
