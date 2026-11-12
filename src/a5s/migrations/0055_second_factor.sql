-- Round 10: how often a5s refused what counts for want of a second factor, each day, by what
-- was refused, for the status. Only the identity provider's policy, never the person, makes a
-- sign-in show one, so the team that runs a5s should know when sign-ins don't. Counts alone:
-- nobody's id, nor when in the day.
create table if not exists second_factor_refusals (
  day date not null,
  doing text not null,
  n integer not null default 0,
  primary key (day, doing)
);
alter table second_factor_refusals owner to a5s_owner;
grant select, insert, update on second_factor_refusals to a5s_gateway, a5s_channels;
grant delete on second_factor_refusals to a5s_gateway;  -- retention lets the old days go
