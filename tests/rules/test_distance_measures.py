"""Acceptance tests for bean-029: every distance measure a min_distance rule
carries is a real one.

ac3 — a min_distance rule refuses a measure when *any* measure that is given is
invalid (a bad distance_m raises even when min_zones is valid, and a bad
min_zones raises even when distance_m is valid), while the still-valid shapes
build as before and an integer distance_m is stored as a float.

ac4 — the whole existing suite keeps passing unchanged; this file only adds
cases and never alters another module's expectations.
"""

import copy
import json

import pytest

from seating_planner.rules import Hardness, Rule, RuleKind


def make_rule(**overrides: object) -> Rule:
    """A constructible soft min_distance rule; override any field under test.

    The default shape is valid on its own (a target plus a good distance_m),
    so each override changes exactly the measure under test.
    """
    base: dict[str, object] = {
        "id": "r-md",
        "kind": RuleKind.MIN_DISTANCE,
        "hardness": Hardness.SOFT,
        "target": "dance_floor",
        "weight": 10,
        "distance_m": 2.5,
    }
    base.update(overrides)
    return Rule(**base)


def test_every_given_measure_is_valid() -> None:
    # Each given measure answers for itself: a bad one raises even when the
    # other measure is valid.

    # The bean's measured case: a soft rule with a phrase where a number
    # belongs, carried by an otherwise-valid zone count.
    with pytest.raises(ValueError):
        make_rule(distance_m="far apart", min_zones=1)

    # A hard rule with a valid distance but a zero zone count (zero is not
    # "at least one"). This one binds to two guests, not a target.
    with pytest.raises(ValueError):
        make_rule(
            hardness=Hardness.HARD,
            weight=None,
            target=None,
            guests=("g3", "g4"),
            distance_m=3.0,
            min_zones=0,
        )

    # A bad distance with no zone count to fall back on.
    with pytest.raises(ValueError):
        make_rule(distance_m="far apart", min_zones=None)

    # The same bad-measure mappings come back as strings and numbers from a
    # JSON load, so Rule.from_dict must refuse them too.
    bad_mappings: list[dict[str, object]] = [
        {
            "id": "r-md",
            "kind": "min_distance",
            "hardness": "soft",
            "guests": ["g1", "g2"],
            "weight": 10,
            "distance_m": "far apart",
            "min_zones": 1,
        },
        {
            "id": "r-md",
            "kind": "min_distance",
            "hardness": "hard",
            "guests": ["g3", "g4"],
            "weight": None,
            "distance_m": 3.0,
            "min_zones": 0,
        },
        {
            "id": "r-md",
            "kind": "min_distance",
            "hardness": "soft",
            "guests": ["g5", "g6"],
            "weight": 10,
            "distance_m": "far apart",
            "min_zones": None,
        },
    ]
    for data in bad_mappings:
        with pytest.raises(ValueError):
            Rule.from_dict(copy.deepcopy(data))

    # The still-valid shapes build exactly as before.
    assert make_rule(distance_m=2.5, min_zones=None).distance_m == 2.5

    # An integer distance_m is accepted and stored as a float.
    both = make_rule(distance_m=5, min_zones=3)
    assert both.distance_m == 5.0
    assert both.min_zones == 3

    # A zone count alone is still a fully valid measure.
    zones_only = make_rule(distance_m=None, min_zones=3)
    assert zones_only.min_zones == 3
    assert zones_only.distance_m is None

    # A fully valid rule survives a to_dict/Rule.from_dict round trip, as it
    # does across a real JSON load.
    rule = make_rule(distance_m=2.5, min_zones=3)
    rebuilt = Rule.from_dict(json.loads(json.dumps(rule.to_dict())))
    assert rebuilt == rule

    # With neither measure at all the rule is still refused (FR-035).
    with pytest.raises(ValueError):
        make_rule(distance_m=None, min_zones=None)
