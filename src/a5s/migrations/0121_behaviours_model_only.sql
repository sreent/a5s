-- The gateway names the model of the rows kept before models were named, and changes nothing
-- else of them: which behaviour a release, a type of action and a model map to is worked out
-- from the release a5s loaded, never taken from this table, so a row changed in the database
-- earns nothing (round 16, A4)
revoke update on behaviours from a5s_gateway;
grant update (model) on behaviours to a5s_gateway;
