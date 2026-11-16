-- Slack, beside Teams and Matrix, is a chat a5s writes to itself, as each agent's own app
-- (core/slack.py): what waits to go there is found as quickly as what waits for the others.
drop index if exists outbox_to_push;
create index if not exists outbox_to_push on outbox (id)
  where delivered_at is null and channel in ('teams', 'matrix', 'slack');
