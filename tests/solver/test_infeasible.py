"""Acceptance tests for failed optimizations (bean-010, FR-050, FR-052).

Four tests, one per acceptance criterion:

* ac1 — an infeasible optimization leaves the previously saved chart
  byte-identical, writes no audit rows, and returns no partial chart;
* ac2 — the same preservation holds for a timed-out optimization, with the
  timeout pinned by forcing CP-SAT's real timeout status (UNKNOWN) instead
  of racing a wall-clock limit;
* ac3 — the infeasibility report names exactly the two hard rules of a
  hand-worked contradiction (same-table AND different-table on one pair,
  2 guests over 2 tables of capacity 2 — plenty of capacity left);
* ac4 — at least one corrective action is recommended from the closed
  vocabulary (add capacity, add a table, unlock, change a hard rule), for
  both the rule-conflict event and a pure capacity-shortage event.

The event is saved to a real file via EventRepository in every test, so the
saved chart is a byte-comparable file; the solver never touches that file on
a failure path, and these tests pin that absence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, SolverTimeout, hard, solve_hard
from seating_planner.store.repository import EventRepository

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)

#: The closed vocabulary of corrective actions (FR-050).
ALLOWED_KINDS = {"add_capacity", "add_table", "unlock", "change_hard_rule"}


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(table_id, f"Table {table_id}", capacity, "round", (0.0, 0.0))


def rule(rule_id: str, kind: RuleKind, guests: tuple[str, ...]) -> Rule:
    return Rule(id=rule_id, kind=kind, hardness=Hardness.HARD, guests=guests)


def conflict_event() -> Event:
    """Hand-worked contradiction: one hard same-table and one hard
    different-table rule on the same pair of guests, two tables of
    capacity 2 — four seats for two guests, so capacity is never the
    problem and the minimal conflict is exactly both rules."""
    return Event(
        id="e-conflict",
        name="Contradictory pair",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule("r-same", RuleKind.SAME_TABLE, ("g1", "g2")),
            rule("r-diff", RuleKind.DIFFERENT_TABLE, ("g1", "g2")),
        ],
    )


def plain_feasible_event() -> Event:
    """The timeout fixture: a plain event that solves cleanly. It carries
    no hard rules, so the stubbed UNKNOWN status — not the answer — is
    what the test pins."""
    return Event(
        id="e-plain",
        name="Plain event",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 4)],
    )


def capacity_shortage_event() -> Event:
    """Three eligible guests over two seats, no rules: infeasible by pure
    capacity, so no hard rule can be named in the conflict."""
    return Event(
        id="e-shortage",
        name="Too many guests",
        guests=[guest(f"g{i}") for i in range(1, 4)],
        tables=[table("t1", 2)],
    )


def save_event(event: Event, tmp_path: Path) -> tuple[EventRepository, Path]:
    """Persist *event* to a file under tmp_path; returns the repository
    and the database path, a byte-comparable saved chart."""
    db_path = tmp_path / f"{event.id}.sqlite3"
    repo = EventRepository(db_path)
    repo.save(event, actor="test")
    return repo, db_path


def test_saved_chart_unchanged_on_infeasible(tmp_path: Path) -> None:
    """ac1: an infeasible optimization preserves the previously saved chart
    byte-for-byte, grows no audit rows, and hands back no partial
    assignments."""
    event = conflict_event()
    repo, db_path = save_event(event, tmp_path)
    before = db_path.read_bytes()
    audit_before = len(repo.audit_entries(event.id))

    result = solve_hard(event, CONFIG, mode="planning")

    assert result.status == "infeasible", (
        f"the contradictory pair is unseatable by construction, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {}, (
        f"a failed solve must not hand back a partial chart, got {result.assignments!r}"
    )
    assert db_path.read_bytes() == before, (
        "FR-052: an infeasible optimization must not modify the "
        "last successfully saved chart"
    )
    assert len(repo.audit_entries(event.id)) == audit_before, (
        "a failed solve must not write audit log entries"
    )


def test_saved_chart_unchanged_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac2: a timed-out optimization preserves the previously saved chart
    byte-for-byte and writes no audit rows. The timeout is pinned by
    replacing CpSolver.solve — on the very module object solve_hard
    imports — with a stub returning cp_model.UNKNOWN, the exact status a
    real exhausted time limit produces, so the test asserts one
    deterministic outcome instead of racing the clock."""

    def _unsettled(_self: object, _model: object) -> int:
        return int(hard.cp_model.UNKNOWN)

    event = plain_feasible_event()
    repo, db_path = save_event(event, tmp_path)
    before = db_path.read_bytes()
    audit_before = len(repo.audit_entries(event.id))

    monkeypatch.setattr(hard.cp_model.CpSolver, "solve", _unsettled)
    with pytest.raises(SolverTimeout):
        solve_hard(event, CONFIG, mode="planning")

    assert db_path.read_bytes() == before, (
        "FR-052: a timed-out optimization must not modify the "
        "last successfully saved chart"
    )
    assert len(repo.audit_entries(event.id)) == audit_before, (
        "a failed solve must not write audit log entries"
    )


def test_conflict_names_hard_constraints(tmp_path: Path) -> None:
    """ac3: the infeasibility report names the specific hard constraints
    in the conflict — on the hand-worked contradiction, exactly the two
    rule ids, no more and no fewer."""
    event = conflict_event()
    save_event(event, tmp_path)

    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "infeasible", (
        f"the contradictory pair is unseatable by construction, "
        f"got status {result.status!r}"
    )

    data = json.loads(json.dumps(result.to_dict(), sort_keys=True))
    report = data.get("infeasibility_report")
    assert report is not None, (
        "an infeasible result must carry an infeasibility_report in to_dict()"
    )
    conflict = report["conflict_rule_ids"]
    assert len(conflict) == 2, (
        f"the minimal conflict is exactly the two rules, got {conflict!r}"
    )
    assert set(conflict) == {"r-same", "r-diff"}, (
        f"the conflict must name exactly the two contradictory rules, got {conflict!r}"
    )


def test_recommends_corrective_action(tmp_path: Path) -> None:
    """ac4: at least one corrective action is recommended — a non-empty
    list of {kind, detail} mappings whose kinds come from the closed
    vocabulary and whose details name the conflicting rule ids. A
    capacity-flavoured variant: more eligible guests than total table
    capacity yields an add_capacity or add_table recommendation and an
    empty conflict_rule_ids."""
    event = conflict_event()
    save_event(event, tmp_path)

    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "infeasible", (
        f"the contradictory pair is unseatable by construction, "
        f"got status {result.status!r}"
    )

    data = json.loads(json.dumps(result.to_dict(), sort_keys=True))
    report = data.get("infeasibility_report")
    assert report is not None, (
        "an infeasible result must carry an infeasibility_report in to_dict()"
    )
    recommendations = report["recommendations"]
    assert isinstance(recommendations, list) and recommendations, (
        "the report must recommend at least one corrective action, "
        f"got {recommendations!r}"
    )
    for rec in recommendations:
        assert isinstance(rec, dict), (
            f"each recommendation must be a mapping, got {type(rec).__name__}"
        )
        assert {"kind", "detail"} <= set(rec), (
            f"each recommendation must carry kind and detail, got {rec!r}"
        )
        assert rec["kind"] in ALLOWED_KINDS, (
            f"recommendation kind {rec['kind']!r} is outside the allowed "
            f"vocabulary {sorted(ALLOWED_KINDS)!r}"
        )
        assert isinstance(rec["detail"], str) and rec["detail"], (
            f"each recommendation must carry a non-empty detail, got {rec!r}"
        )
    for rule_id in ("r-same", "r-diff"):
        assert any(rule_id in rec["detail"] for rec in recommendations), (
            f"some recommendation must name conflicting rule {rule_id!r}"
        )

    # Capacity-flavoured variant: no rules, three eligible guests over two
    # seats — infeasible by pure capacity.
    shortage = capacity_shortage_event()
    save_event(shortage, tmp_path)
    shortage_result = solve_hard(shortage, CONFIG, mode="planning")
    assert shortage_result.status == "infeasible", (
        f"three guests over two seats is unseatable, "
        f"got status {shortage_result.status!r}"
    )
    shortage_data = json.loads(json.dumps(shortage_result.to_dict(), sort_keys=True))
    shortage_report = shortage_data.get("infeasibility_report")
    assert shortage_report is not None, (
        "an infeasible result must carry an infeasibility_report in to_dict()"
    )
    assert shortage_report["conflict_rule_ids"] == [], (
        f"pure capacity shortage implicates no rule, "
        f"got {shortage_report['conflict_rule_ids']!r}"
    )
    kinds = [rec["kind"] for rec in shortage_report["recommendations"]]
    assert any(kind in ("add_capacity", "add_table") for kind in kinds), (
        f"a capacity shortage must be met with add_capacity or add_table, "
        f"got kinds {kinds!r}"
    )
