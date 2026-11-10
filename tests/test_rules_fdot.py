"""Tests for the FDOT TEM rules and the input-completeness rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import make_phase, make_plan
from signal_timing import fdot_ruleset, validate
from signal_timing.cli import EXIT_FINDINGS, EXIT_OK, main
from signal_timing.model import Approach, TimingPlan
from signal_timing.rules.base import Severity
from signal_timing.rules.fdot import (
    InputCompleteness,
    PedestrianCountdown,
    PedestrianReach,
    TemRedClearance,
    TemYellow,
    tem_required_red,
    tem_required_yellow,
)


def findings_for(rule, *phases):
    return list(rule.check(make_plan(phases=list(phases), coordinated_phases=())))


class TestRequiredYellow:
    @pytest.mark.parametrize(
        "mph, expected",
        [(25, 3.4), (30, 3.7), (35, 4.0), (40, 4.4), (45, 4.8), (50, 5.1),
         (55, 5.5), (60, 5.9), (65, 6.0)],
    )
    def test_matches_tem_table_at_level_grade(self, mph, expected):
        assert tem_required_yellow(mph) == pytest.approx(expected)

    def test_downgrade_uses_the_formula_and_lengthens_yellow(self):
        assert tem_required_yellow(45, grade=-0.04) > tem_required_yellow(45)

    def test_off_table_speed_uses_the_formula(self):
        assert tem_required_yellow(42) == pytest.approx(4.5, abs=0.1)


class TestRequiredRed:
    def test_formula_3_6_2(self):
        # (60 + 20) / (1.47 * 45) = 1.21 s -> rounded up to 1.3 s
        assert tem_required_red(60, 45) == pytest.approx(1.3)


class TestTemYellow:
    rule = TemYellow()

    def test_accepts_the_table_minimum(self):
        phase = make_phase(2, yellow_s=4.8, approach=Approach(45.0, grade=0.0))
        assert findings_for(self.rule, phase) == []

    def test_flags_an_ite_adequate_but_tem_short_yellow(self):
        """4.5 s clears the ITE 4.3 s requirement but not the TEM 4.8 s."""
        phase = make_phase(2, yellow_s=4.5, approach=Approach(45.0))
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.ERROR
        assert finding.limit == pytest.approx(4.8)

    def test_flags_yellow_above_six_seconds(self):
        phase = make_phase(2, yellow_s=6.5, approach=Approach(45.0))
        (finding,) = findings_for(self.rule, phase)
        assert finding.limit == 6.0

    def test_applies_the_three_second_floor_without_approach_data(self):
        (finding,) = findings_for(self.rule, make_phase(2, yellow_s=2.5))
        assert finding.limit == 3.0


class TestTemRedClearance:
    rule = TemRedClearance()

    def test_red_clearance_is_mandatory(self):
        (finding,) = findings_for(self.rule, make_phase(2, red_clearance_s=0.0))
        assert finding.severity is Severity.ERROR
        assert finding.limit == 2.0

    def test_flags_red_above_six_seconds(self):
        (finding,) = findings_for(self.rule, make_phase(2, red_clearance_s=6.5))
        assert finding.limit == 6.0

    def test_short_of_formula_within_nchrp_reduction_is_a_warning(self):
        # 100 ft at 30 mph: (100+20)/(1.47*30) = 2.7 s; 2.0 s is within 1.0 s.
        approach = Approach(30.0, clearance_distance_ft=100.0)
        (finding,) = findings_for(
            self.rule, make_phase(2, red_clearance_s=2.0, approach=approach)
        )
        assert finding.severity is Severity.WARNING

    def test_far_short_of_formula_is_an_error(self):
        # 200 ft at 30 mph: 5.0 s; 2.0 s is more than 1.0 s short.
        approach = Approach(30.0, clearance_distance_ft=200.0)
        (finding,) = findings_for(
            self.rule, make_phase(2, red_clearance_s=2.0, approach=approach)
        )
        assert finding.severity is Severity.ERROR


class TestPedestrianReach:
    rule = PedestrianReach()

    def test_flags_total_time_short_of_detector_to_far_side(self):
        # (60 + 6) / 3.0 = 22 s needed, 7 + 12 = 19 s entered.
        phase = make_phase(
            2, walk_s=7.0, ped_change_s=12.0,
            approach=Approach(45.0, crossing_distance_ft=60.0),
        )
        (finding,) = findings_for(self.rule, phase)
        assert finding.limit == pytest.approx(22.0)

    def test_accepts_sufficient_total_time(self):
        phase = make_phase(
            2, walk_s=7.0, ped_change_s=17.2,
            approach=Approach(45.0, crossing_distance_ft=60.0),
        )
        assert findings_for(self.rule, phase) == []


class TestPedestrianCountdown:
    rule = PedestrianCountdown()

    def test_notes_that_a_long_change_interval_needs_a_countdown(self):
        phase = make_phase(2, walk_s=7.0, ped_change_s=14.0)
        (finding,) = findings_for(self.rule, phase)
        assert finding.severity is Severity.INFO

    def test_silent_for_short_change_intervals(self):
        assert findings_for(self.rule, make_phase(2, walk_s=7.0, ped_change_s=7.0)) == []


class TestInputCompleteness:
    rule = InputCompleteness()

    def test_flags_a_phase_with_no_approach_data(self):
        (finding,) = findings_for(self.rule, make_phase(2))
        assert finding.severity is Severity.WARNING
        assert "NOT verified" in finding.message

    def test_flags_missing_clearance_distance_and_assumed_grade(self):
        plan = TimingPlan.from_dict({
            "cycle_length_s": 80,
            "phases": [{"number": 2, "split_s": 20, "yellow_s": 4.8,
                        "red_clearance_s": 2.0, "approach": {"speed_mph": 45}}],
        })
        messages = [f.message for f in self.rule.check(plan)]
        assert any("no grade" in m for m in messages)
        assert any("clearance_distance_ft" in m for m in messages)

    def test_flags_pedestrian_phase_missing_crossing_distance(self):
        phase = make_phase(
            2, walk_s=7.0, ped_change_s=14.0,
            approach=Approach(45.0, clearance_distance_ft=60.0),
        )
        assert any("crossing_distance_ft" in f.message
                   for f in findings_for(self.rule, phase))

    def test_silent_when_every_input_is_present(self):
        phase = make_phase(
            2, walk_s=7.0, ped_change_s=14.0,
            approach=Approach(45.0, clearance_distance_ft=60.0,
                              crossing_distance_ft=48.0),
        )
        assert findings_for(self.rule, phase) == []


class TestFdotRuleset:
    def test_does_not_double_report_range_or_adequacy_problems(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, yellow_s=2.5, approach=Approach(45.0))
        report = validate(make_plan(phases=phases), standard="fdot")
        yellow = [f for f in report.findings if f.phase == 2 and "yellow" in f.message]
        assert len(yellow) == 1

    def test_unknown_standard_is_rejected(self):
        with pytest.raises(ValueError, match="unknown standard"):
            validate(make_plan(), standard="nope")

    def test_cli_standard_flag_changes_the_verdict(self, tmp_path: Path):
        phases = [
            make_phase(n, yellow_s=4.5, red_clearance_s=2.0,
                       approach=Approach(45.0, grade=0.0))
            for n in range(1, 9)
        ]
        path = tmp_path / "p.json"
        path.write_text(json.dumps(make_plan(phases=phases).to_dict()), "utf-8")
        assert main([str(path), "--quiet"]) == EXIT_OK
        assert main([str(path), "--quiet", "--standard", "fdot"]) == EXIT_FINDINGS

    def test_ruleset_is_named_and_nonempty(self):
        assert fdot_ruleset().name == "fdot"
        assert len(fdot_ruleset()) > 0
