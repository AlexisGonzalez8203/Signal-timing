"""Tests for the validator entry point, rule set, and report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import make_phase, make_plan
from signal_timing import default_ruleset, validate, validate_file
from signal_timing.model import Approach, PlanStructureError
from signal_timing.policy import Policy
from signal_timing.report import ValidationReport
from signal_timing.rules.base import Finding, RuleSet, Severity
from signal_timing.validator import load_plan

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class StubRule:
    """A rule that yields whatever it was constructed with."""

    def __init__(self, rule_id: str, findings: list[Finding]):
        self.id = rule_id
        self.description = "stub"
        self._findings = findings

    def check(self, plan):
        return list(self._findings)


def finding(severity: Severity, phase: int | None = None) -> Finding:
    return Finding(
        rule_id="STUB", severity=severity, message=f"{severity.value} finding",
        phase=phase,
    )


class TestRuleSet:
    def test_collects_findings_from_every_rule(self, balanced_plan):
        ruleset = RuleSet("t").extend(
            [
                StubRule("a", [finding(Severity.ERROR)]),
                StubRule("b", [finding(Severity.WARNING)]),
            ]
        )
        assert len(ruleset.check(balanced_plan)) == 2
        assert len(ruleset) == 2

    def test_add_returns_self_for_chaining(self):
        ruleset = RuleSet("t").add(StubRule("a", [])).add(StubRule("b", []))
        assert len(ruleset) == 2

    def test_default_ruleset_is_populated(self):
        assert len(default_ruleset()) == 18

    def test_default_ruleset_binds_the_policy(self):
        strict = default_ruleset(Policy(yellow_min_s=5.0))
        plan = make_plan()
        assert any(f.rule_id == "MUTCD-Y-RANGE" for f in strict.check(plan))


class TestValidate:
    def test_a_sound_plan_produces_no_findings(self, balanced_plan):
        report = validate(balanced_plan)
        assert report.passed
        assert report.findings == []
        assert report.rules_run == 18

    def test_the_report_carries_the_plan_name(self, balanced_plan):
        assert validate(balanced_plan).plan_name == "test plan"

    def test_a_supplied_ruleset_replaces_the_default(self, balanced_plan):
        ruleset = RuleSet("t").add(StubRule("a", [finding(Severity.ERROR)]))
        report = validate(balanced_plan, ruleset=ruleset)
        assert report.rules_run == 1
        assert len(report.errors) == 1

    def test_errors_fail_the_report(self):
        report = validate(make_plan(cycle_length_s=100.0))
        assert not report.passed
        assert report.errors

    def test_warnings_alone_do_not_fail_the_report(self):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[0] = make_phase(1, min_green_s=2.0)
        report = validate(make_plan(phases=phases))
        assert report.warnings
        assert report.passed


class TestReport:
    def _mixed_report(self) -> ValidationReport:
        return ValidationReport(
            plan_name="mixed",
            rules_run=3,
            findings=[
                finding(Severity.INFO, phase=3),
                finding(Severity.ERROR, phase=2),
                finding(Severity.WARNING, phase=1),
            ],
        )

    def test_partitions_findings_by_severity(self):
        report = self._mixed_report()
        assert len(report.errors) == 1
        assert len(report.warnings) == 1
        assert len(report.infos) == 1

    def test_sorts_most_severe_first(self):
        order = [f.severity for f in self._mixed_report().sorted_findings()]
        assert order == [Severity.ERROR, Severity.WARNING, Severity.INFO]

    def test_sorts_by_phase_within_a_severity(self):
        report = ValidationReport(
            plan_name="p",
            findings=[
                finding(Severity.ERROR, phase=6),
                finding(Severity.ERROR, phase=2),
            ],
        )
        assert [f.phase for f in report.sorted_findings()] == [2, 6]

    def test_text_output_reports_pass_for_a_clean_plan(self, balanced_plan):
        text = validate(balanced_plan).to_text()
        assert "No findings." in text
        assert "PASS" in text

    def test_text_output_reports_fail_and_lists_findings(self):
        text = validate(make_plan(cycle_length_s=100.0)).to_text()
        assert "FAIL" in text
        assert "ERROR" in text

    def test_quiet_mode_hides_info_findings(self):
        report = self._mixed_report()
        assert "info finding" in report.to_text(show_info=True)
        assert "info finding" not in report.to_text(show_info=False)

    def test_dict_output_is_json_serializable(self, balanced_plan):
        payload = validate(balanced_plan).to_dict()
        assert json.loads(json.dumps(payload))["passed"] is True
        assert payload["counts"] == {"error": 0, "warning": 0, "info": 0}


class TestFileLoading:
    def test_loads_and_validates_the_bundled_example(self):
        report = validate_file(EXAMPLES / "eight_phase_coordinated.json")
        assert report.passed, report.to_text()

    def test_the_faulty_example_fails_as_documented(self):
        report = validate_file(EXAMPLES / "faulty_plan.json")
        assert not report.passed
        rule_ids = {f.rule_id for f in report.findings}
        assert {
            "COORD-OFFSET-RANGE",
            "MUTCD-PCI-ADEQUACY",
            "MUTCD-WALK-MIN",
            "MUTCD-R-RANGE",
            "MUTCD-Y-RANGE",
            "STRUCT-CYCLE-SUM",
            "STRUCT-RING-SUM",
        } <= rule_ids

    def test_loaded_plan_round_trips(self, tmp_path: Path):
        source = make_plan(metadata={"agency": "Example DOT"})
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(source.to_dict()), encoding="utf-8")
        assert load_plan(path).to_dict() == source.to_dict()

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_plan(tmp_path / "absent.json")

    def test_malformed_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_plan(path)

    def test_structurally_invalid_plan_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps({"cycle_length_s": 60.0, "phases": []}), encoding="utf-8"
        )
        with pytest.raises(PlanStructureError):
            load_plan(path)


class TestEndToEnd:
    def test_a_realistic_plan_with_one_planted_fault_reports_only_that_fault(self):
        """Guards against rules firing on timing they should not care about."""
        phases = [
            make_phase(
                n,
                yellow_s=4.5,
                red_clearance_s=1.5,
                approach=Approach(speed_mph=45.0, clearance_distance_ft=60.0),
            )
            for n in range(1, 9)
        ]
        phases[1] = make_phase(
            2,
            yellow_s=3.0,  # the planted fault: short for a 45 mph approach
            red_clearance_s=1.5,
            approach=Approach(speed_mph=45.0, clearance_distance_ft=60.0),
        )
        report = validate(make_plan(phases=phases))
        assert [f.rule_id for f in report.findings] == ["ITE-Y-ADEQUACY"]
        assert report.findings[0].phase == 2
