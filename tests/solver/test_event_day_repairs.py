# tests/solver/test_event_day_repairs.py
"""Bean-025 red tests: event-day unlock and no-seat report repairs.

Three tests are red on the current tree, each by a plain assertion on a
solve result: ac1 fails on the chart of the unlocked half (the explicit
lock is still encoded); ac4 fails on the generic add-a-table
recommendation the report carries beside the unlocks; ac5 fails on the
status (the contradicted guest is silently moved to the locked table).
The ac2 test is a regression pin for behaviour this tree already has:
the deletion-minimising probes carry the day-lock pins, so only the
rule whose removal alone helps is named, and a seat shortage names no
rule and asks for capacity. Every fixture is small enough to work out
by hand.
"""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import EVENT_DAY

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def locked_guest(guest_id: str, table_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
        locked_to_table=table_id,
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


def diff_rule(rule_id: str, guests: tuple[str, ...]) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.DIFFERENT_TABLE,
        hardness=Hardness.HARD,
        guests=guests,
    )


def test_unlock_releases_an_explicit_lock() -> None:
    """ac1: g1 is locked to t2; g1 and g2 fill t2, g3 sits at t1, and a
    weight-100 soft rule wants g1 with g3. Without g1 in
    unlocked_guest_ids the lock holds: the chart comes back exactly as
    the baseline with soft_score 0. With g1 in unlocked_guest_ids the
    lock releases: g1 is a free guest, t1 has room, t1 is the only
    table g1 can join g3 at without moving anyone else, and the soft
    score climbs to 100. Only g1 moves."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Explicit unlock releases an explicit lock",
            guests=[locked_guest("g1", "t2"), guest("g2"), guest("g3")],
            tables=[table("t1", 2), table("t2", 2)],
            rules=[same_rule("r-g1g3", ("g1", "g3"), 100)],
        )

    current = {"g1": "t2", "g2": "t2", "g3": "t1"}

    locked = solve_hard(
        build_event("e-ac1-locked"),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert locked.status == "feasible", (
        f"the baseline chart honours every capacity, got {locked.status!r}"
    )
    assert locked.assignments == current, (
        "g1 is locked to t2 and not in unlocked_guest_ids, so nothing "
        f"moves, got {locked.assignments!r}"
    )
    assert locked.soft_score == 0, (
        f"g1 is held at t2 apart from g3, got soft_score {locked.soft_score}"
    )

    result = solve_hard(
        build_event("e-ac1-unlocked"),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
        unlocked_guest_ids=frozenset({"g1"}),
    )
    assert result.status == "feasible", (
        f"with the lock released t1 has room for g1, got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g2": "t2", "g3": "t1"}, (
        "the unlock must release the explicit lock: g1 joins g3 at t1 "
        f"and nobody else moves, got {result.assignments!r}"
    )
    assert result.soft_score == 100, (
        f"g1 and g3 share t1, got soft_score {result.soft_score}"
    )


def test_a_lock_that_causes_no_seat_is_named() -> None:
    """ac4: a stored lock that refuses the seat is the only cause a
    no-seat report names. Shape one: t1 holds two (the baseline's g1,
    g2), t2 is empty; g3 is a new arrival explicitly locked to exactly
    full t1. Shape two: t1 holds two (g1, g3), t2 holds one (g2); g1 is
    explicitly locked to the already-filled t2 and the chart pins them
    at t1. Neither event has a rule and each offers three seats for
    three guests, so there is no hard rule to review and adding tables
    or capacity changes nothing the lock refuses: each solve must prove
    infeasible with an empty chart, name no conflicting rule, recommend
    unlocking the locked guest at the locked table and nothing else."""
    full = Event(
        id="e-ac4-locked-arrival",
        name="A new guest locked onto a full table",
        guests=[guest("g1"), guest("g2"), locked_guest("g3", "t1")],
        tables=[table("t1", 2), table("t2", 1)],
        rules=[],
    )
    current_full = {"g1": "t1", "g2": "t1"}

    crossed = Event(
        id="e-ac4-crossed-pin",
        name="A chart guest locked onto the other, full table",
        guests=[locked_guest("g1", "t2"), guest("g2"), guest("g3")],
        tables=[table("t1", 2), table("t2", 1)],
        rules=[],
    )
    current_crossed = {"g1": "t1", "g2": "t2", "g3": "t1"}

    for event, current, locked_id, locked_table_id in (
        (full, current_full, "g3", "t1"),
        (crossed, current_crossed, "g1", "t2"),
    ):
        result = solve_hard(event, CONFIG, mode=EVENT_DAY, current_assignments=current)
        assert result.status == "infeasible", (
            f"{locked_id} is locked to {locked_table_id} and no seat "
            f"there exists in the charted event, got {result.status!r}"
        )
        assert result.assignments == {}, (
            f"a refutation hands back no partial chart, got {result.assignments!r}"
        )
        report = result.infeasibility_report
        assert report is not None, "an infeasible result carries its report"
        assert report.conflict_rule_ids == (), (
            "the event has no rules, so nothing but the lock can be "
            f"named, got {report.conflict_rule_ids!r}"
        )
        unlock_recs = [rec for rec in report.recommendations if rec.kind == "unlock"]
        assert any(
            locked_id in rec.detail and locked_table_id in rec.detail
            for rec in unlock_recs
        ), (
            f"the fix must say unlock {locked_id} at {locked_table_id}, "
            f"got {report.recommendations!r}"
        )
        kinds = {rec.kind for rec in report.recommendations}
        assert kinds == {"unlock"}, (
            "with the lock as the only cause, unlocking is the only "
            f"recommendation that can help, got {report.recommendations!r}"
        )


def test_a_lock_contradicting_the_chart_is_infeasible_and_named() -> None:
    """ac5: an explicit lock never silently overrides the event-day
    chart pin. t-1 and t-2 hold two each; the chart seats g-0 and g-2
    at t-1 (full) and frees g-1's seat; g-2 is explicitly locked to
    t-2 and nobody is in unlocked. The chart pins g-2 at t-1 and the
    lock demands t-2 — they disagree and cannot both hold — so the
    solve is infeasible and the report recommends unlocking g-2 and
    nothing else: no rule exists to review, and three seats for three
    guests are not what is missing. The same event with g-2 in
    unlocked is feasible, so the check cannot refuse every lock that
    disagrees with the chart."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="A stored lock contradicting the chart pin",
            guests=[guest("g-0"), guest("g-1"), locked_guest("g-2", "t-2")],
            tables=[table("t-1", 2), table("t-2", 2)],
            rules=[],
        )

    chart = {"g-0": "t-1", "g-2": "t-1"}

    result = solve_hard(
        build_event("e-ac5-contradicted"),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert result.status == "infeasible", (
        "g-2 is pinned at t-1 by the chart and at t-2 by the stored "
        f"lock, and is not in unlocked, got status {result.status!r}"
    )
    assert result.assignments == {}, (
        f"a refutation hands back no partial chart, {result.assignments!r}"
    )
    report = result.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    assert report.conflict_rule_ids == (), (
        "the event has no rules, so nothing but the lock can be "
        f"named, got {report.conflict_rule_ids!r}"
    )
    unlocks = [rec for rec in report.recommendations if rec.kind == "unlock"]
    assert (
        len(unlocks) == 1 and "g-2" in unlocks[0].detail and "t-2" in unlocks[0].detail
    ), (
        "the one move that resolves this is unlocking g-2 from t-2, "
        f"got {report.recommendations!r}"
    )
    kinds = {rec.kind for rec in report.recommendations}
    assert kinds == {"unlock"}, (
        "no rule is to review and adding capacity is not the remedy, "
        f"got {report.recommendations!r}"
    )

    released = solve_hard(
        build_event("e-ac5-unlocked"),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
        unlocked_guest_ids=frozenset({"g-2"}),
    )
    assert released.status == "feasible", (
        "with g-2 in unlocked both pins release and everyone seats, "
        f"got status {released.status!r}"
    )
    assert released.assignments["g-0"] == "t-1", (
        f"g-0 is still pinned at t-1, got {released.assignments!r}"
    )
    assert released.assigned_count == 3, (
        f"every eligible guest is seated, got {released.assignments!r}"
    )


def test_no_seat_blames_only_rules_that_explain_it() -> None:
    """ac2: a no-seat diagnosis names only the rule whose removal alone
    helps. Part one: t1 holds three (baseline g1, g2), t2 holds one
    (baseline g3); g4 is a new arrival barred from the free t1 seat by
    the hard rule (g1, g4), and t2 is full. A second hard rule (g3,
    g4) the chart already satisfies must not be named: removal of it
    alone changes nothing with the chart in place. The solve must be
    infeasible, name exactly r-g1g4, and recommend changing it; a
    contrast event with only the cause rule disabled is feasible with
    every baseline guest where the baseline put them. Part two, a
    shortage: t1 holds two — three seats for four guests. The shortage
    refutes with every rule and pin off, so no rule is named, the
    report asks for capacity and never for a hard-rule review, and
    removing the satisfied rule alone leaves it infeasible."""

    def build_event(
        event_id: str,
        t1_capacity: int,
        *,
        with_cause: bool = True,
        with_sat: bool = True,
    ) -> Event:
        rules: list[Rule] = []
        if with_cause:
            rules.append(diff_rule("r-g1g4", ("g1", "g4")))
        if with_sat:
            rules.append(diff_rule("r-g3g4", ("g3", "g4")))
        return Event(
            id=event_id,
            name="A missing seat names only the rule that explains it",
            guests=[guest("g1"), guest("g2"), guest("g3"), guest("g4")],
            tables=[table("t1", t1_capacity), table("t2", 1)],
            rules=rules,
        )

    current = {"g1": "t1", "g2": "t1", "g3": "t2"}

    named = solve_hard(
        build_event("e-ac2-named", 3),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert named.status == "infeasible", (
        f"g4 is barred to the free t1 seat and t2 is full, got status {named.status!r}"
    )
    report = named.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    assert report.conflict_rule_ids == ("r-g1g4",), (
        "only the rule that bars g4 from the one seat they can reach "
        "is at fault; the chart already satisfies (g3, g4), got "
        f"{report.conflict_rule_ids!r}"
    )
    assert any(rec.kind == "change_hard_rule" for rec in report.recommendations), (
        "the named rule is hard, so the report must offer to change "
        f"it, got {report.recommendations!r}"
    )
    assert any("r-g1g4" in rec.detail for rec in report.recommendations), (
        "the change-hard-rule recommendation must name r-g1g4, got "
        f"{report.recommendations!r}"
    )

    cause_removed = solve_hard(
        build_event("e-ac2-cause-disabled", 3, with_cause=False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert cause_removed.status == "feasible", (
        "with the cause rule gone g4 takes the free t1 seat, got "
        f"status {cause_removed.status!r}"
    )
    assert cause_removed.assignments == {
        "g1": "t1",
        "g2": "t1",
        "g3": "t2",
        "g4": "t1",
    }, (
        "removal of the named rule alone must help with the chart in "
        f"place and move no one else, got {cause_removed.assignments!r}"
    )

    satisfied_removed = solve_hard(
        build_event("e-ac2-sat-disabled", 3, with_sat=False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert satisfied_removed.status == "infeasible", (
        "removing the already-satisfied rule alone changes nothing, "
        f"got status {satisfied_removed.status!r}"
    )

    capacity = solve_hard(
        build_event("e-ac2-capacity", 2, with_cause=False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert capacity.status == "infeasible", (
        "three seats for four guests: no chart exists anyway, got "
        f"status {capacity.status!r}"
    )
    capacity_report = capacity.infeasibility_report
    assert capacity_report is not None, "an infeasible result carries its report"
    assert capacity_report.conflict_rule_ids == (), (
        "a shortage refutes the event with every rule and pin off, so "
        "no rule can be named, got "
        f"{capacity_report.conflict_rule_ids!r}"
    )
    assert any(rec.kind == "add_capacity" for rec in capacity_report.recommendations), (
        f"the seats are what are missing, got {capacity_report.recommendations!r}"
    )
    assert not any(
        rec.kind == "change_hard_rule" for rec in capacity_report.recommendations
    ), f"no rule explains a shortage of seats, got {capacity_report.recommendations!r}"

    capacity_sat_removed = solve_hard(
        build_event("e-ac2-capacity-sat-disabled", 2, with_cause=False, with_sat=False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=current,
    )
    assert capacity_sat_removed.status == "infeasible", (
        "removing the rule alone cannot create the missing seat, got "
        f"status {capacity_sat_removed.status!r}"
    )
