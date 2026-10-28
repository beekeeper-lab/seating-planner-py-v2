"""Acceptance tests for the soft-constraint scoring objective (bean-007).

The solver answers hard constraints first and, among the charts that honour
them all, returns the one with the highest weighted total of satisfied soft
rules (FR-046). Every fixture here is small enough to work out by hand:
each test asserts a specific chart, not a property it merely enumerates.
"""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def rule(
    rule_id: str,
    kind: RuleKind,
    hardness: Hardness,
    guests: tuple[str, ...],
    weight: int | None = None,
) -> Rule:
    return Rule(id=rule_id, kind=kind, hardness=hardness, guests=guests, weight=weight)


def test_higher_score_preferred() -> None:
    """ac1: two valid charts exist and the one with the higher weighted
    soft score wins. g1+g2 together (soft same, weight 10) plus g3 apart
    from g1 (soft different, weight 1) scores 11; keeping g3 with them
    scores 10 and keeping them apart scores 1 — so the optimum is
    unique up to the table swap, and the assertion reads only the
    solver's assignments."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), weight=10),
            rule(
                "r-apart",
                RuleKind.DIFFERENT_TABLE,
                Hardness.SOFT,
                ("g1", "g3"),
                weight=1,
            ),
        ],
    )
    result = solve_hard(event, CONFIG)
    assignments = result.assignments
    assert result.status == "feasible"
    assert assignments, "no assignments returned"
    assert assignments["g1"] == assignments["g2"], (
        f"the weight-10 same-table preference was lost: {assignments}"
    )
    assert assignments["g3"] != assignments["g1"], (
        f"g3 should sit apart from g1 for the extra point: {assignments}"
    )


def test_soft_never_overrides_hard() -> None:
    """ac2: a weight-100 soft rule must never cause a hard rule to break —
    not by winning a chart the hard rule forbids, and not by making a
    provably infeasible event look feasible (a hard rule is a constraint,
    so no weight can trade against it, however large)."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule("r-hard-apart", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g2")),
            rule(
                "r-soft-together",
                RuleKind.SAME_TABLE,
                Hardness.SOFT,
                ("g1", "g2"),
                weight=100,
            ),
        ],
    )
    result = solve_hard(event, CONFIG)
    assignments = result.assignments
    assert result.status == "feasible"
    assert assignments["g1"] != assignments["g2"], (
        f"the weight-100 soft rule bought its way past a hard rule: {assignments}"
    )

    # The same pair, plus a hard same-table rule: with no soft objective
    # this event is infeasible (bean-006 proves it), and staying so is the
    # whole point. If the weight-100 soft preference could buy through,
    # the solver would report a "feasible" chart with the pair together.
    dead = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule("r-hard-together", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-hard-apart", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g2")),
            rule(
                "r-soft-together",
                RuleKind.SAME_TABLE,
                Hardness.SOFT,
                ("g1", "g2"),
                weight=100,
            ),
        ],
    )
    dead_result = solve_hard(dead, CONFIG)
    assert dead_result.status == "infeasible" and dead_result.assignments == {}


def test_conflicting_soft_rules_follow_weight() -> None:
    """ac3: soft rules that cannot all be satisfied are honoured in weight
    order. Same-table (weight 10) beats different-table (weight 1) for the
    same pair — and swapping the weights flips the outcome, which rules
    out a solver that merely happens to like sitting pairs together."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), weight=10),
            rule(
                "r-apart",
                RuleKind.DIFFERENT_TABLE,
                Hardness.SOFT,
                ("g1", "g2"),
                weight=1,
            ),
        ],
    )
    result = solve_hard(event, CONFIG)
    assignments = result.assignments
    assert result.status == "feasible"
    assert assignments["g1"] == assignments["g2"], (
        f"the higher-weight soft rule lost the conflict: {assignments}"
    )

    swapped = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), weight=1),
            rule(
                "r-apart",
                RuleKind.DIFFERENT_TABLE,
                Hardness.SOFT,
                ("g1", "g2"),
                weight=10,
            ),
        ],
    )
    swapped_result = solve_hard(swapped, CONFIG)
    swapped_assignments = swapped_result.assignments
    assert swapped_result.status == "feasible"
    assert swapped_assignments["g1"] != swapped_assignments["g2"], (
        f"swapping the weights did not swap the outcome: {swapped_assignments}"
    )
