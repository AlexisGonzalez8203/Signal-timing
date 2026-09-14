"""Command line interface: validate timing plan files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import PlanStructureError
from .policy import Policy
from .report import ValidationReport
from .validator import validate_file

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_BAD_INPUT = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signal-timing",
        description="Validate traffic signal timing plans against MUTCD, ITE, "
        "and NEMA structural requirements.",
    )
    parser.add_argument(
        "plans",
        nargs="+",
        type=Path,
        help="One or more timing plan JSON files.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress INFO findings in text output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    parser.add_argument(
        "--walking-speed",
        type=float,
        default=None,
        metavar="FPS",
        help="Override the pedestrian walking speed, ft/s.",
    )
    parser.add_argument(
        "--max-cycle",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Override the practical maximum cycle length.",
    )
    return parser


def _policy_from_args(args: argparse.Namespace) -> Policy:
    overrides: dict[str, float] = {}
    if args.walking_speed is not None:
        overrides["walking_speed_fps"] = args.walking_speed
    if args.max_cycle is not None:
        overrides["max_cycle_length_s"] = args.max_cycle
    return Policy(**overrides)


def _failed(report: ValidationReport, strict: bool) -> bool:
    if strict:
        return bool(report.errors or report.warnings)
    return not report.passed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = _policy_from_args(args)

    reports: list[tuple[Path, ValidationReport]] = []
    for path in args.plans:
        try:
            reports.append((path, validate_file(path, policy=policy)))
        except FileNotFoundError:
            print(f"error: no such plan file: {path}", file=sys.stderr)
            return EXIT_BAD_INPUT
        except json.JSONDecodeError as exc:
            print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
            return EXIT_BAD_INPUT
        except (PlanStructureError, KeyError) as exc:
            print(f"error: {path} is not a usable timing plan: {exc}", file=sys.stderr)
            return EXIT_BAD_INPUT

    if args.format == "json":
        payload = [
            {"file": str(path), **report.to_dict()} for path, report in reports
        ]
        print(json.dumps(payload, indent=2))
    else:
        for index, (path, report) in enumerate(reports):
            if index:
                print()
            print(f"--- {path} ---")
            print(report.to_text(show_info=not args.quiet))

    any_failed = any(_failed(report, args.strict) for _, report in reports)
    return EXIT_FINDINGS if any_failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
