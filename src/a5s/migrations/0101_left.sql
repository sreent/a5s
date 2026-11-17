-- The auditors' and administrators' pages, in the channels app, show someone who has left as a
-- stand-in too, as they show everyone the directory names (core/audit.py, round 15, E1). They
-- read whom a5s found the directory no longer names, by id alone: the trail they read names
-- them already.
grant select (person) on departures to a5s_channels;
