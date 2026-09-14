"""Tests for the command line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import make_phase, make_plan
from signal_timing.cli import EXIT_BAD_INPUT, EXIT_FINDINGS, EXIT_OK, main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
GOOD = str(EXAMPLES / "eight_phase_coordinated.json")
FAULTY = str(EXAMPLES / "faulty_plan.json")


def write_plan(path: Path, plan) -> str:
    path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
    return str(path)


class TestExitCodes:
    def test_clean_plan_exits_zero(self, capsys):
        assert main([GOOD]) == EXIT_OK
        assert "PASS" in capsys.readouterr().out

    def test_plan_with_errors_exits_one(self, capsys):
        assert main([FAULTY]) == EXIT_FINDINGS
        assert "FAIL" in capsys.readouterr().out

    def test_missing_file_exits_two(self, capsys):
        assert main(["does-not-exist.json"]) == EXIT_BAD_INPUT
        assert "no such plan file" in capsys.readouterr().err

    def test_malformed_json_exits_two(self, tmp_path: Path, capsys):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert main([str(path)]) == EXIT_BAD_INPUT
        assert "not valid JSON" in capsys.readouterr().err

    def test_structurally_invalid_plan_exits_two(self, tmp_path: Path, capsys):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"cycle_length_s": 60, "phases": []}), "utf-8")
        assert main([str(path)]) == EXIT_BAD_INPUT
        assert "not a usable timing plan" in capsys.readouterr().err

    def test_missing_required_key_exits_two(self, tmp_path: Path, capsys):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"phases": [{"number": 2}]}), "utf-8")
        assert main([str(path)]) == EXIT_BAD_INPUT
        assert "not a usable timing plan" in capsys.readouterr().err


class TestStrictMode:
    def test_warnings_pass_by_default(self, tmp_path: Path):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[0] = make_phase(1, min_green_s=2.0)
        path = write_plan(tmp_path / "warn.json", make_plan(phases=phases))
        assert main([path]) == EXIT_OK

    def test_warnings_fail_under_strict(self, tmp_path: Path):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[0] = make_phase(1, min_green_s=2.0)
        path = write_plan(tmp_path / "warn.json", make_plan(phases=phases))
        assert main([path, "--strict"]) == EXIT_FINDINGS

    def test_strict_still_passes_a_clean_plan(self):
        assert main([GOOD, "--strict"]) == EXIT_OK


class TestOutputFormats:
    def test_json_output_is_parsable(self, capsys):
        main([GOOD, "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["passed"] is True
        assert payload[0]["file"] == GOOD

    def test_json_output_lists_findings(self, capsys):
        main([FAULTY, "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["counts"]["error"] > 0
        assert payload[0]["findings"][0]["severity"] == "error"

    def test_quiet_suppresses_info_findings(self, tmp_path: Path, capsys):
        phases = [make_phase(n) for n in range(1, 9)]
        phases[1] = make_phase(2, walk_s=7.0, ped_change_s=10.0)
        path = write_plan(tmp_path / "info.json", make_plan(phases=phases))

        main([path])
        assert "INFO" in capsys.readouterr().out
        main([path, "--quiet"])
        assert "INFO" not in capsys.readouterr().out


class TestPolicyOverrides:
    def test_walking_speed_override_changes_the_outcome(self, capsys):
        assert main([GOOD]) == EXIT_OK
        capsys.readouterr()
        # A 3.0 ft/s design speed demands longer pedestrian change intervals.
        assert main([GOOD, "--walking-speed", "3.0"]) == EXIT_FINDINGS
        assert "MUTCD" in capsys.readouterr().out

    def test_max_cycle_override_changes_the_outcome(self, capsys):
        assert main([GOOD, "--max-cycle", "90", "--strict"]) == EXIT_FINDINGS
        assert "practical maximum" in capsys.readouterr().out


class TestMultipleFiles:
    def test_validates_every_file_given(self, capsys):
        main([GOOD, FAULTY])
        out = capsys.readouterr().out
        assert GOOD in out and FAULTY in out

    def test_one_failure_fails_the_run(self):
        assert main([GOOD, FAULTY]) == EXIT_FINDINGS

    def test_all_clean_passes_the_run(self):
        assert main([GOOD, GOOD]) == EXIT_OK

    def test_json_output_covers_every_file(self, capsys):
        main([GOOD, FAULTY, "--format", "json"])
        assert len(json.loads(capsys.readouterr().out)) == 2


class TestArgumentParsing:
    def test_requires_at_least_one_plan(self):
        with pytest.raises(SystemExit):
            main([])

    def test_rejects_an_unknown_format(self):
        with pytest.raises(SystemExit):
            main([GOOD, "--format", "yaml"])
