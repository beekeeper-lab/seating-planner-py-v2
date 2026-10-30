"""Acceptance tests for the event-day mode (FR-067, FR-071).

Six tests: the five acceptance criteria plus one infeasible-report
test:

* ac1 — a new guest takes the one open seat that scores the soft rule,
  and the existing assignments come back exactly where they were;
* ac2 — existing assignments are pinned even though nothing was ever
  explicitly locked, and the same event solved in planning mode proves
  the pinning — not an explicit lock — is what holds g1;
* ac3 — cancelling a guest frees their seat without moving anyone: the
  chart comes back exactly as it was minus the cancelled guest, with
  soft_score 0 although a 100-point shuffle into the freed seat is
  feasible;
* ac4 — the one explicitly unlocked guest may move, and does, to earn
  the soft rule, while everyone else stays in place;
* ac5 — a new guest is placed away from a hard rule's reach even
  though the soft rule tempts them onto the forbidden table, and the
  event without the hard rule proves the temptation was real;
* infeasible — with the only table full and no other table at all, the
  solve proves infeasible as a structural capacity failure: no
  conflicting rule ids and an add-capacity recommendation.

Every event-day call uses the string literal mode="event_day": the
mode constant does not exist until the mode is implemented, and
importing it now would break collection of this whole module. Every
fixture is small enough to work out by hand, and each test asserts a
specific chart and a specific soft score, not a property it merely
enumerates.
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


def same_rule(rule_id: str, guests: tuple[str, ...], weight: int) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.SAME_TABLE,
        hardness=Hardness.SOFT,
        guests=guests,
        weight=weight,
    )


def different_table_rule(rule_id: str, guests: tuple[str, ...]) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.DIFFERENT_TABLE,
        hardness=Hardness.HARD,
        guests=guests,
    )


def test_new_guest_takes_open_seat() -> None:
    """ac1: the new guest takes the one seat that scores, nobody moves.
    g1 and g2 sit at t1 (t1 holds three, t2 holds three); g3 is a new
    arrival, not in the baseline; the one soft rule wants g1, g2 and
    g3 at one table, weight 100. All three can share only t1 — g1 and
    g2 are already there and t2 would leave them apart — and t1 has
    exactly the room: g3 at t1 scores 100, g3 at t2 scores 0. The
    winning chart is all three at t1, with g1 and g2 exactly where
    they were."""
    current = {"g1": "t1", "g2": "t1"}
    event = Event(
        id="e-ac1",
        name="New guest, open seat",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[same_rule("r-g1g2g3", ("g1", "g2", "g3"), 100)],
    )

    result = solve_hard(event, CONFIG, mode="event_day", current_assignments=current)

    assert result.status == "feasible", (
        f"t1 holds two of the three guests and has room for the third, "
        f"so a chart exists, got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g2": "t1", "g3": "t1"}, (
        f"the only chart that satisfies the weight-100 rule seats the "
        f"new g3 at t1 with the rest, got {result.assignments!r}"
    )
    assert result.soft_score == 100, (
        f"all three guests share t1 in the winning chart, "
        f"got soft_score {result.soft_score}"
    )


def test_existing_assignments_implicitly_locked() -> None:
    """ac2: the current chart is pinned with no explicit lock set. g1
    sits at t1 (t1 holds one), g2 and g3 at t2 (t2 holds three); no
    lock_guest call is made anywhere, and the test asserts the event
    actually carries no lock. The soft rule wants all three together,
    weight 100. In event_day, g1 counts as locked to t1, and t1 holds
    exactly one guest — the trio can never share a table, so the
    current chart comes back unchanged with soft_score 0. The contrast
    in the same test: the identical event solved in planning mode has
    nothing holding g1, so all three move to t2 and the rule scores
    100 — the difference is the implicit locking alone."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Implicitly locked",
            guests=[guest("g1"), guest("g2"), guest("g3")],
            tables=[table("t1", 1), table("t2", 3)],
            rules=[same_rule("r-g1g2g3", ("g1", "g2", "g3"), 100)],
        )

    current = {"g1": "t1", "g2": "t2", "g3": "t2"}

    event = build_event("e-ac2")
    for g in event.guests:
        assert g.locked_to_table is None, (
            f"nothing in this fixture is explicitly locked, so "
            f"{g.id} carries no lock, got {g.locked_to_table!r}"
        )

    result = solve_hard(event, CONFIG, mode="event_day", current_assignments=current)

    assert result.status == "feasible", (
        f"the current chart honours every capacity, so a chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == current, (
        f"event_day treats every current assignment as locked, so "
        f"nothing moves, got {result.assignments!r}"
    )
    assert result.soft_score == 0, (
        f"g1 sits at the one-seat t1 while g2 and g3 sit at t2, so the "
        f"weight-100 rule is unsatisfied, got soft_score {result.soft_score}"
    )

    planned = solve_hard(build_event("e-ac2-planning"), CONFIG, mode=PLANNING)
    assert planned.status == "feasible", (
        f"the same event in planning mode is seatable, got status {planned.status!r}"
    )
    assert planned.assignments == {"g1": "t2", "g2": "t2", "g3": "t2"}, (
        f"with nothing locked, t2 is the only table that fits the trio, "
        f"got {planned.assignments!r}"
    )
    assert planned.soft_score == 100, (
        f"the planning solve seats the trio together at t2, "
        f"got soft_score {planned.soft_score}"
    )


def test_cancellation_moves_nobody() -> None:
    """ac3: cancelling a guest frees their seat and moves no one. g1
    sits at t1 (t1 holds two), g2 and g3 at t2 (t2 holds two); the
    soft rule wants g1 and g3 together, weight 100, unsatisfied by the
    current chart. Solving the full chart moves nothing: everyone is
    pinned, soft_score 0. Then g2 cancels: a second event is built
    without g2, baseline {g1: t1, g3: t2}. The freed seat at t2 makes
    a genuine 100-point shuffle feasible — move g3 to t1 with g1 — but
    the mode must refuse it: the chart comes back {g1: t1, g3: t2}
    with soft_score 0 and no trace of g2, because the freed seat is
    simply empty and nobody is moved to fill it."""
    current = {"g1": "t1", "g2": "t2", "g3": "t2"}
    full = Event(
        id="e-ac3",
        name="Before the cancellation",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[same_rule("r-g1g3", ("g1", "g3"), 100)],
    )

    before = solve_hard(full, CONFIG, mode="event_day", current_assignments=current)
    assert before.status == "feasible", (
        f"the current chart honours every capacity, so a chart exists, "
        f"got status {before.status!r}"
    )
    assert before.assignments == current, (
        f"with everyone pinned, no one moves, got {before.assignments!r}"
    )
    assert before.soft_score == 0, (
        f"g1 and g3 sit at different tables in the pinned chart, "
        f"got soft_score {before.soft_score}"
    )

    after_event = Event(
        id="e-ac3-after",
        name="After the cancellation",
        guests=[guest("g1"), guest("g3")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[same_rule("r-g1g3", ("g1", "g3"), 100)],
    )
    after_current = {"g1": "t1", "g3": "t2"}

    result = solve_hard(
        after_event, CONFIG, mode="event_day", current_assignments=after_current
    )

    assert result.status == "feasible", (
        f"two guests over four seats: a chart exists, got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g3": "t2"}, (
        f"the cancellation frees g2's seat but moves no other guest — "
        f"the 100-point shuffle of g3 to t1 must not happen, got "
        f"{result.assignments!r}"
    )
    assert result.soft_score == 0, (
        f"g3 stays at t2 with g1 at t1, so the weight-100 rule is "
        f"deliberately left unsatisfied, got soft_score {result.soft_score}"
    )
    assert "g2" not in result.assignments, (
        f"the cancelled guest is absent from the event and from the "
        f"chart, got {result.assignments!r}"
    )


def test_explicit_unlock_permits_move() -> None:
    """ac4: the explicit unlock is the one exception to the pinning.
    The ac2 fixture again — g1 at the one-seat t1, g2 and g3 at t2,
    the weight-100 rule over the trio, nothing explicitly locked —
    now the event_day solve names g1 in unlocked_guest_ids, so g1 is a
    free variable: t2 is the only table that fits all three together
    and t1 holds one seat, so the only chart that scores is all three
    at t2, soft_score 100. g2 and g3 are not in the unlocked set, so
    they stay where the baseline put them — and they were already at
    t2, so they have not moved."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Explicit unlock",
            guests=[guest("g1"), guest("g2"), guest("g3")],
            tables=[table("t1", 1), table("t2", 3)],
            rules=[same_rule("r-g1g2g3", ("g1", "g2", "g3"), 100)],
        )

    current = {"g1": "t1", "g2": "t2", "g3": "t2"}

    try:
        result = solve_hard(
            build_event("e-ac4"),
            CONFIG,
            mode="event_day",
            current_assignments=current,
            unlocked_guest_ids=frozenset({"g1"}),
        )
    except TypeError:
        # Red until the mode exists: today's solve_hard has no
        # unlocked_guest_ids parameter, so the call fails at the
        # signature, before the body raises the mode's ValueError. Fail
        # by name so this test, like the other five, is red for a
        # reason the event-day implementation can turn green.
        pytest.fail(
            "solve_hard does not accept unlocked_guest_ids yet; the "
            "event-day mode is not implemented"
        )

    assert result.status == "feasible", (
        f"with g1 unlocked the trio fits t2, so a chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t2", "g2": "t2", "g3": "t2"}, (
        f"g1 is the only free guest and the only scoring chart seats "
        f"the trio at t2, got {result.assignments!r}"
    )
    assert result.soft_score == 100, (
        f"all three guests share t2 in the winning chart, "
        f"got soft_score {result.soft_score}"
    )
    assert result.assignments["g2"] == "t2" and result.assignments["g3"] == "t2", (
        f"g2 and g3 are not in the unlocked set, so the pins keep "
        f"them at t2, got {result.assignments!r}"
    )


def test_new_guest_respects_hard_rules() -> None:
    """ac5: the new guest seats where every hard rule holds. g1 and g2
    sit at t1 (t1 holds three, t2 holds three); g3 is new; a hard
    different_table rule keeps g1 and g3 apart, and a soft same_table
    rule over the same pair (weight 100) tempts g3 onto t1. The hard
    rule forbids it, so g3 goes to t2: the soft rule scores 0, the
    hard rule is satisfied, and g1 and g2 are exactly where they were.
    The contrast in the same test: the event without the hard rule
    seats g3 at t1 and scores 100 — the zero-score chart is therefore
    the hard rule doing its work, not a failure to optimise."""

    def build_event(event_id: str, hard: bool) -> Event:
        rule_list = (
            [
                different_table_rule("r-hard", ("g1", "g3")),
            ]
            if hard
            else []
        )
        return Event(
            id=event_id,
            name="Hard rule decides",
            guests=[guest("g1"), guest("g2"), guest("g3")],
            tables=[table("t1", 3), table("t2", 3)],
            rules=[*rule_list, same_rule("r-soft", ("g1", "g3"), 100)],
        )

    current = {"g1": "t1", "g2": "t1"}

    result = solve_hard(
        build_event("e-ac5", True),
        CONFIG,
        mode="event_day",
        current_assignments=current,
    )

    assert result.status == "feasible", (
        f"g3 fits t2, so a chart honouring the hard rule exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g2": "t1", "g3": "t2"}, (
        f"g3 cannot share t1 with g1, so t2 is the only place for "
        f"them, got {result.assignments!r}"
    )
    assert result.soft_score == 0, (
        f"the soft rule is left unsatisfied rather than break the hard "
        f"rule, got soft_score {result.soft_score}"
    )
    hard_state = next(
        assessment
        for assessment in result.rule_states
        if assessment.rule_id == "r-hard"
    )
    assert hard_state.status == "satisfied", (
        f"g1 and g3 sit at different tables, so the hard rule holds, "
        f"got status {hard_state.status!r}"
    )
    hard_violations = tuple(
        assessment
        for assessment in result.violations
        if assessment.hardness == Hardness.HARD.value
    )
    assert hard_violations == (), (
        f"no rule the chart can be judged on is a hard rule this chart "
        f"breaks — the violated rule is the soft one, got "
        f"{hard_violations!r}"
    )

    unplanned = solve_hard(
        build_event("e-ac5-soft-only", False),
        CONFIG,
        mode="event_day",
        current_assignments=current,
    )
    assert unplanned.status == "feasible", (
        f"without the hard rule the event is trivially seatable, "
        f"got status {unplanned.status!r}"
    )
    assert unplanned.assignments == {"g1": "t1", "g2": "t1", "g3": "t1"}, (
        f"without the hard rule the soft rule pulls g3 onto t1, "
        f"got {unplanned.assignments!r}"
    )
    assert unplanned.soft_score == 100, (
        f"g1 and g3 share t1 when nothing forbids it, "
        f"got soft_score {unplanned.soft_score}"
    )


def test_full_room_is_infeasible() -> None:
    """The mode's infeasible path: a proven refutation is structural.
    One table t1 holds two guests; g1 and g2 sit there, so t1 is
    exactly full, and g3 is a new arrival with nowhere to go — there
    is no other table at all. The solve must prove infeasible: the
    status is infeasible, no chart at all (never a partial one) comes
    back, and the result stamps the mode it was solved under. The
    carried report names no conflicting rule — there are no rules —
    and recommends adding capacity: capacity 2 for 3 eligible guests,
    a shape failure no deletion-minimised rule or lock set can blame,
    so the recommendation is the capacity one."""
    current = {"g1": "t1", "g2": "t1"}
    event = Event(
        id="e-full-room",
        name="Full room",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2)],
        rules=[],
    )

    result = solve_hard(event, CONFIG, mode="event_day", current_assignments=current)

    assert result.status == "infeasible", (
        f"three guests over two seats and one table: no chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {}, (
        f"a proven refutation never hands back a partial chart, "
        f"got {result.assignments!r}"
    )
    assert result.mode == "event_day", (
        f"an infeasible result records the mode it was solved under, "
        f"got mode {result.mode!r}"
    )
    report = result.infeasibility_report
    assert report is not None, (
        "an infeasible result must carry its infeasibility report"
    )
    assert report.conflict_rule_ids == (), (
        f"the event has no rules and the failure is pure capacity, "
        f"got {report.conflict_rule_ids!r}"
    )
    capacity_recs = [
        rec for rec in report.recommendations if rec.kind == "add_capacity"
    ]
    assert capacity_recs, (
        f"two seats for three eligible guests must be met with an "
        f"add_capacity recommendation, got {report.recommendations!r}"
    )
