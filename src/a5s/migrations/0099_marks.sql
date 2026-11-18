-- a5s's own words in a conversation that carry what a run that read content from outside
-- wrote, such as a held change's words in what a5s tells whoever it was for: a run given them
-- is marked too, as one given that run's own turns is (core/gateway.py, round 15, F1)
alter table turns add column if not exists marked boolean not null default false;
