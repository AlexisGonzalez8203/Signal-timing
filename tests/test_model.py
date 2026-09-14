"""Tests for the timing plan domain model."""

from __future__ import annotations

import pytest

from conftest import make_phase, make_plan
from signal_timing.model import (
    STANDARD_BARRIER_GROUPS,
    STANDARD_RINGS,
    Approach,
    Phase,
    PlanStructureError,
    TimingPlan,
)


class TestPhase:
    def test_green_is_split_less_clearance(self):
        phase = make_phase(2, split_s=30.0, yellow_s=4.0, red_clearance_s=2.0)
        assert phase.clearance_s == pytest.approx(6.0)
        assert phase.green_s == pytest.approx(24.0)

    def test_green_goes_negative_when_split_cannot_cover_clearance(self):
        """The model reports the arithmetic; the rules decide it is a problem."""
        phase = make_phase(2, split_s=4.0, yellow_s=4.0, red_clearance_s=2.0)
        assert phase.green_s == pytest.approx(-2.0)

    def test_phase_without_pedestrian_timing_does_not_serve_pedestrians(self):
        assert make_phase(2).serves_pedestrians is False
        assert make_phase(2).total_pedestrian_s is None

    def test_walk_alone_marks_the_phase_as_serving_pedestrians(self):
        phase = make_phase(2, walk_s=7.0)
        assert phase.serves_pedestrians is True
        assert phase.total_pedestrian_s == pytest.approx(7.0)

    def test_total_pedestrian_time_sums_walk_and_change(self):
        phase = make_phase(2, walk_s=7.0, ped_change_s=14.0)
        assert phase.total_pedestrian_s == pytest.approx(21.0)

    def test_round_trips_through_dict(self):
        original = make_phase(
            4,
            walk_s=7.0,
            ped_change_s=14.0,
            protected_left=True,
            approach=Approach(speed_mph=35.0, grade=-0.02, crossing_distance_ft=60.0),
        )
        restored = Phase.from_dict(original.to_dict())
        assert restored == original


class TestTimingPlanDefaults:
    def test_applies_standard_rings_and_barriers(self, balanced_plan):
        assert balanced_plan.rings == STANDARD_RINGS
        assert balanced_plan.barrier_groups == STANDARD_BARRIER_GROUPS

    def test_filters_standard_structure_to_the_phases_present(self):
        plan = make_plan(phases=[make_phase(n) for n in (2, 4, 6, 8)])
        assert plan.rings == ((2, 4), (6, 8))
        assert plan.barrier_groups == ((2, 6), (4, 8))

    def test_drops_groups_left_empty_by_filtering(self):
        plan = make_plan(phases=[make_phase(n) for n in (2, 6)])
        assert plan.barrier_groups == ((2, 6),)

    def test_explicit_structure_is_preserved(self):
        plan = make_plan(rings=[[1, 2], [5, 6]], barrier_groups=[[1, 2, 5, 6]])
        assert plan.rings == ((1, 2), (5, 6))
        assert plan.barrier_groups == ((1, 2, 5, 6),)


class TestTimingPlanValidationOnConstruction:
    def test_rejects_an_empty_plan(self):
        with pytest.raises(PlanStructureError, match="at least one phase"):
            TimingPlan(name="empty", cycle_length_s=60.0, phases={})

    def test_rejects_a_phase_keyed_under_the_wrong_number(self):
        with pytest.raises(PlanStructureError, match="keyed as 3"):
            TimingPlan(
                name="mismatched",
                cycle_length_s=60.0,
                phases={3: make_phase(4)},
            )

    def test_rejects_rings_referencing_absent_phases(self):
        with pytest.raises(PlanStructureError, match="rings reference phases"):
            make_plan(phases=[make_phase(2)], rings=[[2], [6]])

    def test_rejects_barrier_groups_referencing_absent_phases(self):
        with pytest.raises(PlanStructureError, match="barrier groups reference"):
            make_plan(
                phases=[make_phase(2)],
                rings=[[2]],
                barrier_groups=[[2, 6]],
            )

    def test_rejects_coordinated_phases_absent_from_the_plan(self):
        with pytest.raises(PlanStructureError, match="coordinated phases"):
            make_plan(phases=[make_phase(2)], coordinated_phases=(2, 6))

    def test_rejects_duplicate_phase_numbers_when_loading(self):
        data = make_plan().to_dict()
        data["phases"].append(data["phases"][0])
        with pytest.raises(PlanStructureError, match="duplicate phase numbers"):
            TimingPlan.from_dict(data)


class TestTimingPlanQueries:
    def test_ring_and_group_lookup(self, balanced_plan):
        assert balanced_plan.ring_of(2) == 0
        assert balanced_plan.ring_of(6) == 1
        assert balanced_plan.barrier_group_of(2) == 0
        assert balanced_plan.barrier_group_of(4) == 1

    def test_lookup_returns_none_for_an_unassigned_phase(self):
        plan = make_plan(
            phases=[make_phase(n) for n in (1, 2)],
            rings=[[1], [2]],
            barrier_groups=[[1]],
            coordinated_phases=(),
        )
        assert plan.barrier_group_of(2) is None

    def test_phases_in_follows_ring_order(self, balanced_plan):
        assert [p.number for p in balanced_plan.phases_in(0, 0)] == [1, 2]
        assert [p.number for p in balanced_plan.phases_in(1, 1)] == [7, 8]

    def test_ring_split_sum_adds_the_group(self, balanced_plan):
        assert balanced_plan.ring_split_sum(0, 0) == pytest.approx(40.0)

    def test_phase_lookup_raises_for_an_unknown_number(self, balanced_plan):
        with pytest.raises(KeyError):
            balanced_plan.phase(99)

    def test_is_coordinated_requires_both_cycle_and_phases(self):
        assert make_plan().is_coordinated is True
        assert make_plan(cycle_length_s=0.0).is_coordinated is False
        assert make_plan(coordinated_phases=()).is_coordinated is False


class TestSerialization:
    def test_plan_round_trips_through_dict(self, balanced_plan):
        restored = TimingPlan.from_dict(balanced_plan.to_dict())
        assert restored.to_dict() == balanced_plan.to_dict()

    def test_metadata_survives_the_round_trip(self):
        plan = make_plan(metadata={"agency": "Example DOT"})
        assert TimingPlan.from_dict(plan.to_dict()).metadata == {
            "agency": "Example DOT"
        }
