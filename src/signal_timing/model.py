"""Domain model for a NEMA ring-barrier signal timing plan.

The model is deliberately permissive: it holds whatever the practitioner
entered, including values that violate policy. Validation is a separate pass
(:mod:`signal_timing.validator`) so that an invalid plan can still be loaded,
inspected, and reported on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: The standard NEMA eight-phase ring assignment.
STANDARD_RINGS: tuple[tuple[int, ...], ...] = ((1, 2, 3, 4), (5, 6, 7, 8))

#: The standard NEMA eight-phase barrier (concurrency) groups.
STANDARD_BARRIER_GROUPS: tuple[tuple[int, ...], ...] = ((1, 2, 5, 6), (3, 4, 7, 8))


class PlanStructureError(ValueError):
    """Raised when a plan cannot be assembled into a coherent structure."""


@dataclass(frozen=True)
class Approach:
    """Geometry and speed for the approach served by a phase."""

    speed_mph: float
    grade: float = 0.0
    #: Stop line to far edge of the conflicting path, feet (for red clearance).
    clearance_distance_ft: float | None = None
    #: Curb-to-curb pedestrian crossing distance, feet.
    crossing_distance_ft: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speed_mph": self.speed_mph,
            "grade": self.grade,
            "clearance_distance_ft": self.clearance_distance_ft,
            "crossing_distance_ft": self.crossing_distance_ft,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Approach":
        return cls(
            speed_mph=data["speed_mph"],
            grade=data.get("grade", 0.0),
            clearance_distance_ft=data.get("clearance_distance_ft"),
            crossing_distance_ft=data.get("crossing_distance_ft"),
        )


@dataclass
class Phase:
    """One NEMA phase and its interval timing.

    ``split_s`` is the total time the phase is allocated in the cycle, which by
    NEMA convention includes the phase's own yellow change and red clearance
    intervals. ``green_s`` is therefore derived, not stored.
    """

    number: int
    name: str = ""
    min_green_s: float = 0.0
    max_green_s: float | None = None
    yellow_s: float = 0.0
    red_clearance_s: float = 0.0
    split_s: float = 0.0
    walk_s: float | None = None
    ped_change_s: float | None = None
    approach: Approach | None = None
    protected_left: bool = False

    @property
    def clearance_s(self) -> float:
        """Change-and-clearance time: yellow plus red clearance."""
        return self.yellow_s + self.red_clearance_s

    @property
    def green_s(self) -> float:
        """Green time available inside the split.

        May be negative if the split cannot cover the phase's own clearance
        intervals; that condition is reported by the structure rules.
        """
        return self.split_s - self.clearance_s

    @property
    def serves_pedestrians(self) -> bool:
        return self.walk_s is not None or self.ped_change_s is not None

    @property
    def total_pedestrian_s(self) -> float | None:
        """WALK plus pedestrian change interval, if the phase serves pedestrians."""
        if not self.serves_pedestrians:
            return None
        return (self.walk_s or 0.0) + (self.ped_change_s or 0.0)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "number": self.number,
            "name": self.name,
            "min_green_s": self.min_green_s,
            "max_green_s": self.max_green_s,
            "yellow_s": self.yellow_s,
            "red_clearance_s": self.red_clearance_s,
            "split_s": self.split_s,
            "walk_s": self.walk_s,
            "ped_change_s": self.ped_change_s,
            "protected_left": self.protected_left,
        }
        if self.approach is not None:
            data["approach"] = self.approach.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Phase":
        approach = data.get("approach")
        return cls(
            number=data["number"],
            name=data.get("name", ""),
            min_green_s=data.get("min_green_s", 0.0),
            max_green_s=data.get("max_green_s"),
            yellow_s=data.get("yellow_s", 0.0),
            red_clearance_s=data.get("red_clearance_s", 0.0),
            split_s=data.get("split_s", 0.0),
            walk_s=data.get("walk_s"),
            ped_change_s=data.get("ped_change_s"),
            approach=Approach.from_dict(approach) if approach else None,
            protected_left=data.get("protected_left", False),
        )


@dataclass
class TimingPlan:
    """A ring-barrier timing plan for one intersection.

    Args:
        name: Plan identifier, e.g. ``"AM Peak"``.
        cycle_length_s: Background cycle length. ``0`` denotes free operation.
        offset_s: Coordination offset from the system reference point.
        phases: The phases in the plan, keyed by phase number on construction.
        rings: Ordered phase numbers per ring. Defaults to standard NEMA rings,
            filtered to the phases actually present.
        barrier_groups: Phase numbers per concurrency group. Defaults to the
            standard NEMA barrier groups, filtered to the phases present.
        coordinated_phases: Phases whose green is held to maintain progression.
    """

    name: str
    cycle_length_s: float
    phases: dict[int, Phase]
    offset_s: float = 0.0
    rings: tuple[tuple[int, ...], ...] = ()
    barrier_groups: tuple[tuple[int, ...], ...] = ()
    coordinated_phases: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.phases:
            raise PlanStructureError("a timing plan must contain at least one phase")

        present = set(self.phases)
        for number, phase in self.phases.items():
            if number != phase.number:
                raise PlanStructureError(
                    f"phase keyed as {number} carries number {phase.number}"
                )

        if not self.rings:
            self.rings = _filter_groups(STANDARD_RINGS, present)
        if not self.barrier_groups:
            self.barrier_groups = _filter_groups(STANDARD_BARRIER_GROUPS, present)

        self.rings = tuple(tuple(r) for r in self.rings)
        self.barrier_groups = tuple(tuple(g) for g in self.barrier_groups)
        self.coordinated_phases = tuple(self.coordinated_phases)

        unknown = {n for ring in self.rings for n in ring} - present
        if unknown:
            raise PlanStructureError(
                f"rings reference phases not in the plan: {sorted(unknown)}"
            )
        unknown = {n for group in self.barrier_groups for n in group} - present
        if unknown:
            raise PlanStructureError(
                f"barrier groups reference phases not in the plan: {sorted(unknown)}"
            )
        unknown = set(self.coordinated_phases) - present
        if unknown:
            raise PlanStructureError(
                f"coordinated phases not in the plan: {sorted(unknown)}"
            )

    @property
    def is_coordinated(self) -> bool:
        return self.cycle_length_s > 0 and bool(self.coordinated_phases)

    def phase(self, number: int) -> Phase:
        """Return the phase with ``number``.

        Raises:
            KeyError: If the phase is not in the plan.
        """
        return self.phases[number]

    def ring_of(self, number: int) -> int | None:
        """Return the index of the ring containing ``number``, or None."""
        for index, ring in enumerate(self.rings):
            if number in ring:
                return index
        return None

    def barrier_group_of(self, number: int) -> int | None:
        """Return the index of the barrier group containing ``number``, or None."""
        for index, group in enumerate(self.barrier_groups):
            if number in group:
                return index
        return None

    def phases_in(self, ring_index: int, group_index: int) -> tuple[Phase, ...]:
        """Return phases in ring ``ring_index`` and barrier group ``group_index``.

        Order follows the ring's phase sequence.
        """
        group = set(self.barrier_groups[group_index])
        return tuple(
            self.phases[n] for n in self.rings[ring_index] if n in group
        )

    def ring_split_sum(self, ring_index: int, group_index: int) -> float:
        """Sum of splits in one ring within one barrier group."""
        return sum(p.split_s for p in self.phases_in(ring_index, group_index))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cycle_length_s": self.cycle_length_s,
            "offset_s": self.offset_s,
            "rings": [list(r) for r in self.rings],
            "barrier_groups": [list(g) for g in self.barrier_groups],
            "coordinated_phases": list(self.coordinated_phases),
            "phases": [self.phases[n].to_dict() for n in sorted(self.phases)],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimingPlan":
        phases = [Phase.from_dict(p) for p in data["phases"]]
        duplicates = _duplicates(p.number for p in phases)
        if duplicates:
            raise PlanStructureError(
                f"duplicate phase numbers in plan: {sorted(duplicates)}"
            )
        return cls(
            name=data.get("name", "unnamed"),
            cycle_length_s=data["cycle_length_s"],
            offset_s=data.get("offset_s", 0.0),
            phases={p.number: p for p in phases},
            rings=tuple(tuple(r) for r in data.get("rings", ())),
            barrier_groups=tuple(tuple(g) for g in data.get("barrier_groups", ())),
            coordinated_phases=tuple(data.get("coordinated_phases", ())),
            metadata=data.get("metadata", {}),
        )


def _filter_groups(
    groups: Iterable[Sequence[int]], present: set[int]
) -> tuple[tuple[int, ...], ...]:
    """Keep only phases that exist, dropping groups left empty."""
    filtered = tuple(
        tuple(n for n in group if n in present) for group in groups
    )
    return tuple(g for g in filtered if g)


def _duplicates(values: Iterable[int]) -> set[int]:
    seen: set[int] = set()
    dupes: set[int] = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return dupes
