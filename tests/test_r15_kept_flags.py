"""Round 15, B6: a5s keeps each flag on a held change as one of its sentences, with what changes
in it, and says it as it was kept to whoever reads it: on the decide page, in the message that
asks a decider and on their card, and to each grader of its sample. A sample's seal covers what
its graders are told."""

from __future__ import annotations

from a5s.core import proposals, samples, words
from conftest import SEAL_KEY


def test_flags_kept_before_are_said_as_they_were():
    assert words.flags({"flags": ["kept before, in English"], "flagged": None}, "en") == [
        "kept before, in English"]
    planted = words.kept("{value.__class__} and {x}", value="a")  # only names are put in
    assert words.said("en", planted) == "{value.__class__} and {x}"


def test_a_samples_seal_covers_what_its_graders_are_told_where_a5s_keeps_it():
    kept = {"id": 1, "scenario": "sample", "flags": ["English"], "flagged": [
        words.kept(proposals.READ_OUTSIDE, agent="assistant")]}
    before = {**kept, "flagged": None}  # drawn before a5s kept its words
    for row in (kept, before):
        assert samples.drawn_by_core((SEAL_KEY,), {**row, "drawn_seal": samples.draw_seal(
            (SEAL_KEY,), row)})
    changed = {**kept, "flagged": [words.kept(proposals.READ_OUTSIDE, agent="someone else")],
               "drawn_seal": samples.draw_seal((SEAL_KEY,), kept)}
    assert not samples.drawn_by_core((SEAL_KEY,), changed)
