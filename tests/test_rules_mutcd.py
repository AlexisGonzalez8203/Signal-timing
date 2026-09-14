"""Tests for the MUTCD and ITE interval rules."""

from __future__ import annotations

import pytest

from conftest import make_phase, make_plan
from signal_timing.model import Approach
from signal_timing.policy import Policy
from signal_timing.rules.base import Severity
from signal_timing.rules.mutcd import (
    MinimumGreenFloor,
    PedestrianChangeIntervalAdequacy,
    RedClearanceAdequacy,
    RedClearanceIntervalRange,
    WalkIntervalMinimum,
    YellowChangeIntervalAdequacy,
    YellowChangeIntervalRange,
)


def findings_for(rule, *phases):
    """Run ``rule`` against a plan built from ``phases`` alone."""
    numbers = [p.number for p in phases]
    plan = make_plan(
        phases=list(phases),
        rings=[numbers],
        barrier_groups=[numbers],
        coordinated_phases=(),
        cycle_length_s=0.0,
    )
    return list(rule.check(plan))


class TestYellowChangeIntervalRange:
    rule = YellowChangeIntervalRange()

    def test_accepts_a_yellow_inside_the_range(self):
        assert findings_for(self.rule, make_phase(2, yellow_s=4.0)) == []

    @pytest.mark.parametrize("yellow", [3.0, 6.0])
    def test_bounds_are_inclusive(self, yellow):
        assert findings_for(self.rule, make_phase(2, yellow_s=yellow)) == []

    def test_flags_a_yellow_below_the_minimum(self):
        (finding,) = findings_for(self.rule, make_phase(2, yellow_s=2.5))
        assert finding.severity is Severity.ERROR
        assert finding.phase == 2
        assert finding.observed == 2.5
        assert finding.limit == 3.0

    def test_flags_a_yellow_above_the_maximum(self):
        (finding,) = findings_for(self.rule, make_phase(2, yellow_s=7.0))
        assert finding.severity is Severity.ERROR
        assert "above" in finding.message

    def test_ignores_a_phase_with_no_split(self):
        """An unused phase in the controller is not a timing violation."""
        assert findings_for(self.rule, make_phase(2, yellow_s=0.0, split_s=0.0)) == []

    def test_respects_a_stricter_policy(self):
        rule = YellowChangeIntervalRange(Policy(yellow_min_s=3.5))
        assert len(findings_for(rule, make_phase(2, yellow_s=3.2))) == 1


class TestRedClearanceIntervalRange:
    rule = RedClearanceIntervalRange()

    def test_accepts_a_red_clearance_inside_the_range(self):
        assert findings_for(self.rule, make_phase(2, red_clearance_s=2.0)) == []

    def test_accepts_zero_red_clearance(self):
        """Not every approach needs a red clearance interval."""
        assert findings_for(self.rule, make_phase(2, red_clearance_s=0.0)) == []

    def test_flags_red_clearance_above_the_maximum(self):
        (finding,) = findings_for(self.rule, make_phase(2, red_clearance_s=6.5))
        assert finding.severity is Severity.ERROR
        assert finding.limit == 6.0

    def test_flags_negative_red_clearance(self):
        (finding,) = findings_for(self.rule, make_phase(2, red_clearance_s=-1.0))
        assert finding.severity is Severity.ERROR
        assert "negative" in finding.message


class TestYellowChangeIntervalAdequacy:
    rule = YellowChangeIntervalAdequacy()

    def test_accepts_a_yellow_that_covers_the_requirement(self):
        phase = make_phase(2, yellow_s=4.5, approach=Approach(speed_mph=45.0))
        assert findings_for(self.rule, phase) == []

    def test_flags_a_yellow_short_for_the_approach_speed(self):
        phase = make_phase(2, yellow_s=3.5, approach=Approach(speed_mph=45.0))
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.ERROR
        assert finding.limit == pytest.approx(4.3, abs=0.01)

    def test_a_legal_yellow_can_still_be_inadequate(self):
        """3.0 s passes the MUTCD range check but not a 55 mph approach."""
        phase = make_phase(2, yellow_s=3.0, approach=Approach(speed_mph=55.0))
        assert findings_for(YellowChangeIntervalRange(), phase) == []
        assert len(findings_for(self.rule, phase)) == 1

    def test_downgrade_can_turn_an_adequate_yellow_inadequate(self):
        level = make_phase(2, yellow_s=4.35, approach=Approach(speed_mph=45.0))
        steep = make_phase(
            2, yellow_s=4.35, approach=Approach(speed_mph=45.0, grade=-0.06)
        )
        assert findings_for(self.rule, level) == []
        assert len(findings_for(self.rule, steep)) == 1

    def test_skips_a_phase_with_no_approach_data(self):
        assert findings_for(self.rule, make_phase(2, yellow_s=3.0)) == []

    def test_warns_rather_than_raises_on_an_uncomputable_grade(self):
        phase = make_phase(2, approach=Approach(speed_mph=45.0, grade=-0.40))
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.WARNING
        assert "could not be computed" in finding.message


class TestRedClearanceAdequacy:
    rule = RedClearanceAdequacy()

    def test_accepts_an_adequate_red_clearance(self):
        phase = make_phase(
            2,
            red_clearance_s=2.5,
            approach=Approach(speed_mph=30.0, clearance_distance_ft=70.0),
        )
        assert findings_for(self.rule, phase) == []

    def test_flags_a_short_red_clearance_as_a_warning(self):
        phase = make_phase(
            2,
            red_clearance_s=1.0,
            approach=Approach(speed_mph=30.0, clearance_distance_ft=70.0),
        )
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.WARNING
        assert finding.limit == pytest.approx(2.045, abs=0.01)

    def test_skips_an_approach_without_a_clearance_distance(self):
        phase = make_phase(2, red_clearance_s=0.0, approach=Approach(speed_mph=30.0))
        assert findings_for(self.rule, phase) == []


class TestWalkIntervalMinimum:
    rule = WalkIntervalMinimum()

    def test_accepts_the_normal_minimum(self):
        assert findings_for(self.rule, make_phase(2, walk_s=7.0)) == []

    def test_warns_between_the_absolute_and_normal_minimums(self):
        (finding,) = findings_for(self.rule, make_phase(2, walk_s=5.0))
        assert finding.severity is Severity.WARNING
        assert "engineering judgment" in finding.message

    def test_errors_below_the_absolute_minimum(self):
        (finding,) = findings_for(self.rule, make_phase(2, walk_s=3.0))
        assert finding.severity is Severity.ERROR

    def test_skips_a_phase_that_does_not_serve_pedestrians(self):
        assert findings_for(self.rule, make_phase(2)) == []


class TestPedestrianChangeIntervalAdequacy:
    rule = PedestrianChangeIntervalAdequacy()

    def test_accepts_an_adequate_change_interval(self):
        phase = make_phase(
            2,
            walk_s=7.0,
            ped_change_s=14.0,
            approach=Approach(speed_mph=30.0, crossing_distance_ft=48.0),
        )
        assert findings_for(self.rule, phase) == []

    def test_flags_a_short_change_interval(self):
        phase = make_phase(
            2,
            walk_s=7.0,
            ped_change_s=10.0,
            approach=Approach(speed_mph=30.0, crossing_distance_ft=48.0),
        )
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.ERROR
        assert finding.limit == pytest.approx(13.71, abs=0.01)

    def test_a_slower_walking_speed_demands_more_time(self):
        phase = make_phase(
            2,
            walk_s=7.0,
            ped_change_s=14.0,
            approach=Approach(speed_mph=30.0, crossing_distance_ft=48.0),
        )
        rule = PedestrianChangeIntervalAdequacy(Policy(walking_speed_fps=3.0))
        assert len(findings_for(rule, phase)) == 1

    def test_reports_info_when_the_crossing_distance_is_missing(self):
        phase = make_phase(2, walk_s=7.0, ped_change_s=14.0)
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.INFO
        assert "cannot be verified" in finding.message

    def test_skips_a_phase_that_does_not_serve_pedestrians(self):
        phase = make_phase(2, approach=Approach(speed_mph=30.0, crossing_distance_ft=48.0))
        assert findings_for(self.rule, phase) == []


class TestMinimumGreenFloor:
    rule = MinimumGreenFloor()

    def test_accepts_a_minimum_green_at_the_floor(self):
        assert findings_for(self.rule, make_phase(2, min_green_s=4.0)) == []

    def test_warns_below_the_floor(self):
        (finding,) = findings_for(self.rule, make_phase(2, min_green_s=2.0))
        assert finding.severity is Severity.WARNING
        assert finding.limit == 4.0

    def test_ignores_an_unused_phase(self):
        assert findings_for(self.rule, make_phase(2, min_green_s=0.0, split_s=0.0)) == []
