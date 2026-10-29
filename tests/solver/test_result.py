"""Acceptance tests for optimization-result reporting (bean-008, FR-049).

Each fixture is small enough to work out by hand; each test reads only
the solver's result: who sat down, who did not, the soft score, and for
every active rule — satisfied, violated, or unevaluable.
"""

from __future__ import annotations

import json
from collections import Counter

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import (
    SATISFIED,
    UNEVALUABLE,
    VIOLATED,
    RuleAssessment,
    SolverConfig,
    SolveResult,
    solve_hard,
)

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(gid: str) -> Guest:
    return Guest(id=gid, name=f"Guest {gid}", rsvp_status=RsvpStatus.CONFIRMED)


def table(tid: str, cap: int) -> Table:
    return Table(tid, f"Table {tid}", cap, "round", (0.0, 0.0))


def rule(rid, kind, hardness, guests, w=None, **kw):
    return Rule(id=rid, kind=kind, hardness=hardness, guests=guests, weight=w, **kw)


def min_distance(rid: str, g: tuple[str, ...], w: int) -> Rule:
    return Rule(
        id=rid,
        kind=RuleKind.MIN_DISTANCE,
        hardness=Hardness.SOFT,
        guests=g,
        weight=w,
        distance_m=3.0,
    )


def find(result: SolveResult, rid: str) -> RuleAssessment | None:
    """One rule's state, or None when absent (returns, not raises)."""
    return next((a for a in result.rule_states if a.rule_id == rid), None)


def wedding(guests: list[Guest], tables: list[Table], rules: list[Rule]) -> Event:
    return Event(id="e1", name="Wedding", guests=guests, tables=tables, rules=rules)


def test_counts_and_score_consistent() -> None:
    """ac1: counts and soft score recompute from the chart. g1+g2 together
    (10) beats any other seating on two-seat tables and g3 stays apart
    from g1 (1) for free, so the optimum — up to table swap — scores 11,
    and the declined guest sits in neither bucket."""
    event = wedding(
        [
            guest("g1"),
            guest("g2"),
            guest("g3"),
            Guest(id="g4", name="Guest g4", rsvp_status=RsvpStatus.DECLINED),
        ],
        [table("t1", 2), table("t2", 2)],
        [
            rule("r-together", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 10),
            rule("r-apart", RuleKind.DIFFERENT_TABLE, Hardness.SOFT, ("g1", "g3"), 1),
        ],
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    at = result.assignments
    assert result.assigned_count == len(at) == 3, at
    assert result.unassigned_count == 0, "every eligible guest is seated"
    assert "g4" not in at, "an ineligible guest was seated"
    assert at["g1"] == at["g2"], f"the weight-10 pairing was lost: {at}"
    assert at["g3"] != at["g1"], f"g3 stays apart from g1 for the extra point: {at}"
    recomputed = (0 if at["g1"] != at["g2"] else 10) + (
        0 if at["g1"] == at["g3"] else 1
    )
    assert result.soft_score == recomputed == 11, (result.soft_score, at)
    together, apart = find(result, "r-together"), find(result, "r-apart")
    assert together is not None and apart is not None
    assert together.status == SATISFIED == apart.status
    # The bean's constraints: serializable; the payload holds ids and
    # numbers only — no field for a guest name or note to leak.
    data = json.loads(json.dumps(result.to_dict()))
    assert (data["status"], data["assignments"], data["soft_score"]) == (
        result.status,
        at,
        11,
    )
    assert {a["rule_id"] for a in data["rule_states"]} == {"r-together", "r-apart"}
    assert "Guest g1" not in json.dumps(data)


def test_violations_name_rule_and_guests() -> None:
    """ac2: each violated soft constraint appears once, named by rule id
    with its weight and guests. r-together (10) fills the two-seat table,
    g3 sits alone, so r-part (3) — honouring both would score just 3 — is
    what the chart abandons."""
    event = wedding(
        [guest("g1"), guest("g2"), guest("g3")],
        [table("t1", 2), table("t2", 1)],
        [
            rule("r-together", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 10),
            rule("r-part", RuleKind.SAME_TABLE, Hardness.SOFT, ("g2", "g3"), 3),
            rule("r-hard-apart", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g3")),
        ],
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    at = result.assignments
    assert at["g1"] == at["g2"], f"the weight-10 pairing was lost: {at}"
    violations = result.violations
    assert len(violations) == 1, (
        f"exactly one rule is broken in this chart: {violations}"
    )
    assert len({a.rule_id for a in violations}) == len(violations)
    broken = violations[0]
    assert broken.rule_id == "r-part"
    assert broken.weight == 3
    assert broken.affected_guest_ids == ("g2", "g3")
    assert broken.status == VIOLATED
    kept = find(result, "r-together")
    assert kept is not None and kept.status == SATISFIED
    # The chart kept r-together (10) and let r-part (3) go.
    assert result.soft_score == 10, result.soft_score


def test_unevaluable_is_not_satisfied() -> None:
    """ac3: a rule the chart cannot decide is unevaluable, never satisfied
    — its kind needs seats or geometry the chart lacks (min_distance,
    adjacent_seat), or the event is infeasible and has no chart at all."""
    event = wedding(
        [guest("g1"), guest("g2"), guest("g3")],
        [table("t1", 2), table("t2", 1)],
        [
            min_distance("r-distance", ("g1", "g2"), 5),
            rule("r-adjacent", RuleKind.ADJACENT_SEAT, Hardness.SOFT, ("g1", "g3"), 5),
            rule("r-together", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 8),
        ],
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    distance, adjacent, together = (
        find(result, rid) for rid in ("r-distance", "r-adjacent", "r-together")
    )
    assert distance is not None and adjacent is not None and together is not None
    assert distance.status == UNEVALUABLE, "a table-level chart has no geometry"
    assert adjacent.status == UNEVALUABLE, "a table-level chart has no seats"
    assert together.status == SATISFIED
    # Unevaluable soft rules score nothing — the solver never scored them.
    assert result.soft_score == 8, result.soft_score
    dead = wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 2), table("t2", 2)],
        [
            rule("r-hard-together", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-hard-apart", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-soft", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 8),
        ],
    )
    dead_result = solve_hard(dead, CONFIG, mode="planning")
    assert dead_result.status == "infeasible"
    assert dead_result.assignments == {}
    dead_soft, dead_hard = (
        find(dead_result, "r-soft"),
        find(dead_result, "r-hard-together"),
    )
    assert dead_soft is not None and dead_hard is not None
    assert dead_soft.status == UNEVALUABLE, "no chart, no verdict — never satisfied"
    assert dead_hard.status == UNEVALUABLE


def test_rule_accounting_is_complete() -> None:
    """ac4: satisfied, violated and unevaluable account for every active
    rule, and a disabled rule is in no bucket at all. The hard pairing
    g1+g2 fills the two-seat table, so r-sat holds (10), g3 breaks r-viol,
    and the min-distance rule is unreadable at table level."""
    event = wedding(
        [guest("g1"), guest("g2"), guest("g3"), guest("g4")],
        [table("t1", 2), table("t2", 2)],
        [
            rule("r-sat", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 10),
            rule("r-viol", RuleKind.SAME_TABLE, Hardness.SOFT, ("g2", "g3"), 3),
            rule("r-hard-sat", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            min_distance("r-uneval", ("g1", "g3"), 5),
            Rule(
                id="r-off",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g3", "g4"),
                weight=2,
                enabled=False,
            ),
        ],
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    at = result.assignments
    assert at["g1"] == at["g2"], f"the hard pairing was broken: {at}"
    assert at["g3"] != at["g2"], f"g3 has no room at the pair's table: {at}"
    counts = Counter(assessment.status for assessment in result.rule_states)
    assert counts[SATISFIED] == 2, counts
    assert counts[VIOLATED] == 1, counts
    assert counts[UNEVALUABLE] == 1, counts
    active_ids = [r.id for r in event.rules if isinstance(r, Rule) and r.enabled]
    assert len(result.rule_states) == len(active_ids)
    assert counts[SATISFIED] + counts[VIOLATED] + counts[UNEVALUABLE] == len(active_ids)
    assert {a.rule_id for a in result.rule_states} == set(active_ids)
    assert find(result, "r-off") is None, "a disabled rule has no state"
