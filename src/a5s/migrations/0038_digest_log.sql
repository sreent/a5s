-- The log of when someone's digest went is let go when they leave (core/departures.py), but a
-- release before 0037 archived it under the leaver's archive name, where nothing reads it.

delete from digests where person like 'former:%';
