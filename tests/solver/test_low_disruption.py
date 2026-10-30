"""Acceptance tests for the low-disruption mode (FR-066).

Five tests, one per acceptance criterion:

* ac1 — the movement limit is binding exactly: two locked guests force
  exactly two moves, the solver seats the third guest where they are,
  and the chart and its score are the ones only that chart can produce;
* ac2 — fewer moves beats a higher score: an explicit two-move chart
  scoring 200 exists inside the limit of two, but the two-level
  objective refuses to buy it and keeps the untouched chart;
* ac3 — the score breaks a tie on move count: two charts move exactly
  the same guests-count and only the one that satisfies both soft rules
  wins;
* ac4 — a limit-caused refutation is proven and names its cause: the
  infeasibility report carries an empty clash and a recommendation to
  raise the movement limit, and no capacity-shaped recommendation;
* ac5 — a zero limit changes nothing: the tempting one-move chart is
  outside the limit and the current chart comes back untouched.

Every fixture in this module is small enough to work out by hand, and
each test asserts a specific chart, not a property it merely enumerates.
"""

from __future__ import annotations

from collections.abc import Mapping

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import LOW_DISRUPTION

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


def same_rule(rule_id: str, guests: tuple[str, ...], weight: int) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.SAME_TABLE,
        hardness=Hardness.SOFT,
        guests=guests,
        weight=weight,
    )


def moved_count(assignments: Mapping[str, str], current: Mapping[str, str]) -> int:
    """How many guests the result sits somewhere other than the current chart."""
    return sum(
        1
        for guest_id, table_id in current.items()
        if assignments.get(guest_id) != table_id
    )


def test_movement_limit_respected() -> None:
    """ac1: the limit binds exactly and the chart is decided by the model.
    g1, g2 and g3 all sit at t1 (t1 holds three, t2 holds three); the soft
    rules (g1, g2) weight 100, (g1, g3) weight 50 and (g2, g3) weight 10
    all want the trio together. g1 and g2 are locked to t2, so both of
    them must move: that is exactly two moves, while filling t2 with all
    three would cost three and is outside the limit of two. So g3 stays,
    the chart is g1, g2 at t2 and g3 at t1, and the only rule satisfied
    is (g1, g2): soft_score 100."""
    current = {"g1": "t1", "g2": "t1", "g3": "t1"}
    event = Event(
        id="e-ac1",
        name="Limit binds exactly",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[
            same_rule("r-g1g2", ("g1", "g2"), 100),
            same_rule("r-g1g3", ("g1", "g3"), 50),
            same_rule("r-g2g3", ("g2", "g3"), 10),
        ],
    )
    event.lock_guest("g1", "t2")
    event.lock_guest("g2", "t2")

    result = solve_hard(
        event, CONFIG, mode=LOW_DISRUPTION, current_assignments=current, move_limit=2
    )

    assert result.status == "feasible", (
        f"two locked moves fit the limit of two, so a chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t2", "g2": "t2", "g3": "t1"}, (
        f"the locks put g1 and g2 at t2 and the third move would break "
        f"the limit, so g3 must stay, got {result.assignments!r}"
    )
    assert moved_count(result.assignments, current) == 2, (
        f"exactly the two locked guests change tables, "
        f"got {moved_count(result.assignments, current)} moves"
    )
    assert result.soft_score == 100, (
        f"only the (g1, g2) pair shares a table in this chart, "
        f"got soft_score {result.soft_score}"
    )


def test_fewer_moves_beats_higher_score() -> None:
    """ac2: the objective refuses to buy score with disruption. g1 and g2
    sit at t1, g3 and g4 at t2 (both tables hold four); the soft rules
    (g1, g3) weight 100 and (g2, g4) weight 100 are both unsatisfied by
    the current chart. Charts at two moves exist that score 200 — for
    instance seating g1 at t2 with g3 and g4 at t1 with g2 — and two is
    the limit, so the tempting chart is inside the limit. The two-level
    objective optimises moves first, though: the untouched chart moves
    zero guests and wins, with soft_score 0."""
    current = {"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2"}
    event = Event(
        id="e-ac2",
        name="No buying score with moves",
        guests=[guest(f"g{i}") for i in range(1, 5)],
        tables=[table("t1", 4), table("t2", 4)],
        rules=[
            same_rule("r-g1g3", ("g1", "g3"), 100),
            same_rule("r-g2g4", ("g2", "g4"), 100),
        ],
    )

    result = solve_hard(
        event, CONFIG, mode=LOW_DISRUPTION, current_assignments=current, move_limit=2
    )

    assert result.status == "feasible", (
        f"the current chart is a chart, so the event is feasible, "
        f"got status {result.status!r}"
    )
    assert result.assignments == current, (
        f"a zero-move chart beats the two-move 200-point chart under the "
        f"two-level objective, so nothing moves, got {result.assignments!r}"
    )
    assert moved_count(result.assignments, current) == 0, (
        f"no guest may change tables when the current chart is valid, "
        f"got {moved_count(result.assignments, current)} moves"
    )
    assert result.soft_score == 0, (
        f"neither soft pair shares a table in the current chart, "
        f"got soft_score {result.soft_score}"
    )


def test_score_breaks_tie_on_moves() -> None:
    """ac3: equal move counts are decided by the score alone. g1 and g2
    sit at t1 (t1 holds two), g3, g4 and g5 at t2 (t2 holds three); the
    soft rules (g2, g4) and (g1, g3) both weigh 100 and neither pair
    shares a table. g3 is locked to t1, and t1 already holds two guests,
    so exactly one more guest may join g3 there: moving g2 over with g3
    is a two-move chart worth 0, while moving g1 over with g3 leaves
    g2 at t2 with g4 and both pairs together — the same two moves, 200
    points. The only other valid shapes re-seat four guests — all
    scoring 0 — so the limit is not binding; the tie-break alone decides,
    and the 200-point chart wins."""
    current = {"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2", "g5": "t2"}
    event = Event(
        id="e-ac3",
        name="Score breaks the tie",
        guests=[guest(f"g{i}") for i in range(1, 6)],
        tables=[table("t1", 2), table("t2", 3)],
        rules=[
            same_rule("r-g2g4", ("g2", "g4"), 100),
            same_rule("r-g1g3", ("g1", "g3"), 100),
        ],
    )
    event.lock_guest("g3", "t1")

    result = solve_hard(
        event, CONFIG, mode=LOW_DISRUPTION, current_assignments=current, move_limit=4
    )

    assert result.status == "feasible", (
        f"two moves satisfy the capacity and the lock, so a chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {
        "g1": "t1",
        "g2": "t2",
        "g3": "t1",
        "g4": "t2",
        "g5": "t2",
    }, (
        f"between the two two-move shapes only g1 joining g3 at t1 "
        f"satisfies both rules, got {result.assignments!r}"
    )
    assert moved_count(result.assignments, current) == 2, (
        f"both winning shapes move g3 plus exactly one of g1 and g2, "
        f"got {moved_count(result.assignments, current)} moves"
    )
    assert result.soft_score == 200, (
        f"both soft pairs share a table in the winning chart, "
        f"got soft_score {result.soft_score}"
    )


def test_limit_infeasibility_names_its_cause() -> None:
    """ac4: when the limit is the cause, the refutation names it. g1 and
    g2 sit at t1 (t1 holds two), g3 and g4 at t2 (t2 holds three); there
    are no rules, and g3 is locked to t1. The lock sends g3 onto a full
    t1, so one of g1 or g2 has to move too: two moves are the minimum,
    against a limit of one — an infeasibility with no rule clash. The
    event has five seats for four guests, so capacity alone is fine: the
    same event solved with a limit of two is feasible and binds at
    exactly those two moves. The report must therefore carry an empty
    clash, a raise-the-movement-limit recommendation naming the one, and
    no capacity-shaped recommendation at all."""
    current = {"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2"}

    def build_event(event_id: str) -> Event:
        event = Event(
            id=event_id,
            name="Limit is the cause",
            guests=[guest(f"g{i}") for i in range(1, 5)],
            tables=[table("t1", 2), table("t2", 3)],
            rules=[],
        )
        event.lock_guest("g3", "t1")
        return event

    relaxed = solve_hard(
        build_event("e-ac4-relaxed"),
        CONFIG,
        mode=LOW_DISRUPTION,
        current_assignments=current,
        move_limit=2,
    )
    assert relaxed.status == "feasible", (
        f"five seats for four guests and a limit of two: the lock plus "
        f"one displaced guest fits, got status {relaxed.status!r}"
    )
    assert moved_count(relaxed.assignments, current) == 2, (
        f"the lock and one displaced guest are exactly the two moves the "
        f"limit of two allows, got {moved_count(relaxed.assignments, current)} moves"
    )

    result = solve_hard(
        build_event("e-ac4"),
        CONFIG,
        mode=LOW_DISRUPTION,
        current_assignments=current,
        move_limit=1,
    )

    assert result.status == "infeasible", (
        f"the lock needs a second move that the limit of one forbids, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {}, (
        f"a proven refutation never hands back a partial chart, "
        f"got {result.assignments!r}"
    )
    report = result.infeasibility_report
    assert report is not None, "an infeasible result must carry its report"
    assert report.conflict_rule_ids == (), (
        f"no rule is in conflict with the lock and the limit; the clash "
        f"is purely a movement one, got {report.conflict_rule_ids!r}"
    )
    raise_recs = [
        rec for rec in report.recommendations if rec.kind == "raise_movement_limit"
    ]
    assert raise_recs, (
        f"the proven cause is the movement limit, so the report must "
        f"recommend raising it, got {report.recommendations!r}"
    )
    assert any("1" in rec.detail for rec in raise_recs), (
        f"the recommendation must name the offending numeric limit of 1, "
        f"got {[rec.detail for rec in raise_recs]!r}"
    )
    capacity_recs = [
        rec
        for rec in report.recommendations
        if rec.kind in ("add_capacity", "add_table")
    ]
    assert capacity_recs == [], (
        f"five seats for four guests: the named cause is the limit, not "
        f"capacity, got {capacity_recs!r}"
    )


def test_zero_limit_changes_nothing() -> None:
    """ac5: a zero limit makes every current placement load-bearing. g1
    and g2 sit at t1 (t1 holds three), g3 at t2 (t2 holds two); the soft
    rule (g1, g3) weight 100 wants g3 at t1 with g1. Seating g3 at t1
    would earn the 100 points, but it costs one move — and the limit is
    zero, so it is not on offer. The only chart that moves no one is the
    current chart itself: the solve returns it untouched, with
    soft_score 0."""
    current = {"g1": "t1", "g2": "t1", "g3": "t2"}
    event = Event(
        id="e-ac5",
        name="Zero limit",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3), table("t2", 2)],
        rules=[same_rule("r-g1g3", ("g1", "g3"), 100)],
    )

    result = solve_hard(
        event, CONFIG, mode=LOW_DISRUPTION, current_assignments=current, move_limit=0
    )

    assert result.status == "feasible", (
        f"the current chart moves no one and the limit is zero, "
        f"got status {result.status!r}"
    )
    assert result.assignments == current, (
        f"every moved chart costs at least one move, so the current "
        f"chart must come back unchanged, got {result.assignments!r}"
    )
    assert moved_count(result.assignments, current) == 0, (
        f"a zero limit admits no moves, "
        f"got {moved_count(result.assignments, current)} moves"
    )
    assert result.soft_score == 0, (
        f"g3 and g1 do not share a table when nothing moves, "
        f"got soft_score {result.soft_score}"
    )
