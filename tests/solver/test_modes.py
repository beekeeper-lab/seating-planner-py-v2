"""Acceptance tests for the explicit optimization mode (FR-059).

Five tests: one per acceptance criterion (ac1 through ac4) plus the
reject-side — an unsupported mode value is refused before any solving:

* ac1 — the mode is a required keyword: calling solve_hard without it
  is a TypeError, so a caller can never silently run a mode;
* ac2 — planning moves an unlocked guest: on the lock/unlock fixtures
  (bean-011) the lock forces the weight-100 soft rule to score 0, and
  unlocking moves exactly enough guests to score it 100;
* ac3 — planning respects locks: the locked trio (bean-011) stays at
  t1 against a proven 200-point optimum that would move them;
* ac4 — the result records the mode it was solved under, feasible and
  infeasible alike, and the mode survives round-tripping to a dict.

Every fixture is small enough to work out by hand and reuses arithmetic
already proven in this repository's passing suite: the ac2 pair of
solves is the lock/unlock fixture of tests/solver/test_locks.py, the
ac3 fixture is that file's locked-trio fixture, each with the mode
keyword added.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import PLANNING

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


def test_mode_is_required() -> None:
    """ac1: the optimization mode is an explicit, required choice — a
    small feasible event (two guests, one two-seat table, no rules)
    cannot be solved without naming a mode, and the omission is a
    TypeError rather than a default the caller never chose."""
    event = Event(
        id="e-ac1",
        name="No default mode",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
        rules=[],
    )

    with pytest.raises(TypeError):
        solve_hard(event, CONFIG)


def test_planning_moves_unlocked_guest() -> None:
    """ac2: planning moves a guest the moment its lock is released. The
    lock/unlock fixtures — t1 one seat, t2 three seats, a weight-100
    soft same-table rule over g1 g2 g3 — score 0 while g1 is locked at
    t1 (only two of the three can share a table), and the moment g1 is
    explicitly unlocked the solver moves it: all three come out at t2
    and the rule scores 100. The unlocked guest moved exactly because
    releasing it improved the score."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Planning moves the unlocked guest",
            guests=[guest("g1"), guest("g2"), guest("g3")],
            tables=[table("t1", 1), table("t2", 3)],
            rules=[
                rule(
                    "r-same",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g1", "g2", "g3"),
                    weight=100,
                ),
            ],
        )

    locked_event = build_event("e-ac2-locked")
    locked_event.lock_guest("g1", "t1")

    locked = solve_hard(locked_event, CONFIG, mode=PLANNING)
    assert locked.status == "feasible", (
        f"one locked guest, four seats, no hard rule: a chart exists, "
        f"got status {locked.status!r}"
    )
    assert locked.assignments.get("g1") == "t1", (
        f"g1 is locked at t1, so it sits there, got {locked.assignments!r}"
    )
    assert locked.assignments.get("g2") == "t2", (
        f"t1 holds the locked g1 and exactly one seat, so g2 sits at t2, "
        f"got {locked.assignments!r}"
    )
    assert locked.assignments.get("g3") == "t2", (
        f"t1 holds the locked g1 and exactly one seat, so g3 sits at t2, "
        f"got {locked.assignments!r}"
    )
    assert locked.soft_score == 0, (
        f"the lock breaks the weight-100 same-table rule — only two of "
        f"the three guests share a table, got soft_score {locked.soft_score}"
    )

    locked_event.unlock_guest("g1")
    unlocked = solve_hard(locked_event, CONFIG, mode=PLANNING)
    assert unlocked.status == "feasible", (
        f"releasing the lock leaves the event seatable, got status {unlocked.status!r}"
    )
    for guest_id in ("g1", "g2", "g3"):
        assert unlocked.assignments.get(guest_id) == "t2", (
            f"t2 is the only table that fits all three of the guests "
            f"together, so after unlock {guest_id} sits there; "
            f"got {unlocked.assignments!r}"
        )
    assert unlocked.soft_score == 100, (
        f"all three guests share t2, so the weight-100 rule is satisfied, "
        f"got soft_score {unlocked.soft_score}"
    )


def test_planning_respects_locks() -> None:
    """ac3: planning honours locks against a proven optimum. Six guests
    over two three-seat tables, three weight-100 soft same-table rules
    on the pairs (g1, g4) (g2, g5) (g3, g6): the unlocked optimum
    scores 200 and it must never want the trio g1 g2 g3 together at t1
    — otherwise the locks below would hold nothing. Lock the trio at t1
    and planning keeps every one of them there, feasible."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Locked trio",
            guests=[guest(f"g{i}") for i in range(1, 7)],
            tables=[table("t1", 3), table("t2", 3)],
            rules=[
                rule(
                    "r-above",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g1", "g4"),
                    weight=100,
                ),
                rule(
                    "r-mid",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g2", "g5"),
                    weight=100,
                ),
                rule(
                    "r-below",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g3", "g6"),
                    weight=100,
                ),
            ],
        )

    unlocked = solve_hard(build_event("e-ac3-unlocked"), CONFIG, mode=PLANNING)
    assert unlocked.status == "feasible", (
        f"the locked-trio event has a chart, got status {unlocked.status!r}"
    )
    assert unlocked.soft_score == 200, (
        f"two of the three soft pairs share a table at the optimum, "
        f"got soft_score {unlocked.soft_score}"
    )
    trio_at_t1 = sorted(
        g for g in ("g1", "g2", "g3") if unlocked.assignments.get(g) == "t1"
    )
    assert trio_at_t1 != ["g1", "g2", "g3"], (
        f"If every soft pair sat below at t2, t1 would need all of "
        "g1 g2 g3 together — which the rules forbid — so the optimum "
        f"cannot put the trio at t1, got {trio_at_t1!r}"
    )

    locked_event = build_event("e-ac3-locked")
    for guest_id in ("g1", "g2", "g3"):
        locked_event.lock_guest(guest_id, "t1")

    locked = solve_hard(locked_event, CONFIG, mode=PLANNING)
    assert locked.status == "feasible", (
        f"locking the trio at t1 still leaves every pair a table, "
        f"got status {locked.status!r}"
    )
    for guest_id in ("g1", "g2", "g3"):
        assert locked.assignments.get(guest_id) == "t1", (
            f"{guest_id} is locked at t1, so planning must not move it "
            f"even though the unlocked optimum would, got "
            f"{locked.assignments!r}"
        )


def test_result_records_mode() -> None:
    """ac4: the result records the mode it was solved under. A small
    feasible event solved in planning mode carries mode == PLANNING on
    the result and in its dict; a proven infeasible one — three guests,
    a single one-seat table — is infeasible and still records the mode."""
    event = Event(
        id="e-ac4",
        name="Result records the mode",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
        rules=[],
    )

    result = solve_hard(event, CONFIG, mode=PLANNING)
    assert result.status == "feasible", (
        f"two guests at a two-seat table: a chart exists, got status {result.status!r}"
    )
    assert result.mode == PLANNING, (
        f"the result was solved in planning mode and must say so, "
        f"got mode {result.mode!r}"
    )
    assert result.to_dict()["mode"] == PLANNING, (
        f"the mode survives the dict round-trip, got {result.to_dict()['mode']!r}"
    )

    infeasible = Event(
        id="e-ac4-infeasible",
        name="Three guests, one seat",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 1)],
        rules=[],
    )
    failed = solve_hard(infeasible, CONFIG, mode=PLANNING)
    assert failed.status == "infeasible", (
        f"three guests cannot fit a one-seat table, got status {failed.status!r}"
    )
    assert failed.mode == PLANNING, (
        f"an infeasible result was also solved in planning mode and "
        f"records it, got mode {failed.mode!r}"
    )


def test_unsupported_mode_rejected() -> None:
    """An unsupported mode is rejected before any solving — a small feasible event with mode='bogus' raises
    ValueError, and the message names the rejected value so the caller
    sees what it passed, not only that it was wrong."""
    event = Event(
        id="e-ac5",
        name="Unsupported mode",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
        rules=[],
    )

    with pytest.raises(ValueError, match="bogus"):
        solve_hard(event, CONFIG, mode="bogus")
