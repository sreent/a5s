-- Round 10: a slice that splits its task gives its parts their shares, and its own run is held
-- to the share it kept from then on (core/tasking.py's split): what its run may still spend.
alter table runs add column if not exists task_cap integer check (task_cap >= 0);
grant update (task_cap) on runs to a5s_gateway;
