-- A group chat's summary (core/groups.py): who heard every turn it holds, so a run is given it
-- only if everyone it acts for heard all of it, and nobody added later learns from it what was
-- said before they joined. A person's own summary has none.

alter table summaries add column if not exists heard_by text[];

-- Someone who leaves: in a group's summary too, they're under their archive's name
grant update (heard_by) on summaries to a5s_gateway;
