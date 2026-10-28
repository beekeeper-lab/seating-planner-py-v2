"""Acceptance tests for the default wedding rule template."""

from seating_planner.rules import (
    MAX_WEIGHT,
    MIN_WEIGHT,
    TEMPLATE_CATEGORIES,
    Hardness,
    Rule,
    RuleKind,
    default_wedding_rules,
)


def test_default_wedding_template() -> None:
    rules = default_wedding_rules()
    assert len(rules) == len(TEMPLATE_CATEGORIES) == 7
    assert all(isinstance(rule, Rule) for rule in rules)

    for category, rule in zip(TEMPLATE_CATEGORIES, rules, strict=True):
        assert rule.id == f"template-{category}"
        assert rule.group_id == category
        assert rule.enabled is True
        assert Rule.from_dict(rule.to_dict()) == rule

    for category in (
        "couple",
        "household",
        "immediate_family",
        "wedding_party",
        "children",
    ):
        rule = rules[TEMPLATE_CATEGORIES.index(category)]
        assert rule.kind is RuleKind.SAME_TABLE
        assert rule.hardness is Hardness.SOFT
        assert rule.weight is not None
        assert isinstance(rule.weight, int) and not isinstance(rule.weight, bool)
        assert MIN_WEIGHT <= rule.weight <= MAX_WEIGHT

    vendors = rules[TEMPLATE_CATEGORIES.index("vendors")]
    assert vendors.kind is RuleKind.DIFFERENT_TABLE
    assert vendors.hardness is Hardness.SOFT

    accessible = rules[TEMPLATE_CATEGORIES.index("accessible_seating")]
    assert accessible.kind is RuleKind.MIN_DISTANCE
    assert accessible.hardness is Hardness.HARD
    assert accessible.weight is None
    assert accessible.target == "dance_floor"
    assert accessible.distance_m is None
    assert accessible.min_zones == 2

    first = default_wedding_rules()
    first[0].enabled = False
    assert default_wedding_rules()[0].enabled is True
