"""Acceptance tests for locked assignments (bean-011, FR-058).

Four tests, one per acceptance criterion:

* ac1 — a locked guest is seated at the locked table by the solver
  itself, and the lock decides things before the search: the soft rule
  wants all three guests together, but the locked guest stays alone at
  its one-seat table;
* ac2 — table-level locks hold against re-optimisation: without locks
  the optimum spreads three pairs across the two tables, and locking
  the trio at t1 keeps them there even though moving them would score
  better;
* ac4 — only an explicit unlock releases a lock: after unlocking, the
  re-optimisation moves every guest to the only chart the soft rule
  prefers;
* ac5 — a lock versus a hard rule is a proven refutation that names
  both sides: the rule lands in conflict_rule_ids and the lock lands in
  an "unlock" recommendation naming the guest and its locked table.

Every fixture is small enough to work out by hand and each test asserts
a specific chart, not a property it merely enumerates.
"""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


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


def rule(
    rule_id: str,
    kind: RuleKind,
    hardness: Hardness,
    guests: tuple[str, ...],
    weight: int | None = None,
) -> Rule:
    return Rule(id=rule_id, kind=kind, hardness=hardness, guests=guests, weight=weight)


def test_locked_guest_does_not_move() -> None:
    """ac1: the organizer's lock beats the optimizer's preference. A
    weight-100 soft same-table rule wants g1, g2, g3 all together, but
    g1 is locked at t1, which holds exactly one seat — so the solved
    chart seats g1 at t1 alone and t1 holds exactly one guest, decided
    by the model, not by any post-solve correction."""
    event = Event(
        id="e-ac1",
        name="Locked alone",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 1), table("t2", 3)],
        rules=[
            rule(
                "r-same",
                RuleKind.SAME_TABLE,
                Hardness.SOFT,
                ("g1", "g2", "g3"),
                weight=100,
            ),
        ],
    )
    event.lock_guest("g1", "t1")

    result = solve_hard(event, CONFIG)

    assert result.status == "feasible", (
        f"one locked guest, four seats, no hard rule: a chart exists, "
        f"got status {result.status!r}"
    )
    assert result.assignments.get("g1") == "t1", (
        f"g1 is locked at t1, so the solver itself must seat g1 there, "
        f"got {result.assignments!r}"
    )
    at_t1 = [g for g, t in result.assignments.items() if t == "t1"]
    assert at_t1 == ["g1"], (
        f"t1 holds exactly one seat and g1 fills it, so the other two "
        f"guests sit at t2; t1 instead holds {at_t1!r}"
    )


def test_table_level_lock_holds() -> None:
    """ac2: re-optimisation honours table-level locks. Six guests over
    two three-seat tables, three weight-100 soft same-table rules on the
    pairs (g1, g4) (g2, g5) (g3, g6): the optimum scores 200 and it must
    never want the trio g1 g2 g3 sitting together at t1 — otherwise the
    locks below would hold nothing. With g1, g2, g3 locked at t1, the
    same event stays feasible and all three come out at t1."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Locked trio",
            guests=[guest(f"g{i}") for i in range(1, 7)],
            tables=[table("t1", 3), table("t2", 3)],
            rules=[
                rule(
                    "r-above",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g1", "g4"),
                    weight=100,
                ),
                rule(
                    "r-mid",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g2", "g5"),
                    weight=100,
                ),
                rule(
                    "r-below",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g3", "g6"),
                    weight=100,
                ),
            ],
        )

    unlocked = solve_hard(build_event("e-ac2-unlocked"), CONFIG)
    assert unlocked.status == "feasible", (
        f"the locked-trio event has a chart, got status {unlocked.status!r}"
    )
    assert unlocked.soft_score == 200, (
        f"two of the three soft pairs share a table at the optimum, "
        f"got soft_score {unlocked.soft_score}"
    )
    trio_at_t1 = sorted(
        g for g in ("g1", "g2", "g3") if unlocked.assignments.get(g) == "t1"
    )
    assert trio_at_t1 != ["g1", "g2", "g3"], (
        f"If every soft pair sat below at t2, t1 would need all of "
        "g1 g2 g3 together — which the rules forbid — so the optimum "
        f"cannot put the trio at t1, got {trio_at_t1!r}"
    )

    locked_event = build_event("e-ac2-locked")
    for guest_id in ("g1", "g2", "g3"):
        locked_event.lock_guest(guest_id, "t1")

    locked = solve_hard(locked_event, CONFIG)
    assert locked.status == "feasible", (
        f"locking the trio at t1 still leaves every pair a table, "
        f"got status {locked.status!r}"
    )
    for guest_id in ("g1", "g2", "g3"):
        assert locked.assignments.get(guest_id) == "t1", (
            f"{guest_id} is locked at t1, so the re-optimisation must "
            f"not move it, got {locked.assignments!r}"
        )


def test_unlock_allows_move() -> None:
    """ac4: the lock moves only when it is released. The ac1 fixtures —
    the soft rule wants all three guests together and only t2 fits all
    of them — come apart the moment g1's lock is explicitly unlocked:
    g1, g2 and g3 all come out at t2, which is the only chart scoring
    the weight-100 rule."""

    def build_event(event_id: str) -> Event:
        return Event(
            id=event_id,
            name="Unlock and move",
            guests=[guest("g1"), guest("g2"), guest("g3")],
            tables=[table("t1", 1), table("t2", 3)],
            rules=[
                rule(
                    "r-same",
                    RuleKind.SAME_TABLE,
                    Hardness.SOFT,
                    ("g1", "g2", "g3"),
                    weight=100,
                ),
            ],
        )

    locked_event = build_event("e-ac4-locked")
    locked_event.lock_guest("g1", "t1")
    locked = solve_hard(locked_event, CONFIG)
    assert locked.status == "feasible", (
        f"the locked ac1 fixtures have a chart, got status {locked.status!r}"
    )
    assert locked.assignments.get("g1") == "t1", (
        f"while the lock stands, g1 sits at t1, got {locked.assignments!r}"
    )

    locked_event.unlock_guest("g1")
    unlocked = solve_hard(locked_event, CONFIG)
    assert unlocked.status == "feasible", (
        f"releasing the lock leaves the event seatable, got status {unlocked.status!r}"
    )
    for guest_id in ("g1", "g2", "g3"):
        assert unlocked.assignments.get(guest_id) == "t2", (
            f"t2 is the only table that fits all three of the guests "
            f"together, so after unlock every one of them sits there; "
            f"got {unlocked.assignments!r}"
        )


def test_lock_versus_hard_rule_conflict() -> None:
    """ac5: a clash between a lock and a hard rule is a proven
    refutation that names both sides. g1 locked at
    one-seat t1, a hard same-table rule binding g1 and g2: the rule
    would need both at one table, the lock forbids it — so conflict_rule_ids
    names exactly the rule, at least one "unlock" recommendation names
    the guest and the locked table, and at least one recommendation
    names the rule id."""
    event = Event(
        id="e-ac5",
        name="Lock versus rule",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 1), table("t2", 2)],
        rules=[rule("r-same", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2"))],
    )
    event.lock_guest("g1", "t1")

    result = solve_hard(event, CONFIG)

    assert result.status == "infeasible", (
        f"the hard same-table rule and g1's one-seat lock cannot both "
        f"hold, got status {result.status!r}"
    )
    assert result.assignments == {}, (
        f"a proven refutation never hands back a partial chart, "
        f"got {result.assignments!r}"
    )
    report = result.infeasibility_report
    assert report is not None, "an infeasible result must carry its report"
    assert report.conflict_rule_ids == ("r-same",), (
        f"the rule the refutation names is exactly the hard one, "
        f"got {report.conflict_rule_ids!r}"
    )
    unlock_recs = [r for r in report.recommendations if r.kind == "unlock"]
    assert unlock_recs, (
        f"the refutation must name the lock with an unlock recommendation, "
        f"got {report.recommendations!r}"
    )
    assert any("g1" in r.detail and "t1" in r.detail for r in unlock_recs), (
        f"the unlock recommendation must name the locked guest and its "
        f"table, got {[r.detail for r in unlock_recs]!r}"
    )
    assert any("r-same" in r.detail for r in report.recommendations), (
        f"some recommendation must name the conflicting rule, "
        f"got {[r.detail for r in report.recommendations]!r}"
    )
