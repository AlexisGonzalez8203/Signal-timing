"""Unit conversions for signal timing calculations.

Calculations follow US customary units, matching the MUTCD and the ITE
change-and-clearance-interval formulas: speeds in mph, distances in feet,
accelerations in ft/s^2, times in seconds.
"""

from __future__ import annotations

#: Feet per second in one mile per hour (5280 ft / 3600 s).
FPS_PER_MPH = 1.46666666666666666667

#: Standard gravitational acceleration, ft/s^2.
GRAVITY_FPS2 = 32.2

#: Feet in one meter.
FEET_PER_METER = 3.280839895013123


def mph_to_fps(mph: float) -> float:
    """Convert miles per hour to feet per second."""
    return mph * FPS_PER_MPH


def fps_to_mph(fps: float) -> float:
    """Convert feet per second to miles per hour."""
    return fps / FPS_PER_MPH


def meters_to_feet(meters: float) -> float:
    """Convert meters to feet."""
    return meters * FEET_PER_METER


def feet_to_meters(feet: float) -> float:
    """Convert feet to meters."""
    return feet / FEET_PER_METER


def kph_to_mph(kph: float) -> float:
    """Convert kilometers per hour to miles per hour."""
    return kph * 0.621371192237334
