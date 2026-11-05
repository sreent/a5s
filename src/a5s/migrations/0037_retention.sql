-- What retention and departures missed (core/retention.py, core/departures.py): what people
-- owed, once the records stopped owing it a year ago; each person's use of a day's budget and
-- the log of their digests, which only their day needs, and which go when they leave; and the
-- chats of someone who left, which go with the record of their archive.

grant delete on obligations, spend, digests, chats to a5s_gateway;  -- by retention, as it deletes
-- held changes and samples a year after they end, and as each day's use is written
