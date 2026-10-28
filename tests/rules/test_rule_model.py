"""Acceptance tests for the rule model: round-trip, weights, measures."""

import json

import pytest

from seating_planner.rules import MAX_WEIGHT, MIN_WEIGHT, Hardness, Rule, RuleKind


def make_rule(**overrides: object) -> Rule:
    """A constructible soft same_table rule; override any field under test."""
    base: dict[str, object] = {
        "id": "r-1",
        "kind": RuleKind.SAME_TABLE,
        "hardness": Hardness.SOFT,
        "guests": ("g1", "g2"),
        "weight": 5,
    }
    base.update(overrides)
    return Rule(**base)


def test_all_rule_types_roundtrip() -> None:
    rules = [
        make_rule(
            kind=RuleKind.SAME_TABLE,
            hardness=Hardness.SOFT,
            weight=10,
            guests=("g1", "g2"),
        ),
        make_rule(
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.HARD,
            weight=None,
            group_id="family",
        ),
        make_rule(
            kind=RuleKind.MIN_DISTANCE,
            hardness=Hardness.SOFT,
            weight=40,
            target="dance_floor",
            distance_m=2.5,
        ),
        make_rule(
            kind=RuleKind.ADJACENT_SEAT,
            hardness=Hardness.HARD,
            weight=None,
            guests=("g3", "g4"),
            enabled=False,
        ),
    ]
    for rule in rules:
        rebuilt = Rule.from_dict(json.loads(json.dumps(rule.to_dict())))
        assert rebuilt == rule


def test_soft_weight_bounds() -> None:
    assert make_rule(weight=MIN_WEIGHT).weight == 1
    assert make_rule(weight=MAX_WEIGHT).weight == 100
    for bad_weight in (0, 101, -4, "50", None, True):
        with pytest.raises(ValueError):
            make_rule(weight=bad_weight)


def test_hard_rule_has_no_weight() -> None:
    rule = make_rule(hardness=Hardness.HARD, weight=None)
    assert rule.weight is None
    for bad_weight in (1, 100):
        with pytest.raises(ValueError):
            make_rule(hardness=Hardness.HARD, weight=bad_weight)


def test_min_distance_requires_measure() -> None:
    for overrides in (
        {},
        {"distance_m": "far apart"},
        {"distance_m": 0},
        {"distance_m": -1},
        {"min_zones": 0},
        {"min_zones": "two"},
    ):
        with pytest.raises(ValueError):
            make_rule(
                kind=RuleKind.MIN_DISTANCE,
                weight=10,
                target="dance_floor",
                **overrides,
            )
    assert (
        make_rule(kind=RuleKind.MIN_DISTANCE, weight=10, distance_m=0.5).distance_m
        == 0.5
    )
    assert make_rule(kind=RuleKind.MIN_DISTANCE, weight=10, min_zones=1).min_zones == 1
