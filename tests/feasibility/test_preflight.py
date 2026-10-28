"""Ac1-ac5 for the pre-flight feasibility checks (FR-041).

One test per acceptance criterion, plain asserts only: every fixture is built
through the bean-002/bean-003 constructors with explicit ids, weights and
capacities, and every assertion reads the project's result — a Finding's kind,
its rule_ids, its message — never the test's own fixture arithmetic.
"""

from __future__ import annotations

from seating_planner.domain import Event, Group, Guest, RsvpStatus, Table
from seating_planner.feasibility import Finding, run_preflight
from seating_planner.rules import Hardness, Rule, RuleKind


def guest(guest_id: str) -> Guest:
    """A confirmed guest: the only status the fixtures need."""
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def table(table_id: str, capacity: int, name: str = "Round") -> Table:
    """A round table at the origin with the given capacity."""
    return Table(
        id=table_id,
        name=name,
        capacity=capacity,
        shape="round",
        position=(0, 0),
    )


def test_contradictory_hard_rules() -> None:
    """ac1: hard same-table and hard different-table on one pair => one
    contradiction naming both rules; the soft pair must produce nothing."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest(f"g{i}") for i in range(1, 6)],
        tables=[table("t1", 4), table("t2", 4)],
        rules=[
            Rule(
                id="r-together",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
            ),
            # Deliberately reversed pair: pair order must not matter.
            Rule(
                id="r-apart",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                guests=("g2", "g1"),
            ),
            Rule(
                id="r-soft",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g3", "g4"),
                weight=10,
            ),
            Rule(
                id="r-soft-apart",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                guests=("g3", "g4"),
            ),
        ],
    )
    findings = run_preflight(event)
    assert len(findings) == 1
    finding: Finding = findings[0]
    assert finding.kind == "contradictory_hard_rules"
    assert finding.rule_ids == ("r-together", "r-apart")
    assert "r-together" in finding.message
    assert "r-apart" in finding.message


def test_group_larger_than_any_table() -> None:
    """ac2: a 7-member group that must stay together against tables of 3 and
    5 => exactly one finding naming the group, the size, and the largest
    capacity; the total capacity (8) must not trip the sum check."""
    event = Event(
        id="e2",
        name="Family wedding",
        guests=[guest(f"g{i}") for i in range(1, 8)],
        tables=[table("t1", 3), table("t2", 5)],
        groups=[
            Group(id="grp1", name="Family", member_ids=[f"g{i}" for i in range(1, 8)])
        ],
        rules=[
            Rule(
                id="r-family",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.HARD,
                group_id="grp1",
            ),
        ],
    )
    findings = run_preflight(event)
    assert len(findings) == 1
    finding: Finding = findings[0]
    assert finding.kind == "group_larger_than_any_table"
    assert finding.rule_ids == ("r-family",)
    assert "grp1" in finding.message
    assert "Family" in finding.message
    assert "must stay together at 7" in finding.message
    assert "seats 5" in finding.message


def test_insufficient_capacity() -> None:
    """ac3: 5 eligible guests and only 4 seats => exactly the pinned finding."""
    event = Event(
        id="e3",
        name="Small wedding",
        guests=[guest(f"g{i}") for i in range(1, 6)],
        tables=[table("t1", 2), table("t2", 2)],
    )
    assert run_preflight(event) == [
        Finding(
            kind="insufficient_capacity",
            message="5 eligible guests but only 4 seats in total",
        ),
    ]


def test_rule_references_missing_target() -> None:
    """ac4: of three min-distance targets, only 'ballroom' is unresolvable;
    the dance floor resolves via the default zone names and 'Main round' via
    an existing table name, so neither of those may be reported."""
    event = Event(
        id="e4",
        name="Evening reception",
        guests=[guest(f"g{i}") for i in range(1, 4)],
        tables=[table("t1", 4, name="Main round"), table("t2", 4)],
        rules=[
            Rule(
                id="r-ghost",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
                target="ballroom",
                min_zones=2,
            ),
            Rule(
                id="r-floor",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.SOFT,
                guests=("g1", "g3"),
                target="dance_floor",
                distance_m=1.5,
                weight=20,
            ),
            Rule(
                id="r-table",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.SOFT,
                guests=("g2", "g3"),
                target="Main round",
                min_zones=1,
                weight=10,
            ),
        ],
    )
    findings = run_preflight(event)
    assert len(findings) == 1
    finding: Finding = findings[0]
    assert finding.kind == "missing_target"
    assert finding.rule_ids == ("r-ghost",)
    assert "r-ghost" in finding.message
    assert "ballroom" in finding.message


def test_feasible_problem_is_clean() -> None:
    """ac5: a small satisfiable event using every rule kind => no findings."""
    event = Event(
        id="e5",
        name="Satisfiable wedding",
        guests=[guest(f"g{i}") for i in range(1, 4)],
        tables=[table("t1", 4, name="Main round")],
        groups=[Group(id="grp", name="Cup", member_ids=["g1", "g2"])],
        rules=[
            Rule(
                id="r-pair",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=30,
            ),
            Rule(
                id="r-group",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                group_id="grp",
                weight=20,
            ),
            Rule(
                id="r-apart",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                guests=("g1", "g3"),
            ),
            Rule(
                id="r-floor",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.HARD,
                guests=("g2", "g3"),
                target="dance_floor",
                min_zones=2,
            ),
        ],
    )
    assert run_preflight(event) == []


if __name__ == "__main__":
    tests = (
        test_contradictory_hard_rules,
        test_group_larger_than_any_table,
        test_insufficient_capacity,
        test_rule_references_missing_target,
        test_feasible_problem_is_clean,
    )
    for test in tests:
        test()
        print(f"{test.__name__}: ok")
    print(f"{len(tests)}/{len(tests)} pre-flight contract tests passed")
