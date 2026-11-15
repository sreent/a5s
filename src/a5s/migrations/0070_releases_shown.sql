-- What the studio's home shows each person (core/home.py): the release a5s is, if it waits for
-- their signature. The channels app serves the home, so it reads the releases this deployment
-- recorded: their manifests and signatures, which their approvers signed and keep in the open,
-- and nothing of anyone's beyond who signed. Without it, the home failed for everyone wherever
-- a5s isn't in development, which is the only place it asks.
grant select on releases to a5s_channels;
