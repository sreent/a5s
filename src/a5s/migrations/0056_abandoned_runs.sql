-- A run whose scheduler stopped without closing it, as when it's killed part way, is closed
-- at the core's next sweep, once the scheduler's lease on its work has lapsed, rather than an
-- hour on, when its time is up: so the core reads the leases, which the scheduler alone writes.
grant select on leases to a5s_gateway;
