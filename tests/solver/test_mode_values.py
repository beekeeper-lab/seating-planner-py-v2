"""Regression pin: optimization modes are chosen by value, not by identity.

The original build validated the mode by equality but dispatched by object
identity: a mode string read from a file, a request, or built at run time is
equal to but not identical with the module constant, so the dispatcher
treated "low_disruption" as "planning". In this tree ``solve_hard`` compares
every mode by value, and these two tests pin that behaviour so an identity
comparison cannot come back without failing:

* ac1 — a low-disruption solve whose mode arrives as a run-time-built string
  respects the movement limit exactly as the literal does;
* ac2 — a run-time-built mode that needs a current chart is refused without
  one, with exactly the ValueError the literal gets, before any solving.

The first test builds its string with ``"".join`` and the second with
``json.loads``, so both run-time routes named in the bean are covered;
neither produces the same string object as the source literal, which the
tests assert, since an identity-equal object would pin nothing.

The ac1 fixture reuses the zero-limit arithmetic already proven in
tests/solver/test_low_disruption.py (its ac5): a 100-point soft rule one
move's distance away that the limit of zero does not allow.
"""

from __future__ import annotations

import json

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import LOW_DISRUPTION

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)

CURRENT = {"g1": "t1", "g2": "t1", "g3": "t2"}


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


def zero_limit_event() -> Event:
    """The zero-limit event of test_low_disruption.py's ac5: g1 and g2 sit
    at t1 (capacity 3), g3 at t2 (capacity 2), and the soft rule (g1, g3)
    weight 100 is worth exactly the one move the limit forbids, so the only
    zero-move chart is the current one, returned untouched with
    soft_score 0. A run-time mode string runs that same arithmetic when it
    is dispatched by value."""
    return Event(
        id="e-mode-values",
        name="Mode by value",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3), table("t2", 2)],
        rules=[
            Rule(
                id="r-g1g3",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g3"),
                weight=100,
            )
        ],
    )


def test_runtime_mode_string_is_the_same_mode() -> None:
    """ac1: the run-time string is the same mode. With move_limit 0 the
    zero-move current chart is the literal's answer, and the joined string
    must return that same chart: a dispatcher that sees the joined string
    as "planning" would refuse the baseline arguments, or run a planning
    solve whose chart ignores the limit it was given."""
    # FLY002 wants the literal, but the join is the point: the string must
    # arrive the way a file, a request or a join would deliver it, as a
    # fresh object, not as hard.py's own constant.
    runtime_mode = "".join(["low_", "disruption"])  # noqa: FLY002
    assert runtime_mode == LOW_DISRUPTION
    assert runtime_mode is not LOW_DISRUPTION, (
        "the pin needs a string equal but not identical with the module "
        "constant; a joined string is always a fresh object"
    )

    literal = solve_hard(
        zero_limit_event(),
        CONFIG,
        mode=LOW_DISRUPTION,
        current_assignments=CURRENT,
        move_limit=0,
    )
    runtime = solve_hard(
        zero_limit_event(),
        CONFIG,
        mode=runtime_mode,
        current_assignments=CURRENT,
        move_limit=0,
    )

    assert literal.status == "feasible"
    assert literal.assignments == CURRENT
    assert literal.soft_score == 0
    assert runtime.status == literal.status, (
        f"the joined string names the same mode, so it settles the same, "
        f"got status {runtime.status!r}"
    )
    assert runtime.assignments == literal.assignments, (
        f"the run-time mode must seat the same chart as the literal, "
        f"got {runtime.assignments!r}"
    )
    assert runtime.soft_score == literal.soft_score, (
        f"the run-time mode must score the same chart as the literal, "
        f"got {runtime.soft_score}"
    )
    assert runtime.mode == "low_disruption", (
        f"the result records the mode it was solved under; the run-time "
        f"string is that mode by value, got {runtime.mode!r}"
    )


def test_runtime_mode_string_is_validated_the_same() -> None:
    """ac2: the refusal is part of the mode's behaviour. A low-disruption
    mode without its current chart raises the same ValueError as the
    literal before any solving starts; a dispatcher that sees the
    json-loaded string as "planning" would accept the call and run a
    planning solve labelled low_disruption — the original defect the bean
    names."""
    runtime_mode = json.loads('"low_disruption"')
    assert runtime_mode == LOW_DISRUPTION
    assert runtime_mode is not LOW_DISRUPTION, (
        "the pin needs a string equal but not identical with the module "
        "constant; json.loads never reuses source literals"
    )

    with pytest.raises(ValueError) as literal_exc:
        solve_hard(zero_limit_event(), CONFIG, mode=LOW_DISRUPTION)
    with pytest.raises(ValueError) as runtime_exc:
        solve_hard(zero_limit_event(), CONFIG, mode=runtime_mode)

    assert str(runtime_exc.value) == str(literal_exc.value), (
        "the run-time mode is refused exactly as the literal is, with the "
        f"same message, got {str(runtime_exc.value)!r} vs "
        f"{str(literal_exc.value)!r}"
    )
