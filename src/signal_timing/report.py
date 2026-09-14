"""Validation results and their rendered forms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules.base import Finding, Severity


@dataclass
class ValidationReport:
    """The findings produced by validating one plan."""

    plan_name: str
    findings: list[Finding] = field(default_factory=list)
    rules_run: int = 0

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def passed(self) -> bool:
        """True when nothing rose to the level of an error."""
        return not self.errors

    def sorted_findings(self) -> list[Finding]:
        """Findings ordered by severity, then phase, then rule id."""
        return sorted(
            self.findings,
            key=lambda f: (-f.severity.rank, f.phase if f.phase else 0, f.rule_id),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "passed": self.passed,
            "rules_run": self.rules_run,
            "counts": {
                "error": len(self.errors),
                "warning": len(self.warnings),
                "info": len(self.infos),
            },
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }

    def to_text(self, show_info: bool = True) -> str:
        """Render the report as plain text for a terminal or a log."""
        marks = {
            Severity.ERROR: "ERROR  ",
            Severity.WARNING: "WARNING",
            Severity.INFO: "INFO   ",
        }

        lines = [f"Timing plan: {self.plan_name}", "=" * 60]
        shown = [
            f
            for f in self.sorted_findings()
            if show_info or f.severity is not Severity.INFO
        ]

        if not shown:
            lines.append("No findings.")
        else:
            for finding in shown:
                lines.append(f"{marks[finding.severity]}  {finding.message}")
                if finding.reference:
                    lines.append(f"{' ' * 11}{finding.reference}")

        lines.append("=" * 60)
        lines.append(
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s), "
            f"{len(self.infos)} info across {self.rules_run} rule(s) -- "
            f"{'PASS' if self.passed else 'FAIL'}"
        )
        return "\n".join(lines)
