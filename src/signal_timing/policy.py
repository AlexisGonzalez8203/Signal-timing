"""Agency-configurable thresholds used by the validation rules.

The defaults follow the MUTCD and common ITE practice. Agencies that adopt
stricter or looser local standards should construct a :class:`Policy` rather
than editing the rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from .intervals import (
    DEFAULT_DECELERATION_FPS2,
    DEFAULT_REACTION_TIME_S,
    DEFAULT_VEHICLE_LENGTH_FT,
    DEFAULT_WALKING_SPEED_FPS,
)


@dataclass(frozen=True)
class Policy:
    """Thresholds and modelling assumptions for validation.

    Attributes:
        yellow_min_s: Shortest permitted yellow change interval.
        yellow_max_s: Longest permitted yellow change interval.
        red_clearance_max_s: Longest permitted red clearance interval.
        min_green_floor_s: Shortest minimum green considered acceptable.
        walk_min_s: WALK interval the MUTCD directs as the normal minimum.
        walk_absolute_min_s: Shortest WALK permitted with engineering judgment.
        walking_speed_fps: Walking speed for the pedestrian change interval.
        reaction_time_s: Perception-reaction time for the yellow calculation.
        deceleration_fps2: Deceleration rate for the yellow calculation.
        vehicle_length_ft: Design vehicle length for red clearance.
        max_cycle_length_s: Longest cycle length considered reasonable.
        interval_tolerance_s: Slack allowed when comparing entered timing
            against a computed value before a finding is raised.
    """

    yellow_min_s: float = 3.0
    yellow_max_s: float = 6.0
    red_clearance_max_s: float = 6.0
    min_green_floor_s: float = 4.0
    walk_min_s: float = 7.0
    walk_absolute_min_s: float = 4.0
    walking_speed_fps: float = DEFAULT_WALKING_SPEED_FPS
    reaction_time_s: float = DEFAULT_REACTION_TIME_S
    deceleration_fps2: float = DEFAULT_DECELERATION_FPS2
    vehicle_length_ft: float = DEFAULT_VEHICLE_LENGTH_FT
    max_cycle_length_s: float = 240.0
    interval_tolerance_s: float = 0.05


#: Policy used when the caller does not supply one.
DEFAULT_POLICY = Policy()
