-- Round 14 (docs/critique.md): when someone in a group chat leaves, its shadow pairs keep them
-- under their archive's name, as its turns do (core/departures.py)
grant update (acts_for) on shadow_answers to a5s_gateway;
