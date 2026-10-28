"""The default wedding rule template: one rule per guest group (FR-028/029).

A new wedding event can start from :func:`default_wedding_rules` and the
organizer turns each preference off or retunes its weight independently, so
every call returns fresh, individually enable-able objects bound to their
category group. ``accessible_seating`` is the template's only hard rule and
its only min_distance rule.
"""

from __future__ import annotations

from .model import Hardness, Rule, RuleKind

#: The template's categories, in order; the order is load-bearing.
TEMPLATE_CATEGORIES: tuple[str, ...] = (
    "couple",
    "household",
    "immediate_family",
    "wedding_party",
    "children",
    "vendors",
    "accessible_seating",
)

#: Soft weights for the template's soft rules, by category. Descending from
#: couple; hard rules (accessible_seating) carry no weight.
_TEMPLATE_WEIGHTS: dict[str, int] = {
    "couple": 100,
    "household": 80,
    "immediate_family": 60,
    "wedding_party": 40,
    "children": 20,
    "vendors": 10,
}


def default_wedding_rules() -> list[Rule]:
    """Build the default wedding template, one fresh rule per category."""
    rules: list[Rule] = []
    for category in TEMPLATE_CATEGORIES:
        if category == "accessible_seating":
            rule = Rule(
                id=f"template-{category}",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.HARD,
                group_id=category,
                weight=None,
                target="dance_floor",
                min_zones=2,
            )
        elif category == "vendors":
            rule = Rule(
                id=f"template-{category}",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.SOFT,
                group_id=category,
                weight=_TEMPLATE_WEIGHTS[category],
            )
        else:
            rule = Rule(
                id=f"template-{category}",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                group_id=category,
                weight=_TEMPLATE_WEIGHTS[category],
            )
        rules.append(rule)
    return rules
