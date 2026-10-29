-- Which agent each message people collect is from, so the web chat can show a
-- person their conversation with each agent. a5s's own notices name the agent
-- they're about.

alter table outbox add column if not exists agent text;
