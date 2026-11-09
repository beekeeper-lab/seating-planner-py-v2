"""Acceptance tests for unevaluable adjacent-seat rules (bean-020, FR-012).

This release has no seat positions, so an adjacent-seat rule never has
anything to read: the result says so — unevaluable, never satisfied,
scored as zero, refused when hard — and says it in words, discoverable
from the result itself.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind, default_wedding_rules
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


def core() -> Event:
    """The shared fixture: two confirmed guests, two one-seat tables, and
    two soft rules on the pair. Capacity alone pushes the pair apart, so
    r-together is genuinely violated and r-adjacent has no seats to read."""
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


def states(payload: dict[str, Any]) -> dict[str, Any]:
    """A serialized to_dict() payload mapped to rule_id -> its entry."""
    return {entry["rule_id"]: entry for entry in payload["rule_states"]}


def test_adjacent_seat_rule_is_unevaluable() -> None:
    """ac1: a chart without seat positions reports its adjacent-seat rule
    unevaluable, never satisfied, and keeps it out of the violations."""
    result = solve_hard(core(), CONFIG, mode="planning")
    assert result.status == "feasible"
    at = result.assignments
    assert at["g1"] != at["g2"], "each one-seat table holds one guest"
    adjacent = find(result, "r-adjacent")
    assert adjacent is not None
    assert adjacent.status == UNEVALUABLE
    assert adjacent.status != SATISFIED
    assert adjacent.rule_id not in [v.rule_id for v in result.violations]


def test_unevaluable_scores_zero() -> None:
    """ac2: an unevaluable rule has no satisfied indicator, so it
    contributes nothing — the soft score recomputes to zero from the chart."""
    result = solve_hard(core(), CONFIG, mode="planning")
    at = result.assignments
    # r-together is 40 only if the pair shares a table; r-adjacent
    # contributes nothing: unevaluable rules are never scored as satisfied.
    recomputed = 40 if at["g1"] == at["g2"] else 0
    assert result.soft_score == recomputed == 0, (result.soft_score, at)


def test_hard_unevaluable_rule_blocks() -> None:
    """ac4: a HARD adjacent-seat rule with no seat positions is refused
    with its rule id and the missing seat positions named — while the soft
    fixture's unevaluable rule is scored (as zero) and reported, not refused."""
    blocked = wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 1), table("t2", 1)],
        [
            Rule(
                id="r-hard-adj",
                kind=RuleKind.ADJACENT_SEAT,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
            ),
        ],
    )
    with pytest.raises(ValueError) as exc:
        solve_hard(blocked, CONFIG, mode="planning")
    message = str(exc.value).lower()
    assert "r-hard-adj" in message
    assert "seat position" in message
    assert "configur" in message
    # The control half: the soft-only core fixture is not refused.
    result = solve_hard(core(), CONFIG, mode="planning")
    assert result.status == "feasible"


def test_unevaluable_reason_is_stated() -> None:
    """ac5: the payload distinguishes unevaluable-because-unconfigured
    from violated — r-adjacent carries a reason in words, r-together none."""
    result = solve_hard(core(), CONFIG, mode="planning")
    together = find(result, "r-together")
    adjacent = find(result, "r-adjacent")
    assert together is not None and together.status == VIOLATED
    assert adjacent is not None and adjacent.status == UNEVALUABLE
    assert {v.rule_id for v in result.violations} == {"r-together"}
    data = json.loads(json.dumps(result.to_dict()))
    state_map = states(data)
    reason = (state_map["r-adjacent"].get("reason") or "").lower()
    assert "seat position" in reason
    assert "configur" in reason
    # A violated rule carries no unevaluable reason.
    assert (state_map["r-together"].get("reason") or "") == ""


def test_unevaluable_rule_states_why_in_words() -> None:
    """ac6: the unevaluable reason names what is missing — seat positions —
    in words, not merely the state code and not the rule's kind standing in."""
    result = solve_hard(core(), CONFIG, mode="planning")
    data = json.loads(json.dumps(result.to_dict()))
    reason = states(data)["r-adjacent"].get("reason")
    assert isinstance(reason, str)
    assert reason
    text = reason.lower()
    assert "seat position" in text
    assert "configur" in text


def test_default_wedding_template_still_solves() -> None:
    """ac7: the refusal is adjacent-seat specific — the product's own
    default template solves in every mode, a lone hard min_distance rule
    from that template is not refused, and a hard adjacent-seat rule still is."""
    event = wedding(
        [guest(f"g{i}") for i in range(1, 5)],
        [table("t1", 2), table("t2", 2)],
        list(default_wedding_rules()),
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    baseline = result.assignments
    low = solve_hard(
        event,
        CONFIG,
        mode="low_disruption",
        current_assignments=baseline,
        move_limit=4,
    )
    assert low.status == "feasible"
    day = solve_hard(event, CONFIG, mode="event_day", current_assignments=baseline)
    assert day.status == "feasible"
    distance = next(
        r for r in default_wedding_rules() if r.kind is RuleKind.MIN_DISTANCE
    )
    lone = wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 1), table("t2", 1)],
        [distance],
    )
    assert solve_hard(lone, CONFIG, mode="planning").status == "feasible"
    # The ac4 refusal still holds inside the same test.
    blocked = wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 1), table("t2", 1)],
        [
            Rule(
                id="r-blocks",
                kind=RuleKind.ADJACENT_SEAT,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
            ),
        ],
    )
    with pytest.raises(ValueError):
        solve_hard(blocked, CONFIG, mode="planning")
