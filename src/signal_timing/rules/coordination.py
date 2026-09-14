"""Rules covering coordination parameters: cycle length, offset, and coord phases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..model import TimingPlan
from ..policy import DEFAULT_POLICY, Policy
from .base import Finding, Severity

COORDINATION_REFERENCE = "ITE Signal Timing Manual -- coordination parameters"


@dataclass
class CycleLengthReasonable:
    """Cycle length must be positive and within a workable range."""

    policy: Policy = DEFAULT_POLICY
    id: str = "COORD-CYCLE-RANGE"
    description: str = "Cycle length is within a workable range"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        if plan.cycle_length_s == 0:
            return  # free operation
        if plan.cycle_length_s < 0:
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=f"Cycle length is negative ({plan.cycle_length_s:.1f} s).",
                observed=plan.cycle_length_s,
                limit=0.0,
                reference=COORDINATION_REFERENCE,
            )
        elif plan.cycle_length_s > self.policy.max_cycle_length_s:
            yield Finding(
                rule_id=self.id,
                severity=Severity.WARNING,
                message=(
                    f"Cycle length of {plan.cycle_length_s:.1f} s exceeds the "
                    f"{self.policy.max_cycle_length_s:.0f} s practical maximum."
                ),
                observed=plan.cycle_length_s,
                limit=self.policy.max_cycle_length_s,
                reference=COORDINATION_REFERENCE,
            )


@dataclass
class OffsetWithinCycle:
    """Offset must fall within one cycle and not be negative."""

    policy: Policy = DEFAULT_POLICY
    id: str = "COORD-OFFSET-RANGE"
    description: str = "Offset is within the cycle length"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        if plan.cycle_length_s <= 0:
            if plan.offset_s:
                yield Finding(
                    rule_id=self.id,
                    severity=Severity.WARNING,
                    message=(
                        f"Offset of {plan.offset_s:.1f} s is set on a plan with no "
                        "cycle length, so it has no effect."
                    ),
                    observed=plan.offset_s,
                    reference=COORDINATION_REFERENCE,
                )
            return

        if plan.offset_s < 0:
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=f"Offset is negative ({plan.offset_s:.1f} s).",
                observed=plan.offset_s,
                limit=0.0,
                reference=COORDINATION_REFERENCE,
            )
        elif plan.offset_s >= plan.cycle_length_s:
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=(
                    f"Offset of {plan.offset_s:.1f} s is not less than the "
                    f"{plan.cycle_length_s:.1f} s cycle length."
                ),
                observed=plan.offset_s,
                limit=plan.cycle_length_s,
                reference=COORDINATION_REFERENCE,
            )


@dataclass
class CoordinatedPhasesDesignated:
    """A plan running a background cycle should name its coordinated phases."""

    policy: Policy = DEFAULT_POLICY
    id: str = "COORD-PHASES-SET"
    description: str = "Coordinated phases are designated on a coordinated plan"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        if plan.cycle_length_s <= 0 or plan.coordinated_phases:
            return
        yield Finding(
            rule_id=self.id,
            severity=Severity.WARNING,
            message=(
                f"Plan runs a {plan.cycle_length_s:.1f} s cycle but designates no "
                "coordinated phase."
            ),
            reference=COORDINATION_REFERENCE,
        )


@dataclass
class CoordinatedPhasesConcurrent:
    """Coordinated phases must be able to run together.

    Phases held concurrently for progression have to sit in different rings and
    in the same barrier group -- the standard case being phases 2 and 6.
    """

    policy: Policy = DEFAULT_POLICY
    id: str = "COORD-PHASES-CONCURRENT"
    description: str = "Coordinated phases can run concurrently"

    def check(self, plan: TimingPlan) -> Iterator[Finding]:
        coordinated = list(plan.coordinated_phases)
        if len(coordinated) < 2:
            return

        groups = {plan.barrier_group_of(n) for n in coordinated}
        if len(groups) > 1:
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=(
                    "Coordinated phases "
                    f"{', '.join(str(n) for n in coordinated)} span multiple "
                    "barrier groups and cannot run concurrently."
                ),
                reference=COORDINATION_REFERENCE,
            )

        rings = [plan.ring_of(n) for n in coordinated]
        if len(set(rings)) != len(rings):
            yield Finding(
                rule_id=self.id,
                severity=Severity.ERROR,
                message=(
                    "Coordinated phases "
                    f"{', '.join(str(n) for n in coordinated)} share a ring and "
                    "cannot run concurrently."
                ),
                reference=COORDINATION_REFERENCE,
            )


def coordination_rules(policy: Policy = DEFAULT_POLICY) -> list:
    """Return every coordination rule, bound to ``policy``."""
    return [
        CycleLengthReasonable(policy),
        OffsetWithinCycle(policy),
        CoordinatedPhasesDesignated(policy),
        CoordinatedPhasesConcurrent(policy),
    ]
