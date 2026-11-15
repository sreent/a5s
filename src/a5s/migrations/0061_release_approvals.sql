-- What people's signatures over a release approve, each part of it signed (core/releases.py):
-- the image it runs as, by digest, and whether it's approved as a baseline, beside the release
-- it follows (previous) and the advisory it fixes, which are signed with them now. So editing
-- any of them approves nothing: the signatures no longer verify.
alter table releases add column if not exists image text;
alter table releases add column if not exists baseline boolean not null default false;
