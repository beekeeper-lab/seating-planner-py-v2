"""Acceptance tests for proposals: an optimization's result until accepted (FR-072).

Five tests: the four pinned acceptance criteria plus one for
optimize's event-day branch, which no acceptance criterion reaches:

* ac1 — planning against scenario C hands back the feasible
  proposal and the store notices nothing: the loaded chart and the
  audit entries are still exactly the snapshots taken before the
  optimize; only a separate accept commits, and it commits the
  proposal's assignments with exactly one new chart_saved row;
* ac2 — the comparison lists every guest whose table would change,
  old and new table named: g2 moves t2 to t1, g3 is unseated, g4
  moves t1 to t2, and the unchanged g1 appears nowhere in it;
* ac3 — a no-change solve reads as "everything stays", not as
  nothing: status feasible, assignments equal to the saved chart,
  and the comparison present as an empty tuple;
* ac4 — declining is not calling anything, so a proposal that is
  never accepted leaves no trace: the loaded chart dict and the
  audit entries are identical to their snapshots;
* event-day — the baseline pins each eligible guest to their saved
  table and the declined guest's freed seat stays empty (FR-071),
  so the assignments are the saved chart minus g3 and the
  comparison is the single unseating, Change("g3", "t2", None).

The shared scenario C is small enough to work out by hand,
pre-verified against the real solver: g1, g2 and g4 are CONFIRMED
while g3 is DECLINED yet sits in the saved chart, the tables are
t1 of capacity 3 and t2 of capacity 1, and the rules are r1 SOFT
same_table(g1, g2) at weight 100 and r2 SOFT different_table(g1,
g4) at weight 50. The saved chart is
{"g1": "t1", "g2": "t2", "g3": "t2", "g4": "t1"}. The hand
arithmetic: the r1 pair needs two seats and only t1 holds any, so
it sits at t1 (+100); g4 scores r2 (+50) only at t2, and t2 is a
single seat — the unique optimum is {"g1": "t1", "g2": "t1",
"g4": "t2"} at soft score 150, no tie to break. Against the saved
chart that is three changes: g2 moves t2 to t1, g3 is unseated
(t2 to None — they declined, and a declined guest in a historical
chart is exactly what the comparison must show), g4 moves t1 to
t2, and g1 is unchanged and absent from the comparison.
"""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import Change, SolverConfig, optimize
from seating_planner.solver.hard import EVENT_DAY, PLANNING
from seating_planner.store import EventRepository

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)

SAVED_CHART = {"g1": "t1", "g2": "t2", "g3": "t2", "g4": "t1"}


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
    )


def declined_guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.DECLINED,
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def scenario_c_event() -> Event:
    """Scenario C, a fresh event per call: g3 has declined but the
    saved chart still seats them."""
    return Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2"), declined_guest("g3"), guest("g4")],
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


def test_optimize_does_not_commit() -> None:
    """ac1: optimize is read-only with respect to the store. The
    loaded chart and the audit entries survive the planning optimize
    on scenario C exactly as their snapshots; the proposal it hands
    back — feasible, seating the r1 pair at t1 and g4 at t2 — is
    applied only by the separate accept, which then leaves the
    loaded chart equal to the proposal's assignments with exactly
    one new chart_saved row."""
    repo = EventRepository(":memory:")
    event = scenario_c_event()
    repo.save(event, "organizer")
    repo.save_chart(event.id, SAVED_CHART, "organizer")
    chart_before = repo.load_chart(event.id)
    audit_before = list(repo.audit_entries(event.id))

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=SAVED_CHART)
    assert proposal.status == "feasible"
    assert proposal.assignments == {"g1": "t1", "g2": "t1", "g4": "t2"}

    assert repo.load_chart(event.id) == chart_before
    assert list(repo.audit_entries(event.id)) == audit_before

    repo.accept(proposal, "organizer@example.com")

    assert repo.load_chart(event.id) == proposal.assignments
    audit_after = repo.audit_entries(event.id)
    assert len(audit_after) == len(audit_before) + 1
    saved_rows = [entry for entry in audit_after if entry.action == "chart_saved"]
    assert len(saved_rows) == 2
    assert saved_rows[1].actor == "organizer@example.com"


def test_comparison_lists_every_change() -> None:
    """ac2: the comparison is exactly the three changes the module
    docstring's arithmetic names — the move, the unseating of the
    declined guest, and the other move, in guest-id order — and the
    unchanged g1 appears nowhere in it."""
    event = scenario_c_event()

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=SAVED_CHART)

    assert proposal.comparison == (
        Change("g2", "t2", "t1"),
        Change("g3", "t2", None),
        Change("g4", "t1", "t2"),
    )
    assert all(change.guest_id != "g1" for change in proposal.comparison)


def test_no_change_yields_empty_comparison() -> None:
    """ac3: two guests already seated at the one two-seat table, so
    planning optimizes to exactly the saved chart — and the
    comparison is still present, as an empty tuple, never absent."""
    event = Event(
        id="e-still",
        name="No change",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2)],
    )
    saved = {"g1": "t1", "g2": "t1"}

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=saved)

    assert proposal.status == "feasible"
    assert proposal.assignments == saved
    assert proposal.comparison == ()
    assert isinstance(proposal.comparison, tuple)


def test_declined_proposal_changes_nothing() -> None:
    """ac4: decline is not calling anything. After a planning
    optimize on scenario C whose proposal would change three
    guests, doing nothing else leaves the loaded chart equal to its
    snapshot dict and the audit entries the identical list — no
    trace of the proposal at all."""
    repo = EventRepository(":memory:")
    event = scenario_c_event()
    repo.save(event, "organizer")
    repo.save_chart(event.id, SAVED_CHART, "organizer")
    chart_before = dict(repo.load_chart(event.id))
    audit_before = list(repo.audit_entries(event.id))

    proposal = optimize(event, CONFIG, mode=PLANNING, saved_chart=SAVED_CHART)
    assert proposal.status == "feasible"
    assert proposal.comparison == (
        Change("g2", "t2", "t1"),
        Change("g3", "t2", None),
        Change("g4", "t1", "t2"),
    )

    assert repo.load_chart(event.id) == chart_before
    assert list(repo.audit_entries(event.id)) == audit_before


def test_event_day_proposal_pins_and_unseats() -> None:
    """The event-day branch, which no acceptance criterion reaches:
    each eligible guest is pinned to their saved table and the
    declined guest's freed seat stays empty, so the assignments are
    the saved chart minus g3 and the comparison is the single
    unseating named in the module docstring."""
    event = scenario_c_event()

    proposal = optimize(event, CONFIG, mode=EVENT_DAY, saved_chart=SAVED_CHART)

    assert proposal.status == "feasible"
    assert proposal.assignments == {"g1": "t1", "g2": "t2", "g4": "t1"}
    assert proposal.comparison == (Change("g3", "t2", None),)
