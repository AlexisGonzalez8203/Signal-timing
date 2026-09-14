"""Tests for unit conversions."""

from __future__ import annotations

import pytest

from signal_timing.units import (
    feet_to_meters,
    fps_to_mph,
    kph_to_mph,
    meters_to_feet,
    mph_to_fps,
)


def test_one_mph_is_the_standard_number_of_fps():
    # 5280 ft/mi divided by 3600 s/h
    assert mph_to_fps(1.0) == pytest.approx(5280 / 3600)


def test_thirty_mph_is_forty_four_fps():
    assert mph_to_fps(30.0) == pytest.approx(44.0)


@pytest.mark.parametrize("mph", [0.0, 25.0, 45.0, 70.0])
def test_speed_conversion_round_trips(mph):
    assert fps_to_mph(mph_to_fps(mph)) == pytest.approx(mph)


@pytest.mark.parametrize("feet", [0.0, 12.0, 48.0, 100.0])
def test_length_conversion_round_trips(feet):
    assert meters_to_feet(feet_to_meters(feet)) == pytest.approx(feet)


def test_one_meter_is_about_three_and_a_quarter_feet():
    assert meters_to_feet(1.0) == pytest.approx(3.2808, abs=0.001)


def test_fifty_kph_is_about_thirty_one_mph():
    assert kph_to_mph(50.0) == pytest.approx(31.07, abs=0.01)
