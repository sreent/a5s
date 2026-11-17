-- The language each person reads (core/languages.py): one of their preferences, which they choose
-- on their own page in the studio, signed in as themselves, so the channels app reads and writes
-- it beside the gateway, which tells each agent that acts for them.

grant select, insert, update on preferences to a5s_channels;
