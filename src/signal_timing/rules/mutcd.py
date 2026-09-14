"""Rules enforcing MUTCD interval requirements and ITE-derived adequacy checks.

Two distinct questions are asked of each interval. First, is the entered value
inside the range the MUTCD permits? Second, is it long enough for the geometry
and speed of the approach it serves? A yellow of 3.0 s is legal everywhere but
badly short on a 55 mph approach, so both checks are needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..intervals import (
    IntervalInputError,
    pedestrian_change_interval,
    red_clearance_interval,
    yellow_change_interval,
)
from ..model import TimingPlan
from ..policy import DEFAULT_POLICY, Policy
from .base import Finding, Severity

MUTCD_CHANGE_CLEARANCE = "MUTCD Ch. 4 -- Yellow Change and Red Clearance Intervals"
MUTCD_PEDESTRIAN = "MUTCD Ch. 4 -- Pedestrian Intervals and Signal Phases"
ITE_HANDBOOK = "ITE Traffic Control Devices Handbook -- change and clearance intervals"


@dataclass
class YellowChangeIntervalRange:
    """Yellow change interval must fall within the MUTCD range."""

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-Y-RANGE"
    description: str = "Yellow change interval within the permitted range"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            if phase.yellow_s < self.policy.yellow_min_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} yellow is {phase.yellow_s:.1f} s, below "
                        f"the {self.policy.yellow_min_s:.1f} s minimum."
                    ),
                    phase=number,
                    observed=phase.yellow_s,
                    limit=self.policy.yellow_min_s,
                    reference=MUTCD_CHANGE_CLEARANCE,
                )
            elif phase.yellow_s > self.policy.yellow_max_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} yellow is {phase.yellow_s:.1f} s, above "
                        f"the {self.policy.yellow_max_s:.1f} s maximum."
                    ),
                    phase=number,
                    observed=phase.yellow_s,
                    limit=self.policy.yellow_max_s,
                    reference=MUTCD_CHANGE_CLEARANCE,
                )


@dataclass
class RedClearanceIntervalRange:
    """Red clearance interval must not exceed the MUTCD maximum."""

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-R-RANGE"
    description: str = "Red clearance interval within the permitted range"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.red_clearance_s < 0:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} red clearance is negative "
                        f"({phase.red_clearance_s:.1f} s)."
                    ),
                    phase=number,
                    observed=phase.red_clearance_s,
                    limit=0.0,
                    reference=MUTCD_CHANGE_CLEARANCE,
                )
            elif phase.red_clearance_s > self.policy.red_clearance_max_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} red clearance is "
                        f"{phase.red_clearance_s:.1f} s, above the "
                        f"{self.policy.red_clearance_max_s:.1f} s maximum."
                    ),
                    phase=number,
                    observed=phase.red_clearance_s,
                    limit=self.policy.red_clearance_max_s,
                    reference=MUTCD_CHANGE_CLEARANCE,
                )


@dataclass
class YellowChangeIntervalAdequacy:
    """Entered yellow should cover the ITE kinematic requirement."""

    policy: Policy = DEFAULT_POLICY
    id: str = "ITE-Y-ADEQUACY"
    description: str = "Yellow change interval adequate for approach speed and grade"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.approach is None:
                continue
            try:
                required = yellow_change_interval(
                    phase.approach.speed_mph,
                    phase.approach.grade,
                    self.policy.reaction_time_s,
                    self.policy.deceleration_fps2,
                )
            except IntervalInputError as exc:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=f"Phase {number} yellow could not be computed: {exc}",
                    phase=number,
                    reference=ITE_HANDBOOK,
                )
                continue

            if phase.yellow_s + self.policy.interval_tolerance_s < required:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} yellow is {phase.yellow_s:.1f} s but "
                        f"{required:.1f} s is required at "
                        f"{phase.approach.speed_mph:.0f} mph on a "
                        f"{phase.approach.grade:+.1%} grade."
                    ),
                    phase=number,
                    observed=phase.yellow_s,
                    limit=round(required, 2),
                    reference=ITE_HANDBOOK,
                )


@dataclass
class RedClearanceAdequacy:
    """Entered red clearance should cover the ITE clearance requirement."""

    policy: Policy = DEFAULT_POLICY
    id: str = "ITE-R-ADEQUACY"
    description: str = "Red clearance adequate to clear the conflict area"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            approach = phase.approach
            if approach is None or approach.clearance_distance_ft is None:
                continue
            try:
                required = red_clearance_interval(
                    approach.clearance_distance_ft,
                    approach.speed_mph,
                    self.policy.vehicle_length_ft,
                )
            except IntervalInputError as exc:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Phase {number} red clearance could not be computed: {exc}"
                    ),
                    phase=number,
                    reference=ITE_HANDBOOK,
                )
                continue

            if phase.red_clearance_s + self.policy.interval_tolerance_s < required:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Phase {number} red clearance is "
                        f"{phase.red_clearance_s:.1f} s but {required:.1f} s is "
                        f"needed to clear {approach.clearance_distance_ft:.0f} ft "
                        f"at {approach.speed_mph:.0f} mph."
                    ),
                    phase=number,
                    observed=phase.red_clearance_s,
                    limit=round(required, 2),
                    reference=ITE_HANDBOOK,
                )


@dataclass
class WalkIntervalMinimum:
    """WALK interval must meet the MUTCD minimum where pedestrians are served."""

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-WALK-MIN"
    description: str = "WALK interval meets the minimum duration"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if not phase.serves_pedestrians or phase.walk_s is None:
                continue
            if phase.walk_s < self.policy.walk_absolute_min_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} WALK is {phase.walk_s:.1f} s, below the "
                        f"{self.policy.walk_absolute_min_s:.1f} s absolute minimum."
                    ),
                    phase=number,
                    observed=phase.walk_s,
                    limit=self.policy.walk_absolute_min_s,
                    reference=MUTCD_PEDESTRIAN,
                )
            elif phase.walk_s < self.policy.walk_min_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Phase {number} WALK is {phase.walk_s:.1f} s, below the "
                        f"{self.policy.walk_min_s:.1f} s normal minimum; this "
                        "requires documented engineering judgment."
                    ),
                    phase=number,
                    observed=phase.walk_s,
                    limit=self.policy.walk_min_s,
                    reference=MUTCD_PEDESTRIAN,
                )


@dataclass
class PedestrianChangeIntervalAdequacy:
    """Pedestrian change interval must cover the crossing at the design speed."""

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-PCI-ADEQUACY"
    description: str = "Pedestrian change interval covers the crossing distance"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            approach = phase.approach
            if not phase.serves_pedestrians:
                continue
            if approach is None or approach.crossing_distance_ft is None:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.INFO,
                    message=(
                        f"Phase {number} serves pedestrians but has no crossing "
                        "distance, so its change interval cannot be verified."
                    ),
                    phase=number,
                    reference=MUTCD_PEDESTRIAN,
                )
                continue

            try:
                required = pedestrian_change_interval(
                    approach.crossing_distance_ft, self.policy.walking_speed_fps
                )
            except IntervalInputError as exc:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Phase {number} pedestrian change interval could not be "
                        f"computed: {exc}"
                    ),
                    phase=number,
                    reference=MUTCD_PEDESTRIAN,
                )
                continue

            entered = phase.ped_change_s or 0.0
            if entered + self.policy.interval_tolerance_s < required:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} pedestrian change interval is "
                        f"{entered:.1f} s but {required:.1f} s is required to "
                        f"cross {approach.crossing_distance_ft:.0f} ft at "
                        f"{self.policy.walking_speed_fps:.1f} ft/s."
                    ),
                    phase=number,
                    observed=entered,
                    limit=round(required, 2),
                    reference=MUTCD_PEDESTRIAN,
                )


@dataclass
class MinimumGreenFloor:
    """Minimum green should not fall below the policy floor."""

    policy: Policy = DEFAULT_POLICY
    id: str = "ITE-MIN-GREEN"
    description: str = "Minimum green meets the policy floor"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            if phase.min_green_s < self.policy.min_green_floor_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Phase {number} minimum green is {phase.min_green_s:.1f} s, "
                        f"below the {self.policy.min_green_floor_s:.1f} s floor."
                    ),
                    phase=number,
                    observed=phase.min_green_s,
                    limit=self.policy.min_green_floor_s,
                    reference=ITE_HANDBOOK,
                )


def mutcd_rules(policy: Policy = DEFAULT_POLICY) -> list:
    """Return every MUTCD/ITE interval rule, bound to ``policy``."""
    return [
        YellowChangeIntervalRange(policy),
        RedClearanceIntervalRange(policy),
        YellowChangeIntervalAdequacy(policy),
        RedClearanceAdequacy(policy),
        WalkIntervalMinimum(policy),
        PedestrianChangeIntervalAdequacy(policy),
        MinimumGreenFloor(policy),
    ]
