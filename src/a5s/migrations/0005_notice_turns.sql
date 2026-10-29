-- a5s's own notices to a person join their conversation, so a later run knows
-- that something they asked wasn't finished.

alter table turns drop constraint if exists turns_role_check;
alter table turns add constraint turns_role_check check (role in ('person', 'agent', 'notice'));
