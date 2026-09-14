"""Shared fixtures and builders for the test suite."""

from __future__ import annotations

import pytest

from signal_timing.model import Approach, Phase, TimingPlan


def make_phase(number: int, **overrides) -> Phase:
    """Build a phase that is valid by default, with targeted overrides.

    Defaults give a 20 s split carrying 3.5 s yellow and 2.0 s red clearance,
    which satisfies every structural rule on its own.
    """
    defaults = dict(
        number=number,
        name=f"phase {number}",
        min_green_s=5.0,
        max_green_s=30.0,
        yellow_s=3.5,
        red_clearance_s=2.0,
        split_s=20.0,
    )
    defaults.update(overrides)
    return Phase(**defaults)


def make_plan(phases=None, **overrides) -> TimingPlan:
    """Build an eight-phase plan whose rings and cycle balance by default."""
    if phases is None:
        phases = [make_phase(n) for n in range(1, 9)]
    defaults = dict(
        name="test plan",
        cycle_length_s=80.0,
        offset_s=0.0,
        phases={p.number: p for p in phases},
        coordinated_phases=(2, 6),
    )
    defaults.update(overrides)
    return TimingPlan(**defaults)


@pytest.fixture
def balanced_plan() -> TimingPlan:
    """An eight-phase plan with equal 20 s splits and an 80 s cycle."""
    return make_plan()


@pytest.fixture
def pedestrian_approach() -> Approach:
    return Approach(
        speed_mph=30.0,
        clearance_distance_ft=70.0,
        crossing_distance_ft=48.0,
    )
