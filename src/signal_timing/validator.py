"""Entry point for validating a timing plan against a rule set."""

from __future__ import annotations

import json
from pathlib import Path

from .model import TimingPlan
from .policy import DEFAULT_POLICY, Policy
from .report import ValidationReport
from .rules import default_ruleset
from .rules.base import RuleSet


def validate(
    plan: TimingPlan,
    ruleset: RuleSet | None = None,
    policy: Policy = DEFAULT_POLICY,
) -> ValidationReport:
    """Validate ``plan`` and return a report.

    Args:
        plan: The timing plan to check.
        ruleset: Rules to apply. Defaults to the full built-in set bound to
            ``policy``. When a ruleset is supplied, ``policy`` is ignored --
            the rules carry their own.
        policy: Thresholds for the default rule set.
    """
    active = ruleset if ruleset is not None else default_ruleset(policy)
    return ValidationReport(
        plan_name=plan.name,
        findings=active.check(plan),
        rules_run=len(active),
    )


def load_plan(path: str | Path) -> TimingPlan:
    """Load a timing plan from a JSON file."""
    with open(path, encoding="utf-8") as handle:
        return TimingPlan.from_dict(json.load(handle))


def validate_file(
    path: str | Path,
    ruleset: RuleSet | None = None,
    policy: Policy = DEFAULT_POLICY,
) -> ValidationReport:
    """Load a plan from ``path`` and validate it."""
    return validate(load_plan(path), ruleset, policy)
