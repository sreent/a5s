-- A repeat its owner changes, such as to Fridays at 10:00 (core/repeats.py): the agent offers
-- it again as it'll be, in place of the old one, and it takes the old one's place once they say
-- yes in a later message. The old one stops then, and the new one waits for the task the old
-- one made last, so they never pile up.
alter table task_repeats add column if not exists replaces uuid
  references task_repeats (id) on delete set null;
