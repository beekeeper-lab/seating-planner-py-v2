# tests/solver/test_validate_on_use.py
"""Acceptance tests for checking the event as it stands, at use time
(bean-030, ac1/ac2/ac3).

Every event here is built validly through the constructors and then changed
by direct list or field assignment — that is the defect under test: the
checks ran once, at construction, and the objects were never re-checked.
ac1: in every mode the solve refuses a construction-check violation — a
soft weight out of 1..100, a weight on a hard rule, a non-numeric
distance, 501 guests, a duplicate guest id, a non-bool seat_reserved —
with an EventValidationError naming the rule, guest or limit, before the
solver runs. ac2: a lock left pointing at a table the event no longer has,
a group naming a guest the event does not, and a rule the same: refused
with an EventValidationError naming the id — never a raw KeyError out of
the model builder. ac3: the checks hold when the event has nothing to
seat — no eligible guests, no guests at all, no tables: an enabled rule
naming an id the event does not have, or an enabled hard rule of the kind
the solve refuses, is still refused; and a valid empty event still
answers as before, feasible with no eligible guests, infeasible with
confirmed guests and no tables.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import (
    Event,
    EventValidationError,
    Group,
    Guest,
    RsvpStatus,
    Table,
)
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, SolveResult, solve_hard
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


def two_guest_event(rule: Rule) -> tuple[Event, dict[str, str]]:
    """The small ac1 shape: two confirmed guests, two tables, one rule;
    the baseline seats the pair apart, so nothing in these branches has
    to reach the solver to answer them.
    """
    event = Event(id="e1", name="Wedding")
    event.add_guest(guest("g1"))
    event.add_guest(guest("g2"))
    event.add_table(table("t1", 2))
    event.add_table(table("t2", 2))
    event.add_rule(rule)
    return event, {"g1": "t1", "g2": "t2"}


def solve_in_mode(event: Event, mode: str, baseline: dict[str, str]) -> SolveResult:
    """Solve in the mode with its baseline arguments: planning takes
    none, low-disruption its baseline and move limit, event-day the
    baseline with every pinned guest held in place."""
    if mode == LOW_DISRUPTION:
        return solve_hard(
            event,
            CONFIG,
            mode=LOW_DISRUPTION,
            current_assignments=baseline,
            move_limit=0,
        )
    if mode == EVENT_DAY:
        return solve_hard(event, CONFIG, mode=EVENT_DAY, current_assignments=baseline)
    return solve_hard(event, CONFIG, mode=PLANNING)


def assert_refused(
    event: Event, mode: str, baseline: dict[str, str], *fragments: str
) -> None:
    """The solve refuses the event as it stands, and the message names
    each fragment literally."""
    with pytest.raises(EventValidationError) as exc:
        solve_in_mode(event, mode, baseline)
    message = str(exc.value)
    for fragment in fragments:
        assert fragment in message, fragment


def test_mutated_event_is_refused() -> None:
    """ac1: in every mode, a construction-check violation made after
    construction is refused before any solve runs, with an
    EventValidationError naming the rule, guest or limit.
    """
    # A soft same-table rule whose weight is set outside 1..100.
    heavy = same_table("r-heavy", ("g1", "g2"), Hardness.SOFT, weight=10)
    event, baseline = two_guest_event(heavy)
    heavy.weight = 10**6
    for mode in MODES:
        assert_refused(event, mode, baseline, "r-heavy")

    # A hard rule given a weight: hard rules carry none.
    weighted = Rule(
        id="r-weighted",
        kind=RuleKind.DIFFERENT_TABLE,
        hardness=Hardness.HARD,
        guests=("g1", "g2"),
    )
    event, baseline = two_guest_event(weighted)
    weighted.weight = 10
    for mode in MODES:
        assert_refused(event, mode, baseline, "r-weighted")

    # A min-distance rule whose measure is set to prose, not a number.
    distant = Rule(
        id="r-distant",
        kind=RuleKind.MIN_DISTANCE,
        hardness=Hardness.SOFT,
        guests=("g1", "g2"),
        weight=10,
        distance_m=3.0,
    )
    event, baseline = two_guest_event(distant)
    distant.distance_m = "far apart"
    for mode in MODES:
        assert_refused(event, mode, baseline, "r-distant")

    # An event over the guest limit: one table, and the guests list
    # replaced wholesale with 501 unique confirmed guests.
    overstuffed = Event(id="e501", name="Wedding")
    overstuffed.add_table(table("only", 501))
    overstuffed.guests = [guest(f"g{i:03d}") for i in range(501)]
    chart = {g.id: "only" for g in overstuffed.guests}
    for mode in MODES:
        assert_refused(overstuffed, mode, chart, "500")

    # A duplicated guest id: the second guest of id g1 is built on its
    # own and appended around every domain check.
    duplicated = Event(id="e1", name="Wedding")
    duplicated.add_guest(guest("g1"))
    duplicated.add_table(table("t1", 3))
    duplicated.guests.append(
        Guest(id="g1", name="Guest g1 again", rsvp_status=RsvpStatus.CONFIRMED)
    )
    for mode in MODES:
        assert_refused(duplicated, mode, {"g1": "t1"}, "g1")

    # A confirmed guest whose seat_reserved is set to a string.
    seatless = Event(id="e1", name="Wedding")
    g1 = guest("g1")
    seatless.add_guest(g1)
    seatless.add_table(table("t1", 2))
    g1.seat_reserved = "no"
    for mode in MODES:
        assert_refused(seatless, mode, {"g1": "t1"}, "g1")


def test_dangling_reference_is_refused() -> None:
    """ac2: a reference left dangling by mutation — a lock pointing at a
    removed table, a group or a rule naming a guest the event does not
    have — is refused with an EventValidationError naming the id, never
    a raw KeyError out of the model builder (whose seat variables are
    keyed by the event's current tables).
    """
    # A lock outliving its table: g1 is locked to t2, then t2 goes.
    locked = Event(id="e1", name="Wedding")
    locked.add_guest(guest("g1"))
    locked.add_table(table("t1", 2))
    gone = table("t2", 2)
    locked.add_table(gone)
    locked.lock_guest("g1", "t2")
    locked.tables.remove(gone)
    for mode in MODES:
        assert_refused(locked, mode, {"g1": "t1"}, "t2", "g1")

    # A group naming a guest the event does not have.
    family = Event(id="e1", name="Wedding")
    family.add_guest(guest("g1"))
    family.add_table(table("t1", 2))
    group = Group("grp", "Family", ["g1"])
    family.add_group(group)
    group.member_ids = ["phantom"]
    assert_refused(family, PLANNING, {}, "phantom", "grp")

    # A rule naming a guest the event does not have.
    named = Event(id="e1", name="Wedding")
    named.add_guest(guest("g1"))
    named.add_guest(guest("g2"))
    named.add_table(table("t1", 2))
    rule = same_table("r-phantom", ("g1", "g2"), Hardness.SOFT, weight=10)
    named.add_rule(rule)
    rule.guests = ("g1", "phantom")
    assert_refused(named, PLANNING, {}, "phantom", "r-phantom")


def test_rules_checked_with_nothing_to_seat() -> None:
    """ac3: the checks hold even when the event settles before a solve
    could run — no eligible guests, no guests at all, no tables. An
    enabled rule naming an id the event does not have, and an enabled
    hard rule of the refusal kind (not a bare ValueError), are refused;
    and a valid empty event still answers as before.
    """
    # No eligible guests: the enabled soft rule names a guest the
    # event does not have.
    no_eligible = Event(id="e1", name="Wedding")
    no_eligible.add_guest(guest("g1", RsvpStatus.DECLINED))
    no_eligible.add_table(table("t1", 1))
    no_eligible.add_rule(
        same_table("r-ghost", ("g1", "ghost"), Hardness.SOFT, weight=10)
    )
    assert_refused(no_eligible, PLANNING, {}, "ghost", "r-ghost")

    # No guests at all: the enabled hard rule binds to a group the
    # event does not have — a group binding needs no guests.
    nobody = Event(id="e2", name="Wedding")
    nobody.add_table(table("t1", 2))
    nobody.add_rule(
        Rule(
            id="r-nobody",
            kind=RuleKind.SAME_TABLE,
            hardness=Hardness.HARD,
            group_id="grp-none",
        )
    )
    assert_refused(nobody, PLANNING, {}, "r-nobody", "grp-none")

    # No tables: the enabled soft rule names a guest the event does
    # not have.
    no_tables = Event(id="e3", name="Wedding")
    no_tables.add_guest(guest("g1"))
    no_tables.add_rule(same_table("r-ghost", ("g1", "ghost"), Hardness.SOFT, weight=10))
    assert_refused(no_tables, PLANNING, {}, "ghost")

    # Nothing to seat and a rule of the refusal kind: enabled, hard,
    # adjacent_seat, over the event's two ineligible guests.
    refusal = Event(id="e4", name="Wedding")
    refusal.add_guest(guest("g1", RsvpStatus.DECLINED))
    refusal.add_guest(guest("g2", RsvpStatus.PENDING))
    refusal.add_table(table("t1", 2))
    refusal.add_rule(
        Rule(
            id="r-adjacent",
            kind=RuleKind.ADJACENT_SEAT,
            hardness=Hardness.HARD,
            guests=("g1", "g2"),
        )
    )
    assert_refused(refusal, PLANNING, {}, "r-adjacent")

    # The valid empty events still answer as before: feasible with no
    # eligible guests and an empty chart, infeasible with a confirmed
    # guest and no tables to seat them at.
    settled = Event(id="e5", name="Wedding")
    settled.add_guest(guest("g1", RsvpStatus.DECLINED))
    settled.add_table(table("t1", 2))
    result = solve_hard(settled, CONFIG, mode=PLANNING)
    assert result.status == "feasible"
    assert result.assignments == {}

    stranded = Event(id="e6", name="Wedding")
    stranded.add_guest(guest("g1"))
    result = solve_hard(stranded, CONFIG, mode=PLANNING)
    assert result.status == "infeasible"
