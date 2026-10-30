"""Acceptance tests for ranked event-day alternatives (FR-069, FR-070).

Six tests: the five acceptance criteria plus one for the seated
branch, which no acceptance criterion reaches:

* ac1 — a new guest with no valid seat stays unassigned, and the
  chart that comes back is exactly the baseline, with the new guest
  nowhere in it;
* ac2 — the refuted solve offers alternatives, and every one is drawn
  from the closed ALTERNATIVE_KINDS menu: in the full-room fixture
  exactly two, one add_table and one change_capacity, both at zero
  disruption;
* ac3 — the blocked-guest fixture pins the whole generation and
  ranking: kinds ["add_table", "exception", "exception", "unlock",
  "unlock"] with disruption counts [0, 0, 0, 1, 1], the exceptions in
  rule order, the unlocks in baseline order — and a direct
  sort-key check that (0, no violation) beats (1, weight 10) which
  beats (1, weight 50);
* ac4 — every alternative states its cost: an int disruption count in
  range, a non-empty detail, exactly the two disabled hard rules
  carried (unweighted, as the rules model makes them), and every
  other rule field None;
* ac5 — generation is read-only: with the event and the baseline
  snapshotted, two calls leave both unchanged, hand back a private
  copy of the assignments, and give equal alternatives;
* seated — in a room with room to spare the guest is seated at the
  scoring seat and no alternatives are offered at all.

Every fixture is small enough to work out by hand, and every guest is
CONFIRMED. Each test asserts a specific chart, sequence and count,
not a property it merely enumerates.
"""

from __future__ import annotations

from dataclasses import asdict

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import (
    ALTERNATIVE_KINDS,
    Alternative,
    SolverConfig,
    admit_new_guest,
)

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


def same_rule(rule_id: str, guests: tuple[str, ...], weight: int) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.SAME_TABLE,
        hardness=Hardness.SOFT,
        guests=guests,
        weight=weight,
    )


def different_table_rule(rule_id: str, guests: tuple[str, ...]) -> Rule:
    return Rule(
        id=rule_id,
        kind=RuleKind.DIFFERENT_TABLE,
        hardness=Hardness.HARD,
        guests=guests,
    )


def full_room_event() -> Event:
    """Scenario A: three guests, two seats, one table — a structural
    refutation with no rules to name and no pin worth removing."""
    return Event(
        id="e-full-room",
        name="Full room",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 2)],
        rules=[],
    )


def blocked_guest_event() -> Event:
    """Scenario B: g5's only two tables are each barred to them by a
    hard rule, and a soft rule fixes the winners' tie-broken form."""
    return Event(
        id="e-blocked",
        name="Blocked guest",
        guests=[guest("g1"), guest("g2"), guest("g3"), guest("g4"), guest("g5")],
        tables=[table("t1", 3), table("t2", 3)],
        rules=[
            different_table_rule("r-keep-g1-apart", ("g1", "g5")),
            different_table_rule("r-keep-g3-apart", ("g3", "g5")),
            same_rule("r-together-g2g5", ("g2", "g5"), 100),
        ],
    )


BLOCKED_BASELINE = {"g1": "t1", "g2": "t1", "g3": "t2", "g4": "t2"}


def test_guest_unassigned_nothing_moves() -> None:
    """ac1, scenario A: the guest with no valid seat stays unassigned
    and nothing they could have displaced moves. g1 and g2 sit at t1,
    which holds exactly two, and g3 is the new arrival there is no
    fourth seat for — the refutation is structural. The result must
    say "unassigned", hand back exactly {g1: t1, g2: t1}, and show
    g3 nowhere: they are not seated, not parked on a table, not
    counted at all."""
    baseline = {"g1": "t1", "g2": "t1"}

    result = admit_new_guest(
        full_room_event(),
        CONFIG,
        current_assignments=baseline,
        new_guest_id="g3",
    )

    assert result.status == "unassigned", (
        f"two seats for three guests: the solve is refuted and the "
        f"new guest stays unassigned, got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g2": "t1"}, (
        f"existing assignments come back exactly where they were, "
        f"got {result.assignments!r}"
    )
    assert "g3" not in result.assignments, (
        f"the unseated guest appears nowhere in the assignments, "
        f"got {result.assignments!r}"
    )


def test_alternatives_are_offered() -> None:
    """ac2, scenario A: the refutation offers from the closed menu.
    Three guests, two seats, one table, no rules: the only fixing
    families that can work are the capacity ones — add_table (g3 sits
    alone on the new capacity-1 table) or raising t1 to 3 (g3 joins
    it). Unlocking g1 or g2 makes room for nobody: there is no extra
    seat anywhere in the event — and no rule exists to except. So
    exactly two alternatives are on offer, one add_table and one
    change_capacity, both at zero disruption, no more and no fewer,
    and each kind is a member of ALTERNATIVE_KINDS."""
    baseline = {"g1": "t1", "g2": "t1"}

    result = admit_new_guest(
        full_room_event(),
        CONFIG,
        current_assignments=baseline,
        new_guest_id="g3",
    )

    assert result.alternatives, (
        f"a refuted arrival must be met with at least one alternative, "
        f"got {result.alternatives!r}"
    )
    assert all(
        kind in ALTERNATIVE_KINDS for kind in (a.kind for a in result.alternatives)
    ), (
        f"every offer is drawn from the FR-070 menu, "
        f"got {[a.kind for a in result.alternatives]!r}"
    )
    assert [a.kind for a in result.alternatives] == ["add_table", "change_capacity"], (
        f"the only fixing families that create a seat are the two "
        f"capacity ones — add_table first, then the raised t1 — got "
        f"{[a.kind for a in result.alternatives]!r}"
    )
    assert [a.disruption_count for a in result.alternatives] == [0, 0], (
        f"either fix seats g3 alone and moves no existing guest, "
        f"got {[a.disruption_count for a in result.alternatives]!r}"
    )


def test_alternatives_ranked_correctly() -> None:
    """ac3, scenario B: the whole generation order and the ranking.
    g5 may not join t1 (g1, hard) and may not join t2 (g3, hard), so
    the refutation is proven. add_table: g5 alone on the new table
    — offered, 0. change_capacity t1 or t2: g5 is still barred from
    both occupied tables — not offered. Unlock g1: g1 vacates to t2
    and g5 takes t1 — offered, 1 (only g1 moved); unlocking g3 is
    the symmetric 1; unlocking g2 or g4 changes nothing because
    g5's two tables stay barred — not offered. Either hard rule
    excepted is feasible at 0. The soft rule offers nothing itself;
    it fixes the charts so each count is unique. Ranked: kinds
    [add_table, exception, exception, unlock, unlock], disruptions
    [0, 0, 0, 1, 1], exceptions in rule order, unlocks in baseline
    order. Plus a direct check of the key itself: (0, no violation)
    beats (1, weight 10), which beats (1, weight 50) — FR-069's
    second key exercised on constructed values, since only hard
    rules, which carry no weight, may be violated by a generated one."""
    result = admit_new_guest(
        blocked_guest_event(),
        CONFIG,
        current_assignments=BLOCKED_BASELINE,
        new_guest_id="g5",
    )

    assert [a.kind for a in result.alternatives] == [
        "add_table",
        "exception",
        "exception",
        "unlock",
        "unlock",
    ], (
        f"add_table and the two excepted hard rules at zero disruption, "
        f"then the two pin releases at one, got "
        f"{[a.kind for a in result.alternatives]!r}"
    )
    assert [a.disruption_count for a in result.alternatives] == [0, 0, 0, 1, 1], (
        f"the capacity-free fixes cost nothing, each unlock moves "
        f"exactly its released guest, "
        f"got {[a.disruption_count for a in result.alternatives]!r}"
    )
    exceptions = [a for a in result.alternatives if a.kind == "exception"]
    assert [a.violated_rule_id for a in exceptions] == [
        "r-keep-g1-apart",
        "r-keep-g3-apart",
    ], (
        f"equal exceptions keep rule order, got "
        f"{[a.violated_rule_id for a in exceptions]!r}"
    )
    unlocks = [a for a in result.alternatives if a.kind == "unlock"]
    assert "g1" in unlocks[0].detail and "g3" in unlocks[1].detail, (
        f"equal unlocks keep baseline order — g1 pinned before g3, "
        f"got {[a.detail for a in unlocks]!r}"
    )

    no_move_no_violation = Alternative(
        kind="add_table", detail="add a table", disruption_count=0
    )
    one_move_weight_10 = Alternative(
        kind="unlock",
        detail="release one seat",
        disruption_count=1,
        violated_rule_weight=10,
    )
    one_move_weight_50 = Alternative(
        kind="exception",
        detail="disable one rule",
        disruption_count=1,
        violated_rule_weight=50,
    )
    ranked = sorted(
        [one_move_weight_50, no_move_no_violation, one_move_weight_10],
        key=Alternative.sort_key,
    )
    assert [a.disruption_count for a in ranked] == [0, 1, 1], (
        f"the no-move offer ranks before either one-move offer, got "
        f"{[a.disruption_count for a in ranked]!r}"
    )
    assert [a.violated_rule_weight for a in ranked] == [None, 10, 50], (
        f"within the same disruption the lighter violated rule ranks "
        f"first, got {[a.violated_rule_weight for a in ranked]!r}"
    )


def test_alternative_states_its_cost() -> None:
    """ac4, scenario B: every alternative states its cost. Each one
    carries an int disruption count between 0 and the four baseline
    guests and a non-empty detail; the sequence of costs down the
    ranked menu is exactly [0, 0, 0, 1, 1]; exactly two alternatives
    carry a violated_rule_id — and they are exactly the two disabled
    hard rules, r-keep-g1-apart and r-keep-g3-apart, each with
    violated_rule_weight None because hard rules carry no weight in
    the rules model; the other three leave both rule fields None."""
    result = admit_new_guest(
        blocked_guest_event(),
        CONFIG,
        current_assignments=BLOCKED_BASELINE,
        new_guest_id="g5",
    )

    for alternative in result.alternatives:
        assert isinstance(alternative.disruption_count, int), (
            f"the disruption count is an int, got "
            f"{type(alternative.disruption_count).__name__}"
        )
        assert 0 <= alternative.disruption_count <= len(BLOCKED_BASELINE), (
            f"the disruption counts baseline guests only, {len(BLOCKED_BASELINE)} "
            f"in this fixture, got {alternative.disruption_count}"
        )
        assert alternative.detail, (
            f"every alternative states its cost in one sentence, got "
            f"detail {alternative.detail!r}"
        )

    assert [a.disruption_count for a in result.alternatives] == [0, 0, 0, 1, 1], (
        f"each alternative states exactly the cost its re-solve proved, "
        f"got {[a.disruption_count for a in result.alternatives]!r}"
    )

    exceptions = [a for a in result.alternatives if a.violated_rule_id is not None]
    others = [a for a in result.alternatives if a.violated_rule_id is None]
    assert {a.violated_rule_id for a in exceptions} == {
        "r-keep-g1-apart",
        "r-keep-g3-apart",
    }, (
        f"exactly the two excepted hard rules carry their id, got "
        f"{[a.violated_rule_id for a in exceptions]!r}"
    )
    assert all(a.violated_rule_weight is None for a in exceptions), (
        f"hard rules carry no weight in the rules model, so the "
        f"violated weight is None, got "
        f"{[a.violated_rule_weight for a in exceptions]!r}"
    )
    assert len(others) == 3, (
        f"add_table and both unlocks break no rule, got {[a.kind for a in others]!r}"
    )
    assert all(
        a.violated_rule_id is None and a.violated_rule_weight is None for a in others
    ), (
        f"the non-exception offers leave both rule fields None, got "
        f"{[(a.violated_rule_id, a.violated_rule_weight) for a in others]!r}"
    )


def test_seated_guest_needs_no_alternatives() -> None:
    """The seated branch, which no acceptance test reaches: there is
    room, so nothing is offered at all. One table t1 of capacity 3
    holds g1 and g2; g3 is the new arrival and the soft rule wants
    all three together at weight 100. The main solve is feasible —
    g3 takes the open seat at t1 where the rule scores — so the
    result is "seated" with all three at t1 and an empty
    alternatives tuple: a feasible arrival generates no candidates,
    and the other admit_new_guest branch is proven without them."""
    event = Event(
        id="e-seated",
        name="Room to spare",
        guests=[guest("g1"), guest("g2"), guest("g3")],
        tables=[table("t1", 3)],
        rules=[same_rule("r-g1g2g3", ("g1", "g2", "g3"), 100)],
    )
    baseline = {"g1": "t1", "g2": "t1"}

    result = admit_new_guest(
        event,
        CONFIG,
        current_assignments=baseline,
        new_guest_id="g3",
    )

    assert result.status == "seated", (
        f"t1 holds two of three guests and g3 takes the open seat, "
        f"got status {result.status!r}"
    )
    assert result.assignments == {"g1": "t1", "g2": "t1", "g3": "t1"}, (
        f"the weight-100 rule scores only with all three at t1, and "
        f"g1 and g2 are already there, got {result.assignments!r}"
    )
    assert result.alternatives == (), (
        f"a seated guest is not offered alternatives, got {result.alternatives!r}"
    )


def test_alternatives_are_read_only() -> None:
    """ac5, scenario A: generation changes no saved state. The event
    and the baseline are snapshotted with dataclasses.asdict and a
    dict copy before two calls on the same input. After both: the
    event snapshot is unchanged — tables, rules, guests, locks — and
    the caller's baseline dict is unchanged. The returned
    assignments equals the baseline but is a private copy: mutating
    it does not reach the caller's dict. And two calls on the same
    input give equal alternatives — the offer depends only on the
    input, on nothing it is allowed to change."""
    event = full_room_event()
    baseline = {"g1": "t1", "g2": "t1"}
    snapshot = asdict(event)
    baseline_before = dict(baseline)

    first = admit_new_guest(
        event,
        CONFIG,
        current_assignments=baseline,
        new_guest_id="g3",
    )
    second = admit_new_guest(
        event,
        CONFIG,
        current_assignments=baseline,
        new_guest_id="g3",
    )

    assert asdict(event) == snapshot, (
        "every probe rides on a copy of the event, so the caller's "
        "event, its tables, rules and guests survive unchanged"
    )
    assert baseline == baseline_before, (
        f"the caller's baseline mapping survives the call unchanged, got {baseline!r}"
    )
    assert first.assignments == baseline_before, (
        f"the unassigned result carries the baseline chart, got {first.assignments!r}"
    )
    first.assignments["g1"] = "t-elsewhere"
    assert baseline == baseline_before, (
        f"the returned assignments is a private copy — mutating it "
        f"leaves the caller's dict intact, got {baseline!r}"
    )
    assert first.alternatives == second.alternatives, (
        f"two calls on the same input offer the same menu, got "
        f"{first.alternatives!r} vs {second.alternatives!r}"
    )
