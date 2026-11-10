"""Acceptance tests for the worker count a caller asks for (bean-024).

The pin: the count a caller requests through
``SolverConfig(num_workers=...)`` is the one every CP-SAT production
solve runs with, and the one the result records, on every path. The
behaviour on this tree is already correct, so this module is a
regression pin only — both tests pass without any source change.

Run 2 of the bean's history shaped the ac1 test: a pin whose spy
covered planning alone, whose other two modes only checked the
recorded field, passed while the production solves in those modes
were silently put back to one worker — the result still recorded the
request, both tests still passed. So here the spy runs in planning,
low_disruption and event_day alike, reading each count off the
solver itself at the moment of the call (a feasible solve runs
exactly one production solve: the infeasibility probes re-solve only
after CP-SAT already proved infeasible), and the ac2 test checks the
record on the two infeasible modes plus the early return that never
reaches a solver at all.
"""

from __future__ import annotations

import pytest
from ortools.sat.python import cp_model

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import EVENT_DAY, LOW_DISRUPTION, PLANNING

#: The request shared by every solve below: two workers, on top of a
#: fixed seed and time limit, so the worker count is the one variable
#: moving between the request, the run and the record.
CONFIG = SolverConfig(time_limit_s=5.0, seed=7, num_workers=2)

#: The count every assertion in the module compares against.
REQUESTED_WORKERS = 2


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def simple_event() -> Event:
    """Feasible in every mode: two confirmed guests over one table that
    holds both, no rules. In low_disruption and event_day the baseline
    seats g1 at t1, leaving g2 a new arrival with a free seat beside
    them, so the three solves differ only in their mode arguments."""
    return Event(
        id="e-worker-pin",
        name="Worker pin",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
        rules=[],
    )


def limit_bound_event() -> Event:
    """Infeasible under move_limit=1: the low_disruption ac4 fixture
    from tests/solver/test_low_disruption.py. g1 and g2 sit at a full
    t1 (capacity 2), g3 and g4 at t2 (capacity 3), and g3 is locked to
    t1: the lock sends g3 to a table one of g1 or g2 must vacate, so
    the minimum is two moves against a limit of one. Five seats for
    four guests, so the refutation is the limit's, proven — which is
    what lets the recording check ride an infeasible result."""
    event = Event(
        id="e-limit-bound",
        name="Limit is the cause",
        guests=[guest(f"g{i}") for i in range(1, 5)],
        tables=[table("t1", 2), table("t2", 3)],
        rules=[],
    )
    event.lock_guest("g3", "t1")
    return event


def full_room_event() -> Event:
    """Infeasible in event_day: the fixture from
    tests/solver/test_event_day.py::test_full_room_is_infeasible. t1
    (capacity 2) holds g1 and g2, g3 is a new arrival, and there is no
    other table — a structural capacity failure no rule names."""
    return Event(
        id="e-full-room",
        name="Full room",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2)],
        rules=[],
    )


def nobody_event() -> Event:
    """The early return: the only guest declined, so nobody is
    eligible and solve_hard summarises without building or running a
    solver. Its recorded configuration is whatever the caller passed
    in — the path that must record the request too."""
    return Event(
        id="e-nobody",
        name="Nobody shows",
        guests=[
            Guest(
                id="g1",
                name="Guest g1",
                rsvp_status=RsvpStatus.DECLINED,
            )
        ],
        tables=[table("t1", 2)],
        rules=[],
    )


def spy_worker_counts(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The worker counts the CP-SAT solves below actually ran with.

    The production solve and the infeasibility probes build their
    solvers from this very class and set
    ``solver.parameters.num_workers`` immediately before the call, so
    reading ``self.parameters.num_workers`` at the moment of the call
    catches the count each solve was handed — not what the result
    later records. Patched on the class the same way
    tests/solver/test_infeasible.py pins the timeout path, and
    delegated to the real solve so the models are solved for real.
    """
    real_solve = cp_model.CpSolver.solve
    counts: list[int] = []

    def spied(self: cp_model.CpSolver, model: cp_model.CpModel) -> object:
        counts.append(int(self.parameters.num_workers))
        return real_solve(self, model)

    monkeypatch.setattr(cp_model.CpSolver, "solve", spied)
    return counts


def test_requested_workers_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """ac1: a feasible solve asked for two workers records two workers,
    and the CP-SAT solve itself runs with two workers, in planning,
    low_disruption and event_day. The spy reads each count from the
    solver at the moment of the call, so a production solve that
    silently runs with one worker fails here even when the result
    keeps recording the request — the defect run 2 let back in for
    the two modes a record-checking pin could not see."""
    counts = spy_worker_counts(monkeypatch)

    planning = solve_hard(simple_event(), CONFIG, mode=PLANNING)
    planning_counts = list(counts)
    counts.clear()

    low_disruption = solve_hard(
        simple_event(),
        CONFIG,
        mode=LOW_DISRUPTION,
        current_assignments={"g1": "t1"},
        move_limit=1,
    )
    low_disruption_counts = list(counts)
    counts.clear()

    event_day = solve_hard(
        simple_event(),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments={"g1": "t1"},
    )
    event_day_counts = list(counts)

    for label, result, worker_counts in (
        ("planning", planning, planning_counts),
        ("low_disruption", low_disruption, low_disruption_counts),
        ("event_day", event_day, event_day_counts),
    ):
        assert result.status == "feasible", (
            f"the shared fixture seats in every mode, "
            f"got status {result.status!r} for {label}"
        )
        assert result.mode == label, (
            f"{label}: the result must stamp the mode solved under, "
            f"got mode {result.mode!r}"
        )
        assert result.solver_config.num_workers == REQUESTED_WORKERS, (
            f"{label}: the result must record the {REQUESTED_WORKERS} "
            f"workers asked for, got {result.solver_config.num_workers}"
        )
        assert worker_counts == [REQUESTED_WORKERS], (
            f"{label}: a feasible call runs exactly one production "
            f"solve, and it must run with the requested "
            f"{REQUESTED_WORKERS} workers, got {worker_counts!r}"
        )


def test_every_path_records_the_request() -> None:
    """ac2: every result records the requested worker count, whichever
    path produced it. The three feasible modes, an infeasible
    low_disruption (the limit is the cause, so the deletion-minimising
    probes run after the proof), an infeasible event_day (a full
    room), and the early return with no eligible guest, which never
    reaches a solver at all. The constraint says the infeasibility
    probes may stay single-worker for report reliability while the
    result still records the request: the two infeasible cases are
    therefore checked on the record alone, without a worker-count
    spy, and the default stays one worker."""
    assert SolverConfig().num_workers == 1

    results = [
        ("feasible planning", solve_hard(simple_event(), CONFIG, mode=PLANNING)),
        (
            "feasible low_disruption",
            solve_hard(
                simple_event(),
                CONFIG,
                mode=LOW_DISRUPTION,
                current_assignments={"g1": "t1"},
                move_limit=1,
            ),
        ),
        (
            "feasible event_day",
            solve_hard(
                simple_event(),
                CONFIG,
                mode=EVENT_DAY,
                current_assignments={"g1": "t1"},
            ),
        ),
        (
            "infeasible low_disruption (limit is the cause)",
            solve_hard(
                limit_bound_event(),
                CONFIG,
                mode=LOW_DISRUPTION,
                current_assignments={"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2"},
                move_limit=1,
            ),
        ),
        (
            "infeasible event_day (full room)",
            solve_hard(
                full_room_event(),
                CONFIG,
                mode=EVENT_DAY,
                current_assignments={"g1": "t1", "g2": "t1"},
            ),
        ),
        (
            "early return with no eligible guest",
            solve_hard(nobody_event(), CONFIG, mode=PLANNING),
        ),
    ]

    statuses = [result.status for _, result in results]
    assert statuses == [
        "feasible",
        "feasible",
        "feasible",
        "infeasible",
        "infeasible",
        "feasible",
    ], (
        f"the fixtures were built to solve exactly these ways; a "
        f"different status means the fixture itself drifted, "
        f"got {statuses!r}"
    )
    for label, result in results:
        assert result.solver_config.num_workers == REQUESTED_WORKERS, (
            f"{label}: the result must record the {REQUESTED_WORKERS} "
            f"workers asked for, got {result.solver_config.num_workers}"
        )
        if result.status == "infeasible":
            assert result.assignments == {}, (
                f"{label}: a proven refutation hands back no chart, "
                f"got {result.assignments!r}"
            )
