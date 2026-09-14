"""Tests for the coordination rules."""

from __future__ import annotations

from conftest import make_phase, make_plan
from signal_timing.policy import Policy
from signal_timing.rules.base import Severity
from signal_timing.rules.coordination import (
    CoordinatedPhasesConcurrent,
    CoordinatedPhasesDesignated,
    CycleLengthReasonable,
    OffsetWithinCycle,
)


class TestCycleLengthReasonable:
    rule = CycleLengthReasonable()

    def test_accepts_a_normal_cycle(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_treats_zero_as_free_operation(self):
        assert list(self.rule.check(make_plan(cycle_length_s=0.0))) == []

    def test_flags_a_negative_cycle(self):
        (finding,) = list(self.rule.check(make_plan(cycle_length_s=-30.0)))
        assert finding.severity is Severity.ERROR

    def test_warns_above_the_practical_maximum(self):
        (finding,) = list(self.rule.check(make_plan(cycle_length_s=300.0)))
        assert finding.severity is Severity.WARNING
        assert finding.limit == 240.0

    def test_respects_a_lower_agency_maximum(self):
        rule = CycleLengthReasonable(Policy(max_cycle_length_s=120.0))
        assert len(list(rule.check(make_plan(cycle_length_s=150.0)))) == 1


class TestOffsetWithinCycle:
    rule = OffsetWithinCycle()

    def test_accepts_an_offset_inside_the_cycle(self):
        assert list(self.rule.check(make_plan(offset_s=45.0))) == []

    def test_accepts_a_zero_offset(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_flags_a_negative_offset(self):
        (finding,) = list(self.rule.check(make_plan(offset_s=-5.0)))
        assert finding.severity is Severity.ERROR

    def test_flags_an_offset_equal_to_the_cycle(self):
        """An offset of one full cycle is the same as zero, and is a data error."""
        (finding,) = list(self.rule.check(make_plan(offset_s=80.0)))
        assert finding.severity is Severity.ERROR

    def test_flags_an_offset_beyond_the_cycle(self):
        (finding,) = list(self.rule.check(make_plan(offset_s=130.0, cycle_length_s=100.0)))
        assert finding.severity is Severity.ERROR
        assert finding.limit == 100.0

    def test_warns_when_an_offset_is_set_on_a_free_plan(self):
        plan = make_plan(cycle_length_s=0.0, offset_s=20.0, coordinated_phases=())
        (finding,) = list(self.rule.check(plan))
        assert finding.severity is Severity.WARNING
        assert "no effect" in finding.message

    def test_silent_on_a_free_plan_with_no_offset(self):
        plan = make_plan(cycle_length_s=0.0, offset_s=0.0, coordinated_phases=())
        assert list(self.rule.check(plan)) == []


class TestCoordinatedPhasesDesignated:
    rule = CoordinatedPhasesDesignated()

    def test_accepts_a_plan_that_names_its_coordinated_phases(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_warns_when_a_cycle_runs_with_no_coordinated_phase(self):
        (finding,) = list(self.rule.check(make_plan(coordinated_phases=())))
        assert finding.severity is Severity.WARNING

    def test_silent_on_free_operation(self):
        plan = make_plan(cycle_length_s=0.0, coordinated_phases=())
        assert list(self.rule.check(plan)) == []


class TestCoordinatedPhasesConcurrent:
    rule = CoordinatedPhasesConcurrent()

    def test_accepts_the_standard_pairing(self, balanced_plan):
        assert list(self.rule.check(balanced_plan)) == []

    def test_silent_for_a_single_coordinated_phase(self):
        assert list(self.rule.check(make_plan(coordinated_phases=(2,)))) == []

    def test_flags_coordinated_phases_in_the_same_ring(self):
        findings = list(self.rule.check(make_plan(coordinated_phases=(1, 2))))
        assert any("share a ring" in f.message for f in findings)

    def test_flags_coordinated_phases_across_barrier_groups(self):
        findings = list(self.rule.check(make_plan(coordinated_phases=(2, 7))))
        assert any("multiple barrier groups" in f.message for f in findings)
        assert all(f.severity is Severity.ERROR for f in findings)

    def test_accepts_the_side_street_pairing(self):
        assert list(self.rule.check(make_plan(coordinated_phases=(4, 8)))) == []
