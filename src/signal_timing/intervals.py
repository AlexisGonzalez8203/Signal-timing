"""Change, clearance, and pedestrian interval calculations.

Vehicle intervals use the ITE kinematic equations that underpin most agency
timing policy. Pedestrian intervals use the MUTCD walking-speed model.

These functions compute *recommended* values. They do not clamp results to
regulatory bounds -- that is the job of the rules in :mod:`signal_timing.rules`,
so that a computed value falling outside MUTCD limits surfaces as a finding
rather than being silently hidden.
"""

from __future__ import annotations

from .units import GRAVITY_FPS2, mph_to_fps

#: Default perception-reaction time, seconds (ITE).
DEFAULT_REACTION_TIME_S = 1.0

#: Default comfortable deceleration rate, ft/s^2 (ITE).
DEFAULT_DECELERATION_FPS2 = 10.0

#: Default design vehicle length, feet (ITE).
DEFAULT_VEHICLE_LENGTH_FT = 20.0

#: Default pedestrian walking speed, ft/s (MUTCD).
DEFAULT_WALKING_SPEED_FPS = 3.5

#: Default pedestrian start-up / perception time, seconds.
DEFAULT_PEDESTRIAN_STARTUP_S = 0.0


class IntervalInputError(ValueError):
    """Raised when interval inputs are outside the domain the formulas model."""


def yellow_change_interval(
    approach_speed_mph: float,
    grade: float = 0.0,
    reaction_time_s: float = DEFAULT_REACTION_TIME_S,
    deceleration_fps2: float = DEFAULT_DECELERATION_FPS2,
) -> float:
    """Return the ITE yellow change interval in seconds.

        Y = t + V / (2a + 2gG)

    where V is the approach speed in ft/s, t the perception-reaction time,
    a the deceleration rate, g gravitational acceleration, and G the approach
    grade as a decimal.

    Args:
        approach_speed_mph: Approach speed (85th-percentile or posted), mph.
        grade: Approach grade as a decimal. Positive for an upgrade, negative
            for a downgrade -- a downgrade lengthens the interval.
        reaction_time_s: Perception-reaction time, seconds.
        deceleration_fps2: Comfortable deceleration rate, ft/s^2.

    Raises:
        IntervalInputError: If the speed or deceleration is non-positive, or if
            the grade is steep enough downhill to drive the denominator to zero
            (the kinematic model breaks down there).
    """
    if approach_speed_mph <= 0:
        raise IntervalInputError("approach_speed_mph must be positive")
    if deceleration_fps2 <= 0:
        raise IntervalInputError("deceleration_fps2 must be positive")
    if reaction_time_s < 0:
        raise IntervalInputError("reaction_time_s must not be negative")

    denominator = 2 * deceleration_fps2 + 2 * GRAVITY_FPS2 * grade
    if denominator <= 0:
        raise IntervalInputError(
            f"grade {grade:+.3f} is too steep a downgrade for the assumed "
            f"deceleration of {deceleration_fps2} ft/s^2; the ITE model yields "
            "a non-positive denominator"
        )

    return reaction_time_s + mph_to_fps(approach_speed_mph) / denominator


def red_clearance_interval(
    clearance_distance_ft: float,
    approach_speed_mph: float,
    vehicle_length_ft: float = DEFAULT_VEHICLE_LENGTH_FT,
) -> float:
    """Return the ITE red clearance interval in seconds.

        R = (W + L) / V

    Args:
        clearance_distance_ft: Distance W from the stop line to the far edge of
            the conflicting traffic path, feet.
        approach_speed_mph: Approach speed, mph.
        vehicle_length_ft: Design vehicle length L, feet.

    Raises:
        IntervalInputError: If any input is non-positive (distance may be zero).
    """
    if approach_speed_mph <= 0:
        raise IntervalInputError("approach_speed_mph must be positive")
    if clearance_distance_ft < 0:
        raise IntervalInputError("clearance_distance_ft must not be negative")
    if vehicle_length_ft < 0:
        raise IntervalInputError("vehicle_length_ft must not be negative")

    return (clearance_distance_ft + vehicle_length_ft) / mph_to_fps(approach_speed_mph)


def pedestrian_change_interval(
    crossing_distance_ft: float,
    walking_speed_fps: float = DEFAULT_WALKING_SPEED_FPS,
) -> float:
    """Return the pedestrian change interval (flashing UPRAISED HAND), seconds.

    The MUTCD measures the crossing distance from the near curb -- or from the
    edge of a median island wide enough to serve as a refuge -- to the far side
    of the travelled way, at a default walking speed of 3.5 ft/s.

    Raises:
        IntervalInputError: If the distance is non-positive or the speed is
            non-positive.
    """
    if crossing_distance_ft <= 0:
        raise IntervalInputError("crossing_distance_ft must be positive")
    if walking_speed_fps <= 0:
        raise IntervalInputError("walking_speed_fps must be positive")

    return crossing_distance_ft / walking_speed_fps


def total_pedestrian_time(
    walk_interval_s: float,
    crossing_distance_ft: float,
    walking_speed_fps: float = DEFAULT_WALKING_SPEED_FPS,
) -> float:
    """Return total pedestrian service time: WALK plus the change interval."""
    if walk_interval_s < 0:
        raise IntervalInputError("walk_interval_s must not be negative")
    return walk_interval_s + pedestrian_change_interval(
        crossing_distance_ft, walking_speed_fps
    )
