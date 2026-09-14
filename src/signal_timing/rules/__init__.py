"""Validation rules, grouped by the question they answer."""

from ..policy import DEFAULT_POLICY, Policy
from .base import Finding, Rule, RuleSet, Severity
from .coordination import coordination_rules
from .mutcd import mutcd_rules
from .structure import structure_rules

__all__ = [
    "Finding",
    "Rule",
    "RuleSet",
    "Severity",
    "coordination_rules",
    "mutcd_rules",
    "structure_rules",
    "default_ruleset",
]


def default_ruleset(policy: Policy = DEFAULT_POLICY) -> RuleSet:
    """Return the full default rule set, bound to ``policy``.

    Structural rules run first: when a plan is arithmetically broken, that is
    usually the finding worth reading before any interval detail.
    """
    return RuleSet(name="default").extend(
        [
            *structure_rules(policy),
            *coordination_rules(policy),
            *mutcd_rules(policy),
        ]
    )
