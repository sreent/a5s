-- Which tenant each registration is in, so a5s knows one it made in a tenant it no longer signs in
-- to, and registers the instance afresh where it does; and the sponsors its agent identity has, so
-- they follow the instance's owner and deputy (round 12, D3, D10). said_sha now holds what a5s last
-- asked to register, refused or not, so a lasting refusal is tried again only once in a while, and
-- recorded only as it changes (D8).
alter table registrations add column if not exists tenant text;
alter table registrations add column if not exists sponsors text[] not null default '{}';
