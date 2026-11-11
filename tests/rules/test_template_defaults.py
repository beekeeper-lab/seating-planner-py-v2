"""Acceptance tests for the template rule defaults (bean-026, FR-028/029).

After this bean the template's hard accessible-seating rule starts disabled
until seat positions are configured: an event that begins from the template
solves as it stands, and turning the rule on later is setting ``enabled`` to
true — the rule itself is unchanged, so nothing else has to move.
"""

from __future__ import annotations

from seating_planner.domain import Event, Group, Guest, RsvpStatus, Table
from seating_planner.feasibility import run_preflight
from seating_planner.rules import (
    TEMPLATE_CATEGORIES,
    Hardness,
    Rule,
    RuleKind,
    default_wedding_rules,
)
from seating_planner.solver import SolverConfig, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(table_id, f"Table {table_id}", capacity, "round", (0.0, 0.0))


def template_event() -> Event:
    """The bean's measured scenario: three tables of eight, fourteen
    confirmed guests, one group per template category, rules exactly as
    ``default_wedding_rules()`` returns them.
    """
    guests = [guest(f"g{i}") for i in range(1, 15)]
    tables = [table(f"t{i}", 8) for i in range(1, 4)]
    pairs = {
        "couple": ["g1", "g2"],
        "household": ["g3", "g4"],
        "immediate_family": ["g5", "g6"],
        "wedding_party": ["g7", "g8"],
        "children": ["g9", "g10"],
        "vendors": ["g11", "g12"],
        "accessible_seating": ["g1", "g2"],
    }
    groups = [
        Group(id=category, name=category, member_ids=pairs[category])
        for category in TEMPLATE_CATEGORIES
    ]
    return Event(
        id="e1",
        name="Wedding",
        guests=guests,
        tables=tables,
        groups=groups,
        rules=default_wedding_rules(),
    )


def test_template_event_solves() -> None:
    """ac1: the template event solves in planning mode with every guest
    seated, pre-flight reports nothing, and the disabled accessible rule
    has no state at all in the report."""
    event = template_event()
    assert run_preflight(event) == []
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    assert result.unassigned_count == 0
    assert len(result.assignments) == 14
    assert "template-accessible_seating" not in [
        assessment.rule_id for assessment in result.rule_states
    ]


def test_accessible_rule_starts_disabled() -> None:
    """ac2: the accessible rule is present, disabled, and otherwise the same
    rule as before; setting enabled to true alone restores it, and the
    disabled flag survives to_dict and from_dict."""
    accessible = next(
        rule
        for rule in default_wedding_rules()
        if rule.id == "template-accessible_seating"
    )
    assert accessible.enabled is False
    assert accessible.kind is RuleKind.MIN_DISTANCE
    assert accessible.hardness is Hardness.HARD
    assert accessible.weight is None
    assert accessible.guests == ()
    assert accessible.group_id == "accessible_seating"
    assert accessible.target == "dance_floor"
    assert accessible.distance_m is None
    assert accessible.min_zones == 2
    data = accessible.to_dict()
    assert data["enabled"] is False
    assert Rule.from_dict(data) == accessible
    restored = Rule.from_dict({**data, "enabled": True})
    assert restored == Rule(
        id="template-accessible_seating",
        kind=RuleKind.MIN_DISTANCE,
        hardness=Hardness.HARD,
        group_id="accessible_seating",
        weight=None,
        target="dance_floor",
        min_zones=2,
    )


def test_other_template_rules_unchanged() -> None:
    """ac3: the other six rules are unchanged and each starts enabled, and
    the template still returns seven rules, one per category, in order."""
    expected: dict[str, tuple[RuleKind, int | None]] = {
        "couple": (RuleKind.SAME_TABLE, 100),
        "household": (RuleKind.SAME_TABLE, 80),
        "immediate_family": (RuleKind.SAME_TABLE, 60),
        "wedding_party": (RuleKind.SAME_TABLE, 40),
        "children": (RuleKind.SAME_TABLE, 20),
        "vendors": (RuleKind.DIFFERENT_TABLE, 10),
    }
    rules = default_wedding_rules()
    assert [rule.group_id for rule in rules] == list(TEMPLATE_CATEGORIES)
    for rule in rules:
        if rule.group_id not in expected:
            assert rule.id == "template-accessible_seating"
            continue
        kind, weight = expected[rule.group_id]
        assert rule.id == f"template-{rule.group_id}"
        assert rule.kind is kind
        assert rule.hardness is Hardness.SOFT
        assert rule.weight == weight
        assert rule.enabled is True
        assert rule.target is None
        assert rule.distance_m is None
        assert rule.min_zones is None
        assert rule.guests == ()
        assert Rule.from_dict(rule.to_dict()) == rule
