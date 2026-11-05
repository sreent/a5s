-- What retention and departures missed (core/retention.py, core/departures.py): what people
-- owed, once the records stopped owing it a year ago, and each person's use of a day's budget
-- and the log of their digests, which only their day needs, and which go when they leave.

grant delete on obligations, spend, digests to a5s_gateway;
