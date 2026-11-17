-- What a chat didn't take in five tries, left in the person's local inbox, is tried again: at
-- once when the chat next takes something for them, else hourly, for a day, unless they read
-- it in the inbox first (round 15, D13). When it fell back, which marks it apart from what a
-- departure or a restore leaves there, which never goes again.
alter table outbox add column if not exists fell_back_at timestamptz;
create index if not exists outbox_fell_back on outbox (person)
  where fell_back_at is not null and delivered_at is null;
grant update (fell_back_at) on outbox to a5s_gateway;
