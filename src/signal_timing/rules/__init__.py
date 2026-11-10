"""Validation rules, grouped by the question they answer."""

from ..policy import DEFAULT_POLICY, Policy
from .base import Finding, Rule, RuleSet, Severity
from .coordination import coordination_rules
from .fdot import fdot_rules
from .mutcd import mutcd_rules
from .structure import structure_rules

__all__ = [
    "Finding",
    "Rule",
    "RuleSet",
    "Severity",
    "coordination_rules",
    "fdot_rules",
    "mutcd_rules",
    "structure_rules",
    "default_ruleset",
    "fdot_ruleset",
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


#: Generic adequacy rules replaced by their stricter TEM equivalents.
_SUPERSEDED_BY_FDOT = {
    "ITE-Y-ADEQUACY",
    "ITE-R-ADEQUACY",
    "MUTCD-Y-RANGE",
    "MUTCD-R-RANGE",
}


def fdot_ruleset(policy: Policy = DEFAULT_POLICY) -> RuleSet:
    """Return the FDOT State Highway System rule set.

    Same structural, coordination, and MUTCD range rules as the default set,
    but the ITE adequacy and MUTCD yellow/red range rules are replaced by the
    TEM yellow and red clearance rules (so one problem is not reported twice), and the pedestrian
    reach, countdown, and input-completeness rules are added.
    """
    base = [
        rule
        for rule in [
            *structure_rules(policy),
            *coordination_rules(policy),
            *mutcd_rules(policy),
        ]
        if rule.id not in _SUPERSEDED_BY_FDOT
    ]
    return RuleSet(name="fdot").extend([*base, *fdot_rules(policy)])


#: Named rule sets selectable by ``--standard`` and :func:`validate`.
RULESETS = {"generic": default_ruleset, "fdot": fdot_ruleset}
