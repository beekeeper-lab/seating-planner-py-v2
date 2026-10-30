"""Acceptance tests for EventRepository.accept (FR-072): the check precedes every write.

* ac5 — scenario C: g3 is DECLINED but sits in the saved chart, tables
  t1 capacity 3 and t2 capacity 1, plus r1 SOFT same_table(g1, g2) at
  weight 100 and r2 SOFT different_table(g1, g4) at weight 50. The r1
  pair needs two seats and only t1 has any, so it goes to t1 (+100); g4
  scores r2 (+50) only at the lone-seated t2. The optimum is
  {g1: t1, g2: t1, g4: t2}; accepting it replaces the chart — g3's row
  gone — and appends exactly one more ``chart_saved`` audit row naming
  the accepting actor.
* ac6 — the bean's own fixture: table t1 of capacity 1, two CONFIRMED
  guests, a saved chart seating BOTH at t1 (savable, because save_chart
  re-checks nothing). Planning against it is infeasible with empty
  assignments and an empty comparison — the run-1 shape that once erased
  a good chart under a normal-looking audit row. Accept must raise and
  write nothing; and the same event at a capacity-2 table optimizes to
  a feasible no-change proposal (comparison ()) that still accepts, so
  the check fails only in the infeasible direction.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, optimize
from seating_planner.solver.hard import PLANNING
from seating_planner.store import EventRepository

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(guest_id: str, rsvp: RsvpStatus = RsvpStatus.CONFIRMED) -> Guest:
    return Guest(id=guest_id, name=f"Guest {guest_id}", rsvp_status=rsvp)


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def test_accept_writes_chart_and_audit() -> None:
    """ac5: accepting scenario C's optimum replaces the saved chart and
    appends one ``chart_saved`` row naming the accepting actor."""
    repo = EventRepository(":memory:")
    event = Event(
        id="e1",
        name="Wedding",
        guests=[
            guest("g1"),
            guest("g2"),
            guest("g3", RsvpStatus.DECLINED),
            guest("g4"),
        ],
        tables=[table("t1", 3), table("t2", 1)],
        rules=[
            Rule(
                id="r1",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=100,
            ),
            Rule(
                id="r2",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g4"),
                weight=50,
            ),
        ],
    )
    saved = {"g1": "t1", "g2": "t2", "g3": "t2", "g4": "t1"}
    repo.save(event, "organizer")
    repo.save_chart("e1", saved, "organizer")

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=saved)
    assert proposal.status == "feasible"
    assert proposal.assignments == {"g1": "t1", "g2": "t1", "g4": "t2"}

    repo.accept(proposal, "organizer@example.com")

    assert repo.load_chart("e1") == {"g1": "t1", "g2": "t1", "g4": "t2"}
    saved_rows = [e for e in repo.audit_entries("e1") if e.action == "chart_saved"]
    assert len(saved_rows) == 2
    assert saved_rows[1].actor == "organizer@example.com"
    assert saved_rows[1].entity_type == "chart"
    assert saved_rows[1].entity_id == "e1"


def test_accepting_an_infeasible_proposal_refuses_and_writes_nothing() -> None:
    """ac6: two guests at a one-seat table — the infeasible proposal
    raises with the chart and audit untouched; at a two-seat table the
    same chart is feasible no-change and accepts."""
    repo = EventRepository(":memory:")
    event = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 1)],
    )
    saved = {"g1": "t1", "g2": "t1"}
    repo.save(event, "organizer")
    repo.save_chart("e1", saved, "organizer")

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=saved)
    assert proposal.status == "infeasible"
    assert proposal.assignments == {}
    assert proposal.comparison == ()
    assert proposal.infeasibility_report is not None

    before = list(repo.audit_entries("e1"))
    with pytest.raises(ValueError):
        repo.accept(proposal, "organizer@example.com")
    assert repo.load_chart("e1") == saved
    assert list(repo.audit_entries("e1")) == before

    # Same event, a table with room: feasible, nothing changes, accept succeeds.
    spacious = EventRepository(":memory:")
    spacious_event = Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
    )
    spacious.save(spacious_event, "organizer")
    spacious.save_chart("e1", saved, "organizer")

    proposal = optimize(spacious_event, CONFIG, mode=PLANNING, saved_chart=saved)
    assert proposal.status == "feasible"
    assert proposal.comparison == ()

    before = len(spacious.audit_entries("e1"))
    spacious.accept(proposal, "organizer@example.com")
    assert spacious.load_chart("e1") == saved
    assert len(spacious.audit_entries("e1")) == before + 1
