# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Unit tests for F31.2.2 resurfacing scoring (G5, G6, G7)."""

from __future__ import annotations

from exocortex.workers.resurfacing_scoring import score_thought, sm2_next_interval


class TestScoreThought:
    def test_G5_deterministic(self):
        """G5: same input = same output."""
        kwargs = dict(
            thought_id="a",
            sm2_interval=7,
            sm2_repetitions=2,
            sm2_efactor=2.5,
            days_since_last_surfaced=10.0,
            edge_count=2,
            provenance="human",
            human_validated=False,
        )
        assert score_thought(**kwargs) == score_thought(**kwargs)

    def test_G6_linked_beats_unlinked(self):
        """G6: a thought with edge_count>0 > a thought with edge_count=0 at the same SM2."""
        base = dict(
            thought_id="x",
            sm2_interval=7,
            sm2_repetitions=2,
            sm2_efactor=2.5,
            days_since_last_surfaced=10.0,
            provenance="ai_authored",
            human_validated=False,
        )
        linked = score_thought(**base, edge_count=3)
        unlinked_orphan = score_thought(**base, edge_count=0)
        assert linked > unlinked_orphan

    def test_G7_human_beats_ai(self):
        """G7: human provenance > ai_authored at the same SM2/proximity."""
        base = dict(
            thought_id="x",
            sm2_interval=7,
            sm2_repetitions=2,
            sm2_efactor=2.5,
            days_since_last_surfaced=10.0,
            edge_count=2,
        )
        human = score_thought(**base, provenance="human", human_validated=False)
        ai = score_thought(**base, provenance="ai_authored", human_validated=False)
        assert human > ai

    def test_G7_human_validated_beats_unvalidated_ai(self):
        """Provenance ladder: human_validated AI > unvalidated AI."""
        base = dict(
            thought_id="x",
            sm2_interval=7,
            sm2_repetitions=2,
            sm2_efactor=2.5,
            days_since_last_surfaced=10.0,
            edge_count=2,
        )
        validated = score_thought(
            **base, provenance="ai_authored", human_validated=True
        )
        unvalidated = score_thought(
            **base, provenance="ai_authored", human_validated=False
        )
        assert validated > unvalidated

    def test_new_thought_has_score(self):
        """Nowy thought (inf days) dostaje score 1.5 (nie 0)."""
        s = score_thought("x", 1, 0, 2.5, float("inf"), 0, "human", False)
        assert s > 0

    def test_not_due_is_zero(self):
        """A thought that is not overdue (days < interval) → score 0."""
        s = score_thought("x", 14, 3, 2.5, 5.0, 0, "human", False)
        assert s == 0.0

    def test_overdue_capped_at_3x(self):
        """SM2 overdue ratio is capped at 3.0 — no very old thought dominates."""
        very_overdue = score_thought("x", 1, 0, 2.5, 1000.0, 2, "human", False)
        moderately_overdue = score_thought("x", 1, 0, 2.5, 3.0, 2, "human", False)
        assert very_overdue == moderately_overdue


class TestSM2NextInterval:
    def test_sm2_next_interval_progression(self):
        """SM2: 1→6→~15 day progression."""
        i1, r1, e1 = sm2_next_interval(1, 0, 2.5, True)
        assert i1 == 1
        assert r1 == 1
        i2, r2, e2 = sm2_next_interval(i1, r1, e1, True)
        assert i2 == 6
        assert r2 == 2
        i3, r3, e3 = sm2_next_interval(i2, r2, e2, True)
        assert i3 > 6
        assert r3 == 3

    def test_efactor_floor(self):
        """EF never drops below 1.3."""
        _, _, ef = sm2_next_interval(1, 0, 1.3, True)
        assert ef >= 1.3

    def test_efactor_floor_when_not_recalled(self):
        """Even with weak recall EF does not drop below 1.3."""
        _, _, ef = sm2_next_interval(7, 5, 1.3, False)
        assert ef >= 1.3
