"""Rule and finding primitives for the validation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol, runtime_checkable

from ..model import TimingPlan


class Severity(str, Enum):
    """How serious a finding is.

    ERROR marks a violation of a mandatory ("shall") requirement or an
    internally inconsistent plan that a controller cannot run as entered.
    WARNING marks a departure from guidance ("should") that an engineer may
    accept with documented judgment. INFO is advisory only.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 2, "warning": 1, "info": 0}[self.value]


@dataclass(frozen=True)
class Finding:
    """A single validation result.

    Args:
        rule_id: Stable identifier of the rule that produced this finding.
        severity: Seriousness of the finding.
        message: Human-readable description, stating the observed value.
        phase: Phase number the finding applies to, if phase-specific.
        observed: The value that was checked.
        limit: The threshold or expected value it was checked against.
        reference: Citation for the requirement, e.g. an MUTCD section.
    """

    rule_id: str
    severity: Severity
    message: str
    phase: int | None = None
    observed: float | None = None
    limit: float | None = None
    reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "phase": self.phase,
            "observed": self.observed,
            "limit": self.limit,
            "reference": self.reference,
        }


@runtime_checkable
class Rule(Protocol):
    """A validation rule.

    Implementations inspect a plan and yield zero or more findings. A rule that
    finds nothing wrong yields nothing.
    """

    id: str
    description: str

    def check(self, plan: TimingPlan) -> Iterable[Finding]:
        """Yield findings for ``plan``."""
        ...


@dataclass
class RuleSet:
    """An ordered collection of rules, applied together."""

    name: str
    rules: list[Rule] = field(default_factory=list)

    def add(self, rule: Rule) -> "RuleSet":
        """Append ``rule`` and return self, for chaining."""
        self.rules.append(rule)
        return self

    def extend(self, rules: Iterable[Rule]) -> "RuleSet":
        """Append several rules and return self."""
        for rule in rules:
            self.add(rule)
        return self

    def check(self, plan: TimingPlan) -> list[Finding]:
        """Run every rule against ``plan`` and collect the findings."""
        findings: list[Finding] = []
        for rule in self.rules:
            findings.extend(rule.check(plan))
        return findings

    def __len__(self) -> int:
        return len(self.rules)


#: Tolerance in seconds for comparing timing values that should be equal.
#: Controllers enter timing to a tenth of a second; anything tighter is noise.
TOLERANCE_S = 0.05


def approximately_equal(a: float, b: float, tolerance: float = TOLERANCE_S) -> bool:
    """Return True if ``a`` and ``b`` agree within ``tolerance``."""
    return abs(a - b) <= tolerance
