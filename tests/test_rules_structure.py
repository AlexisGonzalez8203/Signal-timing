"""Tests for the structural consistency rules."""

from __future__ import annotations

import pytest

from conftest import make_phase, make_plan
from signal_timing.policy import Policy
from signal_timing.rules.base import Severity
from signal_timing.rules.structure import (
    CycleLengthConsistency,
    MaximumGreenAboveMinimum,
    PedestrianTimeFitsSplit,
    PhaseAssignmentComplete,
    RingSumConsistency,
    SplitCoversClearance,
    SplitCoversMinimumGreen,
)


class TestPhaseAssignmentComplete:
    rule = PhaseAssignmentComplete()

    def test_accepts_a_fully_assigned_plan(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_a_phase_missing_from_every_ring(self):
        plan = make_plan(
            phases=[make_phase(n) for n in (1, 2)],
            rings=[[1]],
            barrier_groups=[[1, 2]],
            coordinated_phases=(),
        )
        (finding,) = list(self.rule.check(plan))
        assert finding.phase == 2
        assert "not assigned to any ring" in finding.message

    def test_flags_a_phase_missing_from_every_barrier_group(self):
        plan = make_plan(
            phases=[make_phase(n) for n in (1, 2)],
            rings=[[1], [2]],
            barrier_groups=[[1]],
            coordinated_phases=(),
        )
        (finding,) = list(self.rule.check(plan))
        assert finding.phase == 2
        assert "not assigned to any barrier group" in finding.message

    def test_flags_a_phase_appearing_in_two_rings(self):
        plan = make_plan(
            phases=[make_phase(1)],
            rings=[[1], [1]],
            barrier_groups=[[1]],
            coordinated_phases=(),
        )
        messages = [f.message for f in self.rule.check(plan)]
        assert any("multiple rings" in m for m in messages)

    def test_flags_a_phase_appearing_in_two_barrier_groups(self):
        plan = make_plan(
            phases=[make_phase(1)],
            rings=[[1]],
            barrier_groups=[[1], [1]],
            coordinated_phases=(),
        )
        messages = [f.message for f in self.rule.check(plan)]
        assert any("multiple barrier groups" in m for m in messages)


class TestSplitCoversClearance:
    rule = SplitCoversClearance()

    def test_accepts_a_split_that_leaves_green(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_a_split_shorter_than_its_clearance(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, split_s=4.0, yellow_s=4.0, red_clearance_s=2.0)
        (finding,) = list(self.rule.check(make_plan(phases=phases)))
        assert finding.severity is Severity.ERROR
        assert finding.phase == 2
        assert "leaving no green" in finding.message

    def test_accepts_a_split_exactly_equal_to_clearance(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, split_s=6.0, yellow_s=4.0, red_clearance_s=2.0)
        assert list(self.rule.check(make_plan(phases=phases))) == []

    def test_ignores_an_unused_phase(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, split_s=0.0)
        assert list(self.rule.check(make_plan(phases=phases))) == []


class TestSplitCoversMinimumGreen:
    rule = SplitCoversMinimumGreen()

    def test_accepts_an_adequate_split(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_a_split_that_cannot_serve_minimum_green(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[2] = make_phase(
            3, split_s=10.0, min_green_s=8.0, yellow_s=3.0, red_clearance_s=2.2
        )
        (finding,) = list(self.rule.check(make_plan(phases=phases)))
        assert finding.severity is Severity.ERROR
        assert finding.limit == pytest.approx(13.2)

    def test_tolerance_absorbs_a_rounding_level_shortfall(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[2] = make_phase(
            3, split_s=13.18, min_green_s=8.0, yellow_s=3.0, red_clearance_s=2.2
        )
        assert list(self.rule.check(make_plan(phases=phases))) == []


class TestMaximumGreenAboveMinimum:
    rule = MaximumGreenAboveMinimum()

    def test_accepts_a_max_above_the_min(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_an_inverted_pair(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[3] = make_phase(4, min_green_s=20.0, max_green_s=10.0)
        (finding,) = list(self.rule.check(make_plan(phases=phases)))
        assert finding.severity is Severity.ERROR
        assert finding.phase == 4

    def test_skips_a_phase_with_no_maximum(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[3] = make_phase(4, min_green_s=20.0, max_green_s=None)
        assert list(self.rule.check(make_plan(phases=phases))) == []


class TestRingSumConsistency:
    rule = RingSumConsistency()

    def test_accepts_balanced_rings(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_rings_that_disagree_within_a_group(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[4] = make_phase(5, split_s=25.0)  # ring 2 now sums to 45, ring 1 to 40
        (finding,) = list(self.rule.check(make_plan(phases=phases)))
        assert finding.severity is Severity.ERROR
        assert "Barrier group 1" in finding.message
        assert finding.observed == pytest.approx(45.0)
        assert finding.limit == pytest.approx(40.0)

    def test_an_offsetting_error_in_the_other_group_is_still_caught(self):
        """Two groups can each be unbalanced while the cycle total still works."""
        phases = [make_phase(n) for n in range(1, 9)]
        phases[4] = make_phase(5, split_s=25.0)
        phases[6] = make_phase(7, split_s=15.0)
        assert len(list(self.rule.check(make_plan(phases=phases)))) == 2

    def test_tolerance_absorbs_a_tenth_of_a_second(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[4] = make_phase(5, split_s=20.04)
        assert list(self.rule.check(make_plan(phases=phases))) == []

    def test_skips_a_group_served_by_only_one_ring(self):
        plan = make_plan(
            phases=[make_phase(n) for n in (2, 4)],
            rings=[[2, 4]],
            barrier_groups=[[2], [4]],
            coordinated_phases=(),
        )
        assert list(self.rule.check(plan)) == []


class TestCycleLengthConsistency:
    rule = CycleLengthConsistency()

    def test_accepts_a_matching_cycle(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_a_cycle_that_disagrees_with_the_splits(self):
        (finding,) = list(self.rule.check(make_plan(cycle_length_s=100.0)))
        assert finding.severity is Severity.ERROR
        assert finding.observed == pytest.approx(80.0)
        assert finding.limit == pytest.approx(100.0)

    def test_uses_the_longer_ring_when_rings_disagree(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[4] = make_phase(5, split_s=25.0)  # group 1 is now 45 s, not 40 s
        assert list(self.rule.check(make_plan(phases=phases, cycle_length_s=85.0))) == []

    def test_skips_free_operation(self):
        assert list(self.rule.check(make_plan(cycle_length_s=0.0))) == []


class TestPedestrianTimeFitsSplit:
    rule = PedestrianTimeFitsSplit()

    def test_accepts_pedestrian_time_inside_the_split(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, split_s=20.0, walk_s=7.0, ped_change_s=10.0)
        assert list(self.rule.check(make_plan(phases=phases))) == []

    def test_flags_pedestrian_time_exceeding_the_split(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, split_s=20.0, walk_s=7.0, ped_change_s=21.0)
        (finding,) = list(self.rule.check(make_plan(phases=phases)))
        assert finding.severity is Severity.ERROR
        assert finding.limit == pytest.approx(28.0)

    def test_skips_a_phase_without_pedestrian_service(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []


class TestPolicyOverrides:
    def test_a_looser_tolerance_suppresses_a_small_ring_imbalance(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[4] = make_phase(5, split_s=20.5)
        plan = make_plan(phases=phases, cycle_length_s=80.5)
        assert len(list(RingSumConsistency().check(plan))) == 1
        loose = RingSumConsistency(Policy(interval_tolerance_s=1.0))
        assert list(loose.check(plan)) == []
