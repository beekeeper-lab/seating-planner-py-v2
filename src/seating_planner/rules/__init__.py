"""Structured seating rules: kinds, hardness, soft weights and serialization.

Rule evaluation and solver encoding belong to later beans; this package holds
the rule model (task-1) and the wedding template (task-2).
"""

from .model import MAX_WEIGHT, MIN_WEIGHT, Hardness, Rule, RuleKind

__all__ = [
    "MAX_WEIGHT",
    "MIN_WEIGHT",
    "Hardness",
    "Rule",
    "RuleKind",
]
