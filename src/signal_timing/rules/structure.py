"""Rules checking that a plan is internally consistent and runnable.

These are arithmetic rather than regulatory. A plan that fails them describes
timing no controller can serve as entered -- splits that cannot cover their own
clearance intervals, rings that do not reach the barrier together, or a cycle
length that disagrees with the splits that compose it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..model import TimingPlan
from ..policy import DEFAULT_POLICY, Policy
from .base import Finding, Severity, approximately_equal

NEMA_REFERENCE = "NEMA TS 2 -- ring, barrier, and concurrency structure"


@dataclass
class PhaseAssignmentComplete:
    """Every phase belongs to exactly one ring and one barrier group."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-ASSIGNMENT"
    description: str = "Each phase is assigned to one ring and one barrier group"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            rings = [i for i, r in enumerate(plan.rings) if number in r]
            groups = [i for i, g in enumerate(plan.barrier_groups) if number in g]

            if not rings:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=f"Phase {number} is not assigned to any ring.",
                    phase=number,
                    reference=NEMA_REFERENCE,
                )
            elif len(rings) > 1:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} appears in multiple rings "
                        f"({', '.join(str(i + 1) for i in rings)})."
                    ),
                    phase=number,
                    reference=NEMA_REFERENCE,
                )

            if not groups:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=f"Phase {number} is not assigned to any barrier group.",
                    phase=number,
                    reference=NEMA_REFERENCE,
                )
            elif len(groups) > 1:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} appears in multiple barrier groups "
                        f"({', '.join(str(i + 1) for i in groups)})."
                    ),
                    phase=number,
                    reference=NEMA_REFERENCE,
                )


@dataclass
class SplitCoversClearance:
    """A split must at least cover the phase's own change and clearance time."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-SPLIT-CLEARANCE"
    description: str = "Split covers the phase's yellow and red clearance"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            if phase.green_s < -self.policy.interval_tolerance_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} split of {phase.split_s:.1f} s is shorter "
                        f"than its {phase.clearance_s:.1f} s of change and "
                        "clearance time, leaving no green."
                    ),
                    phase=number,
                    observed=phase.split_s,
                    limit=phase.clearance_s,
                    reference=NEMA_REFERENCE,
                )


@dataclass
class SplitCoversMinimumGreen:
    """A split must accommodate minimum green plus clearance."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-SPLIT-MIN-GREEN"
    description: str = "Split accommodates minimum green plus clearance"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.split_s <= 0:
                continue
            required = phase.min_green_s + phase.clearance_s
            if phase.split_s + self.policy.interval_tolerance_s < required:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} split of {phase.split_s:.1f} s cannot serve "
                        f"{phase.min_green_s:.1f} s minimum green plus "
                        f"{phase.clearance_s:.1f} s clearance "
                        f"({required:.1f} s required)."
                    ),
                    phase=number,
                    observed=phase.split_s,
                    limit=round(required, 2),
                    reference=NEMA_REFERENCE,
                )


@dataclass
class MaximumGreenAboveMinimum:
    """Maximum green must not be shorter than minimum green."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-MAX-GREEN"
    description: str = "Maximum green is at least the minimum green"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            if phase.max_green_s is None:
                continue
            if phase.max_green_s < phase.min_green_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} maximum green of {phase.max_green_s:.1f} s "
                        f"is below its {phase.min_green_s:.1f} s minimum green."
                    ),
                    phase=number,
                    observed=phase.max_green_s,
                    limit=phase.min_green_s,
                    reference=NEMA_REFERENCE,
                )


@dataclass
class RingSumConsistency:
    """Rings must consume equal time between barriers.

    Both rings cross a barrier together. If one ring's splits sum to more than
    the other's within a concurrency group, the shorter ring waits at the
    barrier and the plan does not run as written.
    """

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-RING-SUM"
    description: str = "Rings consume equal time within each barrier group"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for group_index in range(len(plan.barrier_groups)):
            sums: list[tuple[int, float]] = []
            for ring_index in range(len(plan.rings)):
                if not plan.phases_in(ring_index, group_index):
                    continue
                sums.append(
                    (ring_index, plan.ring_split_sum(ring_index, group_index))
                )

            if len(sums) < 2:
                continue

            reference_ring, reference_sum = sums[0]
            for ring_index, total in sums[1:]:
                if approximately_equal(
                    total, reference_sum, self.policy.interval_tolerance_s
                ):
                    continue
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Barrier group {group_index + 1}: ring "
                        f"{ring_index + 1} sums to {total:.1f} s but ring "
                        f"{reference_ring + 1} sums to {reference_sum:.1f} s "
                        f"(differs by {abs(total - reference_sum):.1f} s)."
                    ),
                    observed=round(total, 2),
                    limit=round(reference_sum, 2),
                    reference=NEMA_REFERENCE,
                )


@dataclass
class CycleLengthConsistency:
    """Barrier group durations must sum to the background cycle length."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-CYCLE-SUM"
    description: str = "Barrier group durations sum to the cycle length"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        if plan.cycle_length_s <= 0:
            return

        total = 0.0
        for group_index in range(len(plan.barrier_groups)):
            ring_sums = [
                plan.ring_split_sum(ring_index, group_index)
                for ring_index in range(len(plan.rings))
                if plan.phases_in(ring_index, group_index)
            ]
            if ring_sums:
                total += max(ring_sums)

        if not approximately_equal(
            total, plan.cycle_length_s, self.policy.interval_tolerance_s
        ):
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=(
                    f"Splits sum to {total:.1f} s but the cycle length is "
                    f"{plan.cycle_length_s:.1f} s "
                    f"(differs by {abs(total - plan.cycle_length_s):.1f} s)."
                ),
                observed=round(total, 2),
                limit=plan.cycle_length_s,
                reference=NEMA_REFERENCE,
            )


@dataclass
class PedestrianTimeFitsSplit:
    """Pedestrian service must complete within the phase that serves it."""

    policy: Policy = DEFAULT_POLICY
    id: str = "STRUCT-PED-FITS"
    description: str = "WALK plus pedestrian change interval fits within the split"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        for number in sorted(plan.phases):
            phase = plan.phase(number)
            required = phase.total_pedestrian_s
            if required is None or phase.split_s <= 0:
                continue
            if phase.split_s + self.policy.interval_tolerance_s < required:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.ERROR,
                    message=(
                        f"Phase {number} needs {required:.1f} s of pedestrian time "
                        f"but its split is only {phase.split_s:.1f} s."
                    ),
                    phase=number,
                    observed=phase.split_s,
                    limit=round(required, 2),
                    reference=NEMA_REFERENCE,
                )


def structure_rules(policy: Policy = DEFAULT_POLICY) -> list:
    """Return every structural consistency rule, bound to ``policy``."""
    return [
        PhaseAssignmentComplete(policy),
        SplitCoversClearance(policy),
        SplitCoversMinimumGreen(policy),
        MaximumGreenAboveMinimum(policy),
        RingSumConsistency(policy),
        CycleLengthConsistency(policy),
        PedestrianTimeFitsSplit(policy),
    ]
