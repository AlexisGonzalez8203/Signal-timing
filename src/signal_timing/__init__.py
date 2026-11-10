"""Validation of traffic signal timing parameters and operational compliance."""

from .intervals import (
    pedestrian_change_interval,
    red_clearance_interval,
    total_pedestrian_time,
    yellow_change_interval,
)
from .model import Approach, Phase, PlanStructureError, TimingPlan
from .policy import DEFAULT_POLICY, Policy
from .report import ValidationReport
from .rules import Finding, RuleSet, Severity, default_ruleset, fdot_ruleset
from .validator import load_plan, validate, validate_file

__version__ = "0.1.0"

__all__ = [
    "Approach",
    "DEFAULT_POLICY",
    "Finding",
    "Phase",
    "PlanStructureError",
    "Policy",
    "RuleSet",
    "Severity",
    "TimingPlan",
    "ValidationReport",
    "default_ruleset",
    "fdot_ruleset",
    "load_plan",
    "pedestrian_change_interval",
    "red_clearance_interval",
    "total_pedestrian_time",
    "validate",
    "validate_file",
    "yellow_change_interval",
    "__version__",
]
