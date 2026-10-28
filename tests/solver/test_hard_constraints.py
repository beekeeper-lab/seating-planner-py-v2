"""Acceptance tests for hard-constraint table assignment (bean-006, ac1-ac5)."""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(
    guest_id: str,
    status: RsvpStatus = RsvpStatus.CONFIRMED,
    reserved: bool = False,
) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=status,
        seat_reserved=reserved,
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
    rule_id: str, kind: RuleKind, hardness: Hardness, guests: tuple[str, ...]
) -> Rule:
    return Rule(id=rule_id, kind=kind, hardness=hardness, guests=guests)


def _counts(assignments: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_id in assignments.values():
        counts[table_id] = counts.get(table_id, 0) + 1
    return counts


def test_all_eligible_guests_assigned() -> None:
    """ac1: 5 eligible guests, 7 seats, satisfiable rules => everyone seated."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest(f"g{i}") for i in range(1, 6)],
        tables=[table("t1", 3), table("t2", 4)],
        rules=[
            rule("r1", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r2", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g3", "g4")),
        ],
    )
    result = solve_hard(event, CONFIG)
    assert result.status == "feasible"
    assert set(result.assignments) == {f"g{i}" for i in range(1, 6)}
    for guest_id, table_id in result.assignments.items():
        assert table_id in {"t1", "t2"}, (
            f"guest {guest_id} sent to unknown table {table_id!r}"
        )


def test_capacity_never_exceeded() -> None:
    """ac2: 7 eligible guests, 7 seats, a trio forced together => exact packing."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest(f"g{i}") for i in range(1, 8)],
        tables=[table("t1", 3), table("t2", 4)],
        rules=[
            rule("r1", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2", "g3")),
        ],
    )
    result = solve_hard(event, CONFIG)
    assert result.status == "feasible"
    counts = _counts(result.assignments)
    # 7 guests over 7 seats (3+4, the trio cannot fit both tables): each
    # table is forced to be exactly full, no more — overfilling is impossible.
    assert counts == {"t1": 3, "t2": 4}


def test_same_and_different_table_rules() -> None:
    """ac3: a hard same-table pair shares a table; a hard different pair does not."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest(f"g{i}") for i in range(1, 5)],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-diff", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g3", "g4")),
        ],
    )
    result = solve_hard(event, CONFIG)
    assert result.status == "feasible"
    assert result.assignments["g1"] == result.assignments["g2"]
    assert result.assignments["g3"] != result.assignments["g4"]


def test_ineligible_guests_unassigned() -> None:
    """ac4: confirmed and reserved-pending guests are seated; the rest never are."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[
            guest("g1"),
            guest("g2"),
            guest("g3"),
            guest("g4", status=RsvpStatus.DECLINED),
            guest("g5", status=RsvpStatus.PENDING),
            guest("g6", status=RsvpStatus.PENDING, reserved=True),
        ],
        tables=[table("t1", 6)],
    )
    result = solve_hard(event, CONFIG)
    assert result.status == "feasible"
    assert "g4" not in result.assignments
    assert "g5" not in result.assignments
    assert set(result.assignments) == {"g1", "g2", "g3", "g6"}


def test_infeasible_returns_no_assignment() -> None:
    """ac5: a hard same-table and hard different-table rule on one pair => no chart."""
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest(f"g{i}") for i in range(1, 5)],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-diff", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g2")),
        ],
    )
    result = solve_hard(event, CONFIG)
    assert result.status == "infeasible"
    assert result.assignments == {}
