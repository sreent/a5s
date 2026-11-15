-- The groups the sign-in an approval was made with showed, which the core keeps, under its seal,
-- once it has checked it (core/approvals.py): an approval counts for the roles groups give that
-- both that sign-in and the approver's latest show, never a group they joined, or left, since.
alter table settings_approvals add column if not exists groups text[];
grant update (seal, proof, refused, groups) on settings_approvals to a5s_gateway;
