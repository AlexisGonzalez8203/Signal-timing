"""Tests for the ITE and MUTCD interval formulas."""

from __future__ import annotations

import pytest

from signal_timing.intervals import (
    IntervalInputError,
    pedestrian_change_interval,
    red_clearance_interval,
    total_pedestrian_time,
    yellow_change_interval,
)


class TestYellowChangeInterval:
    @pytest.mark.parametrize(
        "speed_mph, expected",
        [
            (25.0, 2.833),
            (30.0, 3.200),
            (35.0, 3.567),
            (45.0, 4.300),
            (55.0, 5.033),
        ],
    )
    def test_matches_published_values_on_level_grade(self, speed_mph, expected):
        assert yellow_change_interval(speed_mph) == pytest.approx(expected, abs=0.005)

    def test_downgrade_lengthens_the_interval(self):
        level = yellow_change_interval(45.0, grade=0.0)
        downhill = yellow_change_interval(45.0, grade=-0.04)
        assert downhill > level

    def test_upgrade_shortens_the_interval(self):
        level = yellow_change_interval(45.0, grade=0.0)
        uphill = yellow_change_interval(45.0, grade=0.04)
        assert uphill < level

    def test_grade_is_symmetric_about_level(self):
        """A given grade magnitude moves the denominator, not the reaction term."""
        up = yellow_change_interval(45.0, grade=0.05) - 1.0
        down = yellow_change_interval(45.0, grade=-0.05) - 1.0
        level = yellow_change_interval(45.0, grade=0.0) - 1.0
        assert up < level < down

    def test_higher_speed_lengthens_the_interval(self):
        assert yellow_change_interval(55.0) > yellow_change_interval(35.0)

    def test_reaction_time_is_additive(self):
        base = yellow_change_interval(40.0, reaction_time_s=0.0)
        assert yellow_change_interval(40.0, reaction_time_s=1.5) == pytest.approx(
            base + 1.5
        )

    @pytest.mark.parametrize("speed", [0.0, -10.0])
    def test_rejects_non_positive_speed(self, speed):
        with pytest.raises(IntervalInputError, match="approach_speed_mph"):
            yellow_change_interval(speed)

    def test_rejects_non_positive_deceleration(self):
        with pytest.raises(IntervalInputError, match="deceleration"):
            yellow_change_interval(45.0, deceleration_fps2=0.0)

    def test_rejects_negative_reaction_time(self):
        with pytest.raises(IntervalInputError, match="reaction_time_s"):
            yellow_change_interval(45.0, reaction_time_s=-1.0)

    def test_rejects_grade_that_zeroes_the_denominator(self):
        """At a steep enough downgrade the kinematic model breaks down."""
        with pytest.raises(IntervalInputError, match="too steep"):
            yellow_change_interval(45.0, grade=-0.35)


class TestRedClearanceInterval:
    def test_known_value(self):
        # (60 ft + 20 ft) / (45 mph * 1.467 ft/s/mph) = 1.212 s
        assert red_clearance_interval(60.0, 45.0) == pytest.approx(1.212, abs=0.005)

    def test_wider_intersection_lengthens_the_interval(self):
        assert red_clearance_interval(90.0, 30.0) > red_clearance_interval(50.0, 30.0)

    def test_higher_speed_shortens_the_interval(self):
        assert red_clearance_interval(70.0, 45.0) < red_clearance_interval(70.0, 25.0)

    def test_vehicle_length_is_included(self):
        with_vehicle = red_clearance_interval(60.0, 30.0, vehicle_length_ft=20.0)
        without = red_clearance_interval(60.0, 30.0, vehicle_length_ft=0.0)
        assert with_vehicle > without

    def test_zero_distance_is_allowed(self):
        assert red_clearance_interval(0.0, 30.0) > 0

    def test_rejects_negative_distance(self):
        with pytest.raises(IntervalInputError, match="clearance_distance_ft"):
            red_clearance_interval(-5.0, 30.0)

    def test_rejects_non_positive_speed(self):
        with pytest.raises(IntervalInputError, match="approach_speed_mph"):
            red_clearance_interval(60.0, 0.0)


class TestPedestrianIntervals:
    def test_change_interval_at_default_walking_speed(self):
        assert pedestrian_change_interval(48.0) == pytest.approx(48.0 / 3.5)

    def test_slower_walking_speed_lengthens_the_interval(self):
        assert pedestrian_change_interval(48.0, 3.0) > pedestrian_change_interval(48.0)

    def test_total_time_adds_the_walk_interval(self):
        assert total_pedestrian_time(7.0, 48.0) == pytest.approx(
            7.0 + pedestrian_change_interval(48.0)
        )

    def test_rejects_non_positive_crossing_distance(self):
        with pytest.raises(IntervalInputError, match="crossing_distance_ft"):
            pedestrian_change_interval(0.0)

    def test_rejects_non_positive_walking_speed(self):
        with pytest.raises(IntervalInputError, match="walking_speed_fps"):
            pedestrian_change_interval(48.0, 0.0)

    def test_rejects_negative_walk_interval(self):
        with pytest.raises(IntervalInputError, match="walk_interval_s"):
            total_pedestrian_time(-1.0, 48.0)
