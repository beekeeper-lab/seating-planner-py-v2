# tests/solver/test_rule_reporting.py
"""Acceptance tests for rule reporting (bean-027, ac1/ac3/ac4).

Three behaviours: a hard same-table or different-table rule the chart
cannot test — its targets leave fewer than two eligible guests to
read — is reported unevaluable, exactly as a soft rule on the same
guests is, and never satisfied; the solve refuses an event whose rules
share an id, however they got into its rule list, before any solve
runs; and in every result the rule states, the soft score and the
violations agree with each other.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import (
    SATISFIED,
    UNEVALUABLE,
    VIOLATED,
    SolverConfig,
    solve_hard,
)
from seating_planner.solver.hard import EVENT_DAY, LOW_DISRUPTION, PLANNING

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)
MODES = (PLANNING, LOW_DISRUPTION, EVENT_DAY)


def guest(guest_id: str, status: RsvpStatus = RsvpStatus.CONFIRMED) -> Guest:
    return Guest(id=guest_id, name=f"Guest {guest_id}", rsvp_status=status)


def table(table_id: str, capacity: int) -> Table:
    return Table(table_id, f"Table {table_id}", capacity, "round", (0.0, 0.0))


def same_table(
    rid: str, guests: tuple[str, ...], hardness: Hardness, weight: int | None = None
) -> Rule:
    return Rule(
        id=rid,
        kind=RuleKind.SAME_TABLE,
        hardness=hardness,
        guests=guests,
        weight=weight,
    )


def thin_pair_event() -> Event:
    """The bean's measured shape: every thin pair's targets hold one
    confirmed and one declined guest, so each pair leaves the chart one
    guest to read. ``hard-ok`` binds two eligible guests and stays a
    live constraint.
    """
    event = Event(id="e1", name="Wedding")
    event.add_guest(guest("g1"))
    event.add_guest(guest("g2"))
    event.add_guest(guest("g3", RsvpStatus.DECLINED))
    event.add_table(table("t1", 2))
    event.add_table(table("t2", 2))
    event.add_rule(
        same_table("hard-same", ("g1", "g3"), Hardness.HARD),
    )
    event.add_rule(
        Rule(
            id="hard-diff",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.HARD,
            guests=("g2", "g3"),
        ),
    )
    event.add_rule(
        same_table("soft-same", ("g1", "g3"), Hardness.SOFT, weight=10),
    )
    event.add_rule(
        same_table("hard-ok", ("g1", "g2"), Hardness.HARD),
    )
    return event


@pytest.mark.parametrize("mode", MODES)
def test_hard_rule_without_two_seated_guests_is_unevaluable(mode: str) -> None:
    """ac1: in any mode, a hard same-table or different-table rule whose
    targets include fewer than two eligible guests is reported
    unevaluable — exactly as the soft rule on the same guests is, and
    never as satisfied — while a hard rule on two or more eligible
    targets is still reported satisfied in a feasible result.
    """
    event = thin_pair_event()
    planning = solve_hard(event, CONFIG, mode=PLANNING)
    if mode == PLANNING:
        result = planning
    elif mode == LOW_DISRUPTION:
        result = solve_hard(
            event,
            CONFIG,
            mode=LOW_DISRUPTION,
            current_assignments=planning.assignments,
            move_limit=0,
        )
    else:
        result = solve_hard(
            event,
            CONFIG,
            mode=EVENT_DAY,
            current_assignments=planning.assignments,
        )
    assert result.status == "feasible"
    states = {a.rule_id: a.status for a in result.rule_states}
    assert states["hard-same"] == UNEVALUABLE
    assert states["hard-same"] != SATISFIED
    assert states["hard-diff"] == UNEVALUABLE
    # exactly as the soft rule on the same guests is
    assert states["soft-same"] == UNEVALUABLE
    assert states["soft-same"] == states["hard-same"]
    # a hard rule on two or more eligible targets is still satisfied
    assert states["hard-ok"] == SATISFIED
    assert result.soft_score == 0
    assert result.violations == ()


def dup_rule_event() -> Event:
    """A four-guest event whose rule list — after the fact — holds two
    rules sharing an id: appending reaches the list around every domain
    check.
    """
    event = Event(id="e1", name="Wedding")
    for guest_id in ("g1", "g2", "g3", "g4"):
        event.add_guest(guest(guest_id))
    event.add_table(table("t1", 2))
    event.add_table(table("t2", 2))
    event.add_rule(
        same_table("twin", ("g1", "g2"), Hardness.SOFT, weight=10),
    )
    event.rules.append(
        Rule(
            id="twin",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.SOFT,
            guests=("g3", "g4"),
            weight=1,
        ),
    )
    return event


@pytest.mark.parametrize("mode", MODES)
def test_solve_refuses_duplicate_rule_ids(mode: str) -> None:
    """ac3: in every mode the solve refuses the event, however the id
    got into its rule list, with a ValueError whose message names the
    id — before any solve runs.
    """
    event = dup_rule_event()
    baseline = {"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2"}
    if mode == PLANNING:
        with pytest.raises(ValueError) as exc:
            solve_hard(event, CONFIG, mode=PLANNING)
    elif mode == LOW_DISRUPTION:
        with pytest.raises(ValueError) as exc:
            solve_hard(
                event,
                CONFIG,
                mode=LOW_DISRUPTION,
                current_assignments=baseline,
                move_limit=0,
            )
    else:
        with pytest.raises(ValueError) as exc:
            solve_hard(
                event,
                CONFIG,
                mode=EVENT_DAY,
                current_assignments=baseline,
            )
    assert "twin" in str(exc.value)


def test_solve_refuses_duplicate_ids_before_any_solve() -> None:
    """The refusal precedes any solve, not just replaces a settled
    status: a zero-eligible event and a no-tables event both settle
    today without the solver running, and both still refuse a shared
    rule id.
    """
    no_guests = Event(id="e1", name="Wedding")
    no_guests.add_table(table("t1", 2))
    no_guests.add_rule(same_table("twins", ("g1", "g2"), Hardness.SOFT, weight=10))
    no_guests.rules.append(
        Rule(
            id="twins",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.SOFT,
            guests=("g2", "g1"),
            weight=1,
        ),
    )
    with pytest.raises(ValueError) as exc:
        solve_hard(no_guests, CONFIG, mode=PLANNING)
    assert "twins" in str(exc.value)

    no_tables = Event(id="e2", name="Wedding")
    no_tables.add_guest(guest("g1"))
    no_tables.add_rule(same_table("twins", ("g1", "g2"), Hardness.SOFT, weight=10))
    no_tables.rules.append(
        Rule(
            id="twins",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.SOFT,
            guests=("g2", "g1"),
            weight=1,
        ),
    )
    with pytest.raises(ValueError) as exc:
        solve_hard(no_tables, CONFIG, mode=PLANNING)
    assert "twins" in str(exc.value)


def test_states_and_score_agree() -> None:
    """ac4: a guard, not a red test — in every result the rule states
    hold exactly one entry per enabled rule, the soft score is the
    total weight of the soft rules reported satisfied, and the
    violations are exactly the soft rules reported violated. Measured
    on a feasible chart that separates the soft rules and on a proven
    refutation that leaves none of them readable.
    """
    event = Event(id="e1", name="Wedding")
    for guest_id in ("g1", "g2", "g3", "g4"):
        event.add_guest(guest(guest_id))
    event.add_table(table("t1", 2))
    event.add_table(table("t2", 2))
    event.add_rule(same_table("h-pair", ("g1", "g3"), Hardness.HARD))
    event.add_rule(
        same_table("s-together", ("g1", "g2"), Hardness.SOFT, weight=7),
    )
    event.add_rule(
        Rule(
            id="s-apart",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.SOFT,
            guests=("g3", "g4"),
            weight=5,
        ),
    )
    event.add_rule(
        same_table("s-cross", ("g1", "g4"), Hardness.SOFT, weight=3),
    )
    result = solve_hard(event, CONFIG, mode=PLANNING)
    assert result.status == "feasible"
    chart = result.assignments
    states = {a.rule_id: a for a in result.rule_states}
    # one entry per enabled rule, in the event's rule order
    assert [a.rule_id for a in result.rule_states] == [
        "h-pair",
        "s-together",
        "s-apart",
        "s-cross",
    ]
    # the scenario's arithmetic is pinned: the hard pair sits together,
    # and the 2+2 tables leave the other two guests together elsewhere
    assert chart["g1"] == chart["g3"]
    assert chart["g2"] == chart["g4"]
    assert chart["g1"] != chart["g2"]
    expected = {
        "h-pair": SATISFIED,
        "s-together": VIOLATED,
        "s-apart": SATISFIED,
        "s-cross": VIOLATED,
    }
    for rule_id, status in expected.items():
        assert states[rule_id].status == status, rule_id
    # the score is the total of the satisfied softs' weights, and the
    # violations are exactly the violated softs
    assert result.soft_score == 5
    assert result.soft_score == sum(
        a.weight
        for a in result.rule_states
        if a.hardness == "soft" and a.status == SATISFIED
    )
    assert {v.rule_id for v in result.violations} == {"s-together", "s-cross"}
    assert all(v.hardness == "soft" for v in result.violations)

    # the same agreement on a proven refutation, where the chart can
    # read nothing at all
    blocked = Event(id="e2", name="Wedding")
    for guest_id in ("g1", "g2", "g3"):
        blocked.add_guest(guest(guest_id))
    blocked.add_table(table("t1", 2))
    blocked.add_rule(
        Rule(
            id="h-apart",
            kind=RuleKind.DIFFERENT_TABLE,
            hardness=Hardness.HARD,
            guests=("g1", "g2", "g3"),
        ),
    )
    blocked.add_rule(
        same_table("s-together", ("g1", "g2"), Hardness.SOFT, weight=5),
    )
    refuted = solve_hard(blocked, CONFIG, mode=PLANNING)
    assert refuted.status == "infeasible"
    assert [a.rule_id for a in refuted.rule_states] == ["h-apart", "s-together"]
    assert all(a.status == UNEVALUABLE for a in refuted.rule_states)
    assert refuted.soft_score == 0
    assert refuted.violations == ()
