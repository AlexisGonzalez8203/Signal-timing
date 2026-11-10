"""FDOT Traffic Engineering Manual (TEM) rules and input-completeness checks.

The generic MUTCD/ITE rules answer "is this plan reasonable anywhere?". On the
Florida State Highway System the TEM is stricter: the yellow table minimums are
binding, red clearance is mandatory, and the 3-6 s and 2-6 s ranges are
requirements rather than guidance. This module encodes those rules, plus a
completeness rule that reports every check that could not run because an input
was missing -- so a plan never passes simply because nothing was checked.

Citations follow the FDOT TEM (Topic No. 750-000-005) and MUTCD 11th Edition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator

from ..model import TimingPlan
from ..policy import DEFAULT_POLICY, Policy
from ..units import GRAVITY_FPS2
from .base import Finding, Severity

TEM_YELLOW = "FDOT TEM 3.6.2.1 -- Yellow change interval (Formula 3.6-1, Table 3.6-1)"
TEM_RED = "FDOT TEM 3.6.2.2 -- Red clearance interval (Formula 3.6-2)"
MUTCD_PED = "MUTCD 11th Ed. 4I.06 -- Pedestrian intervals"
MUTCD_COUNTDOWN = "MUTCD 11th Ed. 4I.04 -- Pedestrian countdown"

#: TEM Table 3.6-1: minimum yellow (s) at 0% grade by posted speed (mph).
TEM_YELLOW_TABLE: dict[int, float] = {
    25: 3.4, 30: 3.7, 35: 4.0, 40: 4.4, 45: 4.8, 50: 5.1, 55: 5.5, 60: 5.9, 65: 6.0,
}

TEM_REACTION_TIME_S = 1.4
TEM_DECELERATION_FPS2 = 10.0
TEM_VEHICLE_LENGTH_FT = 20.0
TEM_YELLOW_MIN_S = 3.0
TEM_YELLOW_MAX_S = 6.0
TEM_RED_MIN_S = 2.0
TEM_RED_MAX_S = 6.0
#: NCHRP 731 allows reducing the computed red clearance by up to this much.
TEM_RED_REDUCTION_S = 1.0
TEM_COUNTDOWN_THRESHOLD_S = 7.0
MUTCD_DETECTOR_OFFSET_FT = 6.0
MUTCD_MIN_WALK_SPEED_FPS = 3.0


def round_up_tenth(value: float) -> float:
    """Round ``value`` up to the next 0.1 s, ignoring float noise."""
    return math.ceil(round(value * 10, 6)) / 10


def tem_yellow_formula(speed_mph: float, grade: float = 0.0) -> float:
    """TEM Formula 3.6-1: Y = t + 1.47 v / (2 (a + G g)), unrounded."""
    denominator = 2 * (TEM_DECELERATION_FPS2 + grade * GRAVITY_FPS2)
    if denominator <= 0:
        raise ValueError(f"grade {grade:+.3f} is too steep a downgrade for the model")
    return TEM_REACTION_TIME_S + 1.47 * speed_mph / denominator


def tem_required_yellow(speed_mph: float, grade: float = 0.0) -> float:
    """Minimum TEM yellow: formula rounded up, never below Table 3.6-1 at 0% grade, capped at 6.0 s.

    The table applies at 0% grade only; other grades use the formula (and the
    3.0 s floor). Speeds not in the table use the formula.
    """
    required = round_up_tenth(tem_yellow_formula(speed_mph, grade))
    table = TEM_YELLOW_TABLE.get(int(speed_mph)) if float(speed_mph).is_integer() else None
    if table is not None and abs(grade) < 1e-9:
        required = max(required, table)
    # The 3-6 s range is binding on the SHS, so the requirement is capped at 6.0 s
    # (the formula gives 6.2 s at 65 mph; the table and the cap both say 6.0 s).
    return min(max(required, TEM_YELLOW_MIN_S), TEM_YELLOW_MAX_S)


def tem_required_red(clearance_distance_ft: float, speed_mph: float) -> float:
    """TEM Formula 3.6-2: R = (W + L) / (1.47 v), rounded up, unclamped."""
    return round_up_tenth(
        (clearance_distance_ft + TEM_VEHICLE_LENGTH_FT) / (1.47 * speed_mph)
    )


@dataclass
class TemYellow:
    """Yellow must meet the TEM formula/table minimum and the 3-6 s range."""

    policy: Policy = DEFAULT_POLICY
    id: str = "FDOT-Y-TEM"
    description: str = "Yellow meets TEM Formula 3.6-1 / Table 3.6-1 and 3-6 s range"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        tol = self.policy.interval_tolerance_s
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            if phase.yellow_s > TEM_YELLOW_MAX_S + tol:
                yield Finding(
                    self.id, Severity.ERROR,
                    f"Phase {number} yellow is {phase.yellow_s:.1f} s, above the "
                    f"{TEM_YELLOW_MAX_S:.1f} s TEM maximum.",
                    number, phase.yellow_s, TEM_YELLOW_MAX_S, TEM_YELLOW,
                )
            approach = phase.approach
            if approach is None:
                if phase.yellow_s + tol < TEM_YELLOW_MIN_S:
                    yield Finding(
                        self.id, Severity.ERROR,
                        f"Phase {number} yellow is {phase.yellow_s:.1f} s, below "
                        f"the {TEM_YELLOW_MIN_S:.1f} s TEM minimum.",
                        number, phase.yellow_s, TEM_YELLOW_MIN_S, TEM_YELLOW,
                    )
                continue
            try:
                required = tem_required_yellow(approach.speed_mph, approach.grade)
            except ValueError as exc:
                yield Finding(
                    self.id, Severity.WARNING,
                    f"Phase {number} TEM yellow could not be computed: {exc}",
                    number, reference=TEM_YELLOW,
                )
                continue
            if phase.yellow_s + tol < required:
                yield Finding(
                    self.id, Severity.ERROR,
                    f"Phase {number} yellow is {phase.yellow_s:.1f} s but the TEM "
                    f"minimum is {required:.1f} s at {approach.speed_mph:.0f} mph "
                    f"on a {approach.grade:+.1%} grade (t = {TEM_REACTION_TIME_S} s, "
                    f"a = {TEM_DECELERATION_FPS2:.0f} ft/s^2, posted speed).",
                    number, phase.yellow_s, required, TEM_YELLOW,
                )


@dataclass
class TemRedClearance:
    """Red clearance is mandatory (2-6 s) and must cover Formula 3.6-2."""

    policy: Policy = DEFAULT_POLICY
    id: str = "FDOT-R-TEM"
    description: str = "Red clearance present, within 2-6 s, and covers Formula 3.6-2"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        tol = self.policy.interval_tolerance_s
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            red = phase.red_clearance_s
            if red + tol < TEM_RED_MIN_S:
                yield Finding(
                    self.id, Severity.ERROR,
                    f"Phase {number} red clearance is {red:.1f} s, below the "
                    f"{TEM_RED_MIN_S:.1f} s TEM minimum (red clearance is mandatory).",
                    number, red, TEM_RED_MIN_S, TEM_RED,
                )
            elif red > TEM_RED_MAX_S + tol:
                yield Finding(
                    self.id, Severity.ERROR,
                    f"Phase {number} red clearance is {red:.1f} s, above the "
                    f"{TEM_RED_MAX_S:.1f} s TEM maximum.",
                    number, red, TEM_RED_MAX_S, TEM_RED,
                )
            approach = phase.approach
            if approach is None or approach.clearance_distance_ft is None:
                continue
            required = tem_required_red(approach.clearance_distance_ft, approach.speed_mph)
            if red + tol >= required:
                continue
            floor = max(required - TEM_RED_REDUCTION_S, TEM_RED_MIN_S)
            if red + tol < floor:
                severity, note = Severity.ERROR, ""
            else:
                severity = Severity.WARNING
                note = (
                    " This is within the 1.0 s reduction NCHRP 731 allows, which "
                    "needs documented engineering judgment."
                )
            yield Finding(
                self.id, severity,
                f"Phase {number} red clearance is {red:.1f} s but Formula 3.6-2 "
                f"gives {required:.1f} s to clear {approach.clearance_distance_ft:.0f} "
                f"ft at {approach.speed_mph:.0f} mph (L = {TEM_VEHICLE_LENGTH_FT:.0f} ft)."
                + note,
                number, red, required, TEM_RED,
            )


@dataclass
class PedestrianReach:
    """WALK + change must let a pedestrian from the detector reach the far side.

    MUTCD 4I.06 (Guidance): Walk + clearance >= time to walk from the detector
    (or 6 ft behind the curb) to the far side at 3.0 ft/s.
    """

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-PED-REACH"
    description: str = "WALK plus change covers detector-to-far-side at 3.0 ft/s"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            approach = phase.approach
            if (
                not phase.serves_pedestrians
                or approach is None
                or approach.crossing_distance_ft is None
            ):
                continue
            required = (
                approach.crossing_distance_ft + MUTCD_DETECTOR_OFFSET_FT
            ) / MUTCD_MIN_WALK_SPEED_FPS
            entered = phase.total_pedestrian_s or 0.0
            if entered + self.policy.interval_tolerance_s < required:
                yield Finding(
                    self.id, Severity.WARNING,
                    f"Phase {number} WALK + change is {entered:.1f} s but "
                    f"{required:.1f} s is needed to cross "
                    f"{approach.crossing_distance_ft:.0f} ft from the detector at "
                    f"{MUTCD_MIN_WALK_SPEED_FPS:.1f} ft/s; add the shortfall to WALK.",
                    number, entered, round(required, 2), MUTCD_PED,
                )


@dataclass
class PedestrianCountdown:
    """Flag phases whose change interval makes a countdown display required."""

    policy: Policy = DEFAULT_POLICY
    id: str = "MUTCD-PED-COUNTDOWN"
    description: str = "Countdown required when the change interval exceeds 7 s"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if not phase.serves_pedestrians or phase.ped_change_s is None:
                continue
            if phase.ped_change_s > TEM_COUNTDOWN_THRESHOLD_S:
                yield Finding(
                    self.id, Severity.INFO,
                    f"Phase {number} pedestrian change is {phase.ped_change_s:.1f} s "
                    f"(> {TEM_COUNTDOWN_THRESHOLD_S:.0f} s): a pedestrian countdown "
                    "display is required. Confirm one is provided.",
                    number, phase.ped_change_s, TEM_COUNTDOWN_THRESHOLD_S,
                    MUTCD_COUNTDOWN,
                )


@dataclass
class InputCompleteness:
    """Report every adequacy check that was skipped for lack of input.

    A plan that is silently unchecked looks the same as a plan that passed.
    This rule makes each gap explicit so it can be filled or accepted.
    """

    policy: Policy = DEFAULT_POLICY
    id: str = "COMPLETE-INPUTS"
    description: str = "Every adequacy check had the inputs it needs"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            approach = phase.approach
            if approach is None:
                yield Finding(
                    self.id, Severity.WARNING,
                    f"Phase {number} has no approach data: yellow and red "
                    "clearance adequacy were NOT verified. Provide speed_mph "
                    "(posted), grade and clearance_distance_ft.",
                    number, reference=TEM_YELLOW,
                )
                continue
            if approach.grade_assumed:
                yield Finding(
                    self.id, Severity.WARNING,
                    f"Phase {number} has no grade; 0% was assumed. Yellow changes "
                    "with grade (Formula 3.6-1), and the table minimum applies at 0% only.",
                    number, reference=TEM_YELLOW,
                )
            if approach.clearance_distance_ft is None:
                yield Finding(
                    self.id, Severity.WARNING,
                    f"Phase {number} has no clearance_distance_ft: red clearance "
                    "adequacy (Formula 3.6-2) was NOT verified.",
                    number, reference=TEM_RED,
                )
            if phase.serves_pedestrians:
                if approach.crossing_distance_ft is None:
                    yield Finding(
                        self.id, Severity.WARNING,
                        f"Phase {number} serves pedestrians but has no "
                        "crossing_distance_ft: change interval and reach were NOT verified.",
                        number, reference=MUTCD_PED,
                    )
                if phase.walk_s is None or phase.ped_change_s is None:
                    yield Finding(
                        self.id, Severity.WARNING,
                        f"Phase {number} serves pedestrians but walk_s or "
                        "ped_change_s is missing, so WALK minimums and reach are incomplete.",
                        number, reference=MUTCD_PED,
                    )


def fdot_rules(policy: Policy = DEFAULT_POLICY) -> list:
    """Return the FDOT TEM rules and the completeness rule."""
    return [
        TemYellow(policy),
        TemRedClearance(policy),
        PedestrianReach(policy),
        PedestrianCountdown(policy),
        InputCompleteness(policy),
    ]
