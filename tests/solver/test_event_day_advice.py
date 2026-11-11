# tests/solver/test_event_day_advice.py
"""Bean-031 red tests: an infeasible event-day report says what to do.

Four tests are red on the current tree, each by a plain assertion on the
report's recommendations: ac2 fails because the deletion-minimised kept set
names two of the three locked arrivals and g-2 goes unnamed; ac3 fails
because a chart that overfills its table gets unlock advice for the charted
guests instead of a capacity recommendation; ac5 fails on the
chart-overfill scenario, which names no capacity at all; ac6 fails because
of two chart guests each locked away from their table the report names only
one — deletion minimisation shrinks the second guest's self-contained
literal pair to nothing. The ac1 test is a regression pin for behaviour
this tree already has: every infeasible event-day shape below carries at
least one recommendation. Every fixture is worked out by hand and was
checked with a plain-python solve before being asserted: each premise
variant (one lock removed, all locks removed, the table's capacity raised)
comes back exactly as the corresponding assert demands.
"""

from __future__ import annotations

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.solver import SolverConfig, solve_hard
from seating_planner.solver.hard import EVENT_DAY

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def locked_guest(guest_id: str, table_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
        locked_to_table=table_id,
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def no_rules_event(
    event_id: str, name: str, guests: list[Guest], tables: list[Table]
) -> Event:
    return Event(id=event_id, name=name, guests=guests, tables=tables, rules=[])


def locked_arrivals_event(event_id: str, locked_ids: tuple[str, ...]) -> Event:
    """The ac2 shape: t-1 (cap 3) holds the baselined g-0 and g-1, t-2
    (cap 3) is free, and g-2, g-3, g-4 are new arrivals — locked to t-1
    when their id is in locked_ids, unmarked otherwise."""
    guests = [guest("g-0"), guest("g-1")]
    for guest_id in ("g-2", "g-3", "g-4"):
        guests.append(
            locked_guest(guest_id, "t-1") if guest_id in locked_ids else guest(guest_id)
        )
    return no_rules_event(
        "e-" + event_id,
        "New arrivals locked onto a nearly full table",
        guests,
        [table("t-1", 3), table("t-2", 3)],
    )


def chart_overfill_event(event_id: str, t1_capacity: int) -> Event:
    """The ac3 shape: the baseline chart seats g-0, g-1 and g-2 all at
    t-1, which only holds t1_capacity, beside an empty t-2 (cap 3)."""
    return no_rules_event(
        "e-" + event_id,
        "A chart that overfills its own table",
        [guest("g-0"), guest("g-1"), guest("g-2")],
        [table("t-1", t1_capacity), table("t-2", 3)],
    )


def contradicted_pair_event(event_id: str, with_locks: bool) -> Event:
    """The ac6 shape: g-3 and g-4 are charted at t-2 and, unless the
    variant drops the stored locks, each is locked to t-3."""
    tables = [table("t-1", 2), table("t-2", 4), table("t-3", 4)]
    guests = [guest("g-0"), guest("g-1"), guest("g-2")]
    for guest_id in ("g-3", "g-4"):
        guests.append(locked_guest(guest_id, "t-3") if with_locks else guest(guest_id))
    return no_rules_event(
        "e-" + event_id,
        "Two chart guests each locked off their table",
        guests,
        tables,
    )


def kinds(result) -> set[str]:
    assert result.infeasibility_report is not None, (
        "an infeasible result carries its report"
    )
    return {rec.kind for rec in result.infeasibility_report.recommendations}


def names(result, guest_id: str, table_id: str) -> bool:
    """True when some unlock recommendation names both the guest and the
    table the advice is about."""
    report = result.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    return any(
        rec.kind == "unlock" and guest_id in rec.detail and table_id in rec.detail
        for rec in report.recommendations
    )


def test_infeasible_event_day_always_advises() -> None:
    """ac1 (regression pin): six hand-checked ways an event-day chart plus
    the organizer's stored locks leave no valid assignment. Each solve
    must come back infeasible and hand back a report that already
    recommends at least one corrective action. The shapes: (a) three
    new arrivals locked onto the third seat of the charted table and
    past it; (b) the chart itself seating three into two seats; (c)
    every guest of the ac6 contradicted pair except the one unlocked;
    (d) a structural shortage, three guests and two seats on one
    table; (e) one chart guest locked onto the other table; (f) one
    new arrival locked onto the already full table."""
    locked_arrivals = locked_arrivals_event("ac1-a", ("g-2", "g-3", "g-4"))
    chart_overfill = chart_overfill_event("ac1-b", 2)
    contradicted_pair = contradicted_pair_event("ac1-c", with_locks=True)
    shortage = no_rules_event(
        "e-ac1-d",
        "Three guests and two seats on one table",
        [guest("g-0"), guest("g-1"), guest("g-2")],
        [table("t-1", 2)],
    )
    crossed = no_rules_event(
        "e-ac1-e",
        "A chart guest locked onto the other table",
        [guest("g-0"), locked_guest("g-2", "t-2")],
        [table("t-1", 2), table("t-2", 2)],
    )
    full_table = no_rules_event(
        "e-ac1-f",
        "A new guest locked onto the full table",
        [guest("g-1"), guest("g-2"), locked_guest("g-3", "t1")],
        [table("t1", 2), table("t2", 1)],
    )

    scenarios = (
        (locked_arrivals, {"g-0": "t-1", "g-1": "t-1"}),
        (chart_overfill, {"g-0": "t-1", "g-1": "t-1", "g-2": "t-1"}),
        (
            contradicted_pair,
            {"g-0": "t-1", "g-1": "t-1", "g-2": "t-1", "g-3": "t-2", "g-4": "t-2"},
        ),
        (shortage, {"g-0": "t-1", "g-1": "t-1"}),
        (crossed, {"g-0": "t-1", "g-2": "t-1"}),
        (full_table, {"g-1": "t1", "g-2": "t1"}),
    )
    unlocked_for = {2: frozenset({"g-2"})}

    for index, (event, baseline) in enumerate(scenarios):
        result = solve_hard(
            event,
            CONFIG,
            mode=EVENT_DAY,
            current_assignments=baseline,
            unlocked_guest_ids=unlocked_for.get(index),
        )
        assert result.status == "infeasible", (
            f"scenario {index}: the stored locks and the chart hand this "
            f"event no valid chart, got status {result.status!r}"
        )
        report = result.infeasibility_report
        assert report is not None, (
            f"scenario {index}: an infeasible result carries its report"
        )
        assert len(report.recommendations) >= 1, (
            f"scenario {index}: an infeasible event-day report must "
            f"recommend at least one corrective action, got {report.recommendations!r}"
        )


def test_locks_that_overfill_a_table_are_named() -> None:
    """ac2: three new arrivals are locked to t-1 beside the two charted
    there, three seats. The event has no rules, so the report is pure
    remedy advice: no hard-rule review is offered, only unlocks, and
    every one of the three locked guests is named with the table their
    lock holds — a report that withholds one of them is advice that
    cannot work. The premises hold: with only g-2 free the two kept
    locks still overfill t-1 and the solve stays infeasible; with no
    locks at all the five guests take the six seats and the solve is
    feasible."""
    chart = {"g-0": "t-1", "g-1": "t-1"}

    result = solve_hard(
        locked_arrivals_event("ac2-all-locked", ("g-2", "g-3", "g-4")),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert result.status == "infeasible", (
        "t-1 holds the two charted guests plus three locked ones "
        f"against three seats, got status {result.status!r}"
    )
    assert not any(
        rec.kind == "change_hard_rule"
        for rec in result.infeasibility_report.recommendations
    ), (
        "the event has no rules, so no hard-rule review is offered, got "
        f"{result.infeasibility_report.recommendations!r}"
    )
    assert kinds(result) == {"unlock"}, (
        "only the stored locks are at fault, so the report is all "
        f"unlock advice, got {result.infeasibility_report.recommendations!r}"
    )
    for guest_id in ("g-2", "g-3", "g-4"):
        assert names(result, guest_id, "t-1"), (
            f"the locked guest {guest_id} at t-1 must be named by an "
            f"unlock recommendation, got {result.infeasibility_report.recommendations!r}"
        )

    one_free = solve_hard(
        locked_arrivals_event("ac2-g2-free", ("g-3", "g-4")),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert one_free.status == "infeasible", (
        "with g-3 and g-4 still locked to t-1, freeing only g-2 does "
        f"not fix five occupants for three seats, got status {one_free.status!r}"
    )

    all_free = solve_hard(
        locked_arrivals_event("ac2-none-locked", ()),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert all_free.status == "feasible", (
        "with no locks stored the two charted hold their seats and the "
        "three arrivals take the free seats, got status "
        f"{all_free.status!r}"
    )


def test_a_chart_that_overfills_a_table_asks_for_capacity() -> None:
    """ac3: the baseline chart itself seats three guests at a two-seat
    table and the event stores no locks at all, so no unlock is a
    remedy anyone could carry out: the missing thing is a seat, and
    the report offers nothing but capacity advice, with the overfilled
    table named by the add_capacity line — no unlock and no rule
    review standing beside it. Raising t-1 to three seats solves the
    event feasible."""
    chart = {"g-0": "t-1", "g-1": "t-1", "g-2": "t-1"}

    result = solve_hard(
        chart_overfill_event("ac3-cap2", 2),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert result.status == "infeasible", (
        f"the chart seats three guests at two seats, got status {result.status!r}"
    )
    report = result.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    assert any(
        rec.kind == "add_capacity" and "t-1" in rec.detail
        for rec in report.recommendations
    ), f"the missing thing is a seat at t-1, got {report.recommendations!r}"
    assert not any(rec.kind == "change_hard_rule" for rec in report.recommendations), (
        f"the event has no rules, so none is reviewed, got {report.recommendations!r}"
    )
    assert {rec.kind for rec in report.recommendations} == {"add_capacity"}, (
        "no guest is stored-locked anywhere, so no unlock remedy exists "
        "beside the capacity remedy, got "
        f"{report.recommendations!r}"
    )

    raised = solve_hard(
        chart_overfill_event("ac3-cap3", 3),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert raised.status == "feasible", (
        "the same chart holds at three seats, so the capacity remedy "
        f"as advised really restores feasibility, got status {raised.status!r}"
    )


def test_fallback_advice_is_probed() -> None:
    """ac5: the report's fallback advice is probe-checked, one step for
    each shape. Part one — t-b (cap 2) holds the baselined g-1 plus
    new arrivals g-2 and g-3 both locked there: raising t-b alone
    would also seat them, so capacity is a tempting lie, yet the
    unlocks alone already suffice (g-2 and g-3 scatter across t-a's
    four free seats once their locks are gone). The report must offer
    exactly the unlocks — each guest named with t-b — and no
    add_capacity; and re-solved with the named locks removed the event
    is feasible. Part two — the chart overfill names its table in an
    add_capacity recommendation, and the event re-solved with that
    table at three seats is feasible: the capacity advice, like the
    unlock advice, is proven to restore feasibility before it is
    offered."""
    arrivals_chart = {"g-0": "t-a", "g-1": "t-b"}

    def arrivals_event(event_id: str, with_locks: bool) -> Event:
        guests = [guest("g-0"), guest("g-1")]
        for guest_id in ("g-2", "g-3"):
            guests.append(
                locked_guest(guest_id, "t-b") if with_locks else guest(guest_id)
            )
        return no_rules_event(
            "e-" + event_id,
            "Locked arrivals overfilling the baselined table",
            guests,
            [table("t-a", 4), table("t-b", 2)],
        )

    result = solve_hard(
        arrivals_event("ac5-locked", True),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=arrivals_chart,
    )
    assert result.status == "infeasible", (
        "t-b holds three occupants against two seats while the locks "
        f"hold all of them there, got status {result.status!r}"
    )
    assert kinds(result) == {"unlock"}, (
        "the unlocks alone restore feasibility, so the advice is all "
        "unlocks and no capacity line stands beside them, got "
        f"{result.infeasibility_report.recommendations!r}"
    )
    for guest_id in ("g-2", "g-3"):
        assert names(result, guest_id, "t-b"), (
            f"the locked arrival {guest_id} at t-b must be named, got "
            f"{result.infeasibility_report.recommendations!r}"
        )

    freed = solve_hard(
        arrivals_event("ac5-released", False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=arrivals_chart,
    )
    assert freed.status == "feasible", (
        "unlocking every guest the unlock recommendations name restores "
        f"feasibility in one step, got status {freed.status!r}"
    )

    chart = {"g-0": "t-1", "g-1": "t-1", "g-2": "t-1"}
    overfill = solve_hard(
        chart_overfill_event("ac5-overfill", 2),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert overfill.status == "infeasible", (
        f"three guests charted at two seats, got status {overfill.status!r}"
    )
    report = overfill.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    assert any(
        rec.kind == "add_capacity" and "t-1" in rec.detail
        for rec in report.recommendations
    ), f"the overfilled table t-1 must be named, got {report.recommendations!r}"
    raised = solve_hard(
        chart_overfill_event("ac5-raised", 3),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
    )
    assert raised.status == "feasible", (
        "adding the seat at every table the capacity advice names "
        f"restores feasibility, got status {raised.status!r}"
    )


def test_every_contradicted_guest_is_named_at_once() -> None:
    """ac6: two chart guests are each pinned to t-2 by the chart and
    demanded at t-3 by their stored lock, and neither is in
    unlocked. The deletion walk keeps one guest's self-contained
    literal pair and shrinks it to a single member, so the old report
    names only g-4 — following it leaves the event infeasible and
    costs another round trip. The correct report names both g-3 and
    g-4 at t-3 in the same step: no rule exists to be named, the
    advice is all unlocks, and the event re-solved with both stored
    locks removed (the same baseline, the same unlocked set) is
    feasible — every contradicted guest freed in one move."""
    chart = {"g-0": "t-1", "g-1": "t-1", "g-2": "t-1", "g-3": "t-2", "g-4": "t-2"}
    unlocked = frozenset({"g-2"})

    result = solve_hard(
        contradicted_pair_event("ac6-locked", with_locks=True),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
        unlocked_guest_ids=unlocked,
    )
    assert result.status == "infeasible", (
        "g-3 and g-4 are each charted at t-2 and locked to t-3, and "
        f"neither is unlocked, got status {result.status!r}"
    )
    report = result.infeasibility_report
    assert report is not None, "an infeasible result carries its report"
    assert report.conflict_rule_ids == (), (
        "the event has no rules, so the contradiction is between the "
        f"chart and the locks alone, got {report.conflict_rule_ids!r}"
    )
    assert {rec.kind for rec in report.recommendations} == {"unlock"}, (
        "seats are plentiful, so the only remedy is releasing the "
        f"contradicted locks, got {report.recommendations!r}"
    )
    for guest_id in ("g-3", "g-4"):
        assert names(result, guest_id, "t-3"), (
            f"both contradicted guests must be named at once in the "
            f"same report; {guest_id} is missing, got "
            f"{report.recommendations!r}"
        )

    released = solve_hard(
        contradicted_pair_event("ac6-released", with_locks=False),
        CONFIG,
        mode=EVENT_DAY,
        current_assignments=chart,
        unlocked_guest_ids=unlocked,
    )
    assert released.status == "feasible", (
        "unlocking every guest the report names restores feasibility "
        f"in one step, got status {released.status!r}"
    )
