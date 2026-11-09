"""Regression pins for the requested worker count (bean-024).

The bean-009 defect class was a two-sided one: the solver ran with a worker
count different from the one requested, and the result it recorded could
diverge from what actually ran. The tree under test is expected to already
thread ``SolverConfig.num_workers`` into every CP-SAT solve and to stamp the
same configuration on every result path; these tests only pin that
behaviour, so a failure here is a signal that the tree moved, not a licence
to rewrite the pin.
"""

from __future__ import annotations

from typing import Any

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, hard, solve_hard


def guest(gid: str, status: RsvpStatus = RsvpStatus.CONFIRMED) -> Guest:
    return Guest(id=gid, name=f"Guest {gid}", rsvp_status=status)


def table(tid: str, capacity: int) -> Table:
    return Table(tid, f"Table {tid}", capacity, "round", (0.0, 0.0))


def feasible_event() -> Event:
    """The hand-workable feasible event: three confirmed guests over two
    tables of capacity two — plenty of seats, no rules, a plain plan."""
    return Event(
        id="e-feasible",
        name="Feasible event",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2), table("t2", 2)],
    )


def conflict_event() -> Event:
    """Infeasible by rule contradiction, not by capacity: a hard same-table
    and a hard different-table rule on the same pair, the same three guests
    and two tables of capacity two as the feasible event."""
    return Event(
        id="e-conflict",
        name="Contradictory pair",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            Rule(
                id="r-same",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
            ),
            Rule(
                id="r-diff",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                guests=("g1", "g2"),
            ),
        ],
    )


#: The baseline chart for the re-planning paths: g1 and g2 share t1, g3
#: sits at t2 — a valid chart of the feasible event.
BASELINE = {"g1": "t1", "g2": "t1", "g3": "t2"}


def test_requested_workers_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """ac1: the requested worker count reaches the solver AND is recorded.
    The real solve method is captured first and the patched wrapper merely
    appends the worker count it saw before delegating, so the run stays a
    real CP-SAT solve — ``num_workers``, not ``num_search_workers``, is the
    readable proto field on this pinned ortools."""
    seen: list[int] = []
    real_solve = hard.cp_model.CpSolver.solve

    def spy(self: Any, model: Any) -> Any:
        seen.append(int(self.parameters.num_workers))
        return real_solve(self, model)

    monkeypatch.setattr(hard.cp_model.CpSolver, "solve", spy)

    default = solve_hard(
        feasible_event(), SolverConfig(time_limit_s=5.0, seed=7), mode="planning"
    )
    assert default.status == "feasible", default.status
    assert seen == [1], f"default must run single-worker, the stub saw {seen!r}"
    assert default.solver_config.num_workers == 1, default.solver_config

    seen.clear()
    requested = solve_hard(
        feasible_event(),
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=2),
        mode="planning",
    )
    assert requested.status == "feasible", requested.status
    assert seen == [2], f"the requested two workers must run, the stub saw {seen!r}"
    assert requested.solver_config.num_workers == 2, requested.solver_config


def test_every_path_records_the_request() -> None:
    """ac2: every result path solve_hard can take stamps exactly the
    requested worker count, and each path requests a distinct count above
    one, so a stamp that records one fixed wrong number cannot hide on any
    of them. Only the recording is asserted on the infeasible path: the
    deletion-minimising probes may run at any worker count."""
    # (1) planning, feasible — request 2.
    result = solve_hard(
        feasible_event(),
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=2),
        mode="planning",
    )
    assert result.status == "feasible", result.status
    assert result.solver_config.num_workers == 2, result.solver_config

    # (2) planning, infeasible by rule contradiction — request 3.
    result = solve_hard(
        conflict_event(),
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=3),
        mode="planning",
    )
    assert result.status == "infeasible", result.status
    assert result.solver_config.num_workers == 3, result.solver_config

    # (3) low_disruption, feasible — the baseline chart, one move allowed,
    # request 4.
    result = solve_hard(
        feasible_event(),
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=4),
        mode="low_disruption",
        current_assignments=BASELINE,
        move_limit=1,
    )
    assert result.status == "feasible", result.status
    assert result.solver_config.num_workers == 4, result.solver_config

    # (4) event_day — the same baseline, every guest pinned, request 5.
    result = solve_hard(
        feasible_event(),
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=5),
        mode="event_day",
        current_assignments=BASELINE,
    )
    assert result.status == "feasible", result.status
    assert result.solver_config.num_workers == 5, result.solver_config

    # (5) planning on an event whose guests have all declined — the early
    # return hands back feasible with no chart, and must still record the
    # request: 6.
    declined = Event(
        id="e-declined",
        name="Everyone declined",
        guests=[guest(f"g{i}", RsvpStatus.DECLINED) for i in range(1, 4)],
        tables=[table("t1", 2), table("t2", 2)],
    )
    result = solve_hard(
        declined, SolverConfig(time_limit_s=5.0, seed=7, num_workers=6), mode="planning"
    )
    assert result.status == "feasible", result.status
    assert result.assignments == {}, result.assignments
    assert result.solver_config.num_workers == 6, result.solver_config

    # (6) planning on an event with guests and no tables — the other early
    # return proves infeasible without a solve and must record 7.
    tableless = Event(
        id="e-tableless",
        name="No tables",
        guests=[guest(f"g{i}") for i in range(1, 4)],
        tables=[],
    )
    result = solve_hard(
        tableless,
        SolverConfig(time_limit_s=5.0, seed=7, num_workers=7),
        mode="planning",
    )
    assert result.status == "infeasible", result.status
    assert result.solver_config.num_workers == 7, result.solver_config
