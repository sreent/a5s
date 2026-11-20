-- The health page is one of the channels app's (core/health_api.py), which reads as
-- a5s_channels, like the other studio pages.
grant select on canary_scores, model_health to a5s_channels;
