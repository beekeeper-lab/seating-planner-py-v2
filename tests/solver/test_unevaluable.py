"""Acceptance tests for unevaluable rules (bean-020).

One fixture drives every state-reading test: two confirmed guests,
two one-seat tables, and two soft rules on the pair (g1, g2).
Capacity alone — two guests, two one-seat tables — forces the pair
into different tables in the only feasible chart, so r-together (40)
is genuinely violated with nothing else to force it, and r-adjacent
(20) is unevaluable because no seat positions exist. The soft score
is 0: the broken rule scores nothing, and neither does the rule the
chart cannot read.
"""

from __future__ import annotations

import json

import pytest

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


def wedding(guests: list[Guest], tables: list[Table], rules: list[Rule]) -> Event:
    return Event(id="e1", name="Wedding", guests=guests, tables=tables, rules=rules)


def core_event() -> Event:
    """Two guests, two one-seat tables, two soft rules on (g1, g2): the
    only feasible chart seats them apart, so r-together is VIOLATED,
    r-adjacent is UNEVALUABLE, the violations name exactly r-together,
    and the soft score is 0."""
    return wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 1), table("t2", 1)],
        [
            Rule(
                id="r-together",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=40,
            ),
            Rule(
                id="r-adjacent",
                kind=RuleKind.ADJACENT_SEAT,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=20,
            ),
        ],
    )


def find(result: SolveResult, rid: str) -> RuleAssessment | None:
    """One rule's state, or None when absent (returns, not raises)."""
    return next((a for a in result.rule_states if a.rule_id == rid), None)


def states(result: SolveResult) -> dict[str, dict]:
    """The result's serialized rule_states, keyed by rule id."""
    data = json.loads(json.dumps(result.to_dict()))
    return {entry["rule_id"]: entry for entry in data["rule_states"]}


def test_adjacent_seat_rule_is_unevaluable() -> None:
    """ac1: a rule the chart cannot decide is unevaluable, never satisfied
    — r-adjacent needs seat positions the table-level chart lacks — and it
    scores nothing, so it is not among the violations."""
    result = solve_hard(core_event(), CONFIG, mode="planning")
    assert result.status == "feasible"
    at = result.assignments
    assert at["g1"] != at["g2"], (
        f"two guests in two one-seat tables force the pair apart: {at}"
    )
    adjacent = find(result, "r-adjacent")
    assert adjacent is not None
    assert adjacent.status == UNEVALUABLE, (
        f"no seat positions, so no verdict: {adjacent.status}"
    )
    assert adjacent.status != SATISFIED, "an unreadable rule is never satisfied"
    assert "r-adjacent" not in {a.rule_id for a in result.violations}, result.violations


def test_unevaluable_scores_zero() -> None:
    """ac2: the soft score recomputes from the chart and an unevaluable
    rule contributes nothing — r-together is broken (no 40), r-adjacent
    is unreadable (no 20), so the chart scores 0."""
    result = solve_hard(core_event(), CONFIG, mode="planning")
    at = result.assignments
    # r-together scores only when the pair shares a table; r-adjacent is
    # unevaluable, so it contributes nothing of its 20.
    recomputed = (0 if at["g1"] != at["g2"] else 40) + 0
    assert result.soft_score == recomputed == 0, (result.soft_score, at)


def test_hard_unevaluable_rule_blocks() -> None:
    """ac4: a hard rule the chart cannot read must refuse the solve with an
    explanatory error — the rule is named, and seat positions are said to
    be unconfigured. As the control, the all-soft core fixture completes:
    an unevaluable soft rule is scored and reported, never refused."""
    hard_rules = [
        Rule(
            id="r-hard-adj",
            kind=RuleKind.ADJACENT_SEAT,
            hardness=Hardness.HARD,
            guests=("g1", "g2"),
        ),
        Rule(
            id="r-hard-distance",
            kind=RuleKind.MIN_DISTANCE,
            hardness=Hardness.HARD,
            guests=("g1", "g2"),
            distance_m=3.0,
        ),
    ]
    for hard in hard_rules:
        with pytest.raises(ValueError) as excinfo:
            solve_hard(
                wedding(
                    [guest("g1"), guest("g2")],
                    [table("t1", 1), table("t2", 1)],
                    [hard],
                ),
                CONFIG,
                mode="planning",
            )
        message = str(excinfo.value).lower()
        assert hard.id in message, str(excinfo.value)
        assert "seat position" in message and "configur" in message, str(excinfo.value)
    control = solve_hard(core_event(), CONFIG, mode="planning")
    assert control.status == "feasible"


def test_unevaluable_reason_is_stated() -> None:
    """ac5: the result distinguishes unevaluable — with a reason — from
    violated, which carries none. The reason is discovered from the result,
    in words: seat positions are not configured."""
    result = solve_hard(core_event(), CONFIG, mode="planning")
    together, adjacent = find(result, "r-together"), find(result, "r-adjacent")
    assert together is not None and adjacent is not None
    assert together.status == VIOLATED
    assert adjacent.status == UNEVALUABLE
    assert {a.rule_id for a in result.violations} == {"r-together"}
    entries = states(result)
    reason = (entries["r-adjacent"].get("reason") or "").lower()
    assert "seat position" in reason and "configur" in reason, reason
    assert (entries["r-together"].get("reason") or "") == "", (
        "a violated rule has no unevaluable reason"
    )


def test_unevaluable_rule_states_why_in_words() -> None:
    """ac6: the reason is not the state code — it is a non-empty string
    naming what is missing (seat positions), standing in for nothing: an
    assessment with only the code, or only the rule's own kind word, is no
    explanation."""
    result = solve_hard(core_event(), CONFIG, mode="planning")
    reason = states(result)["r-adjacent"].get("reason")
    assert isinstance(reason, str) and reason, (
        f"the reason must be a non-empty string, got {reason!r}"
    )
    text = reason.lower()
    assert "seat position" in text and "configur" in text, text
