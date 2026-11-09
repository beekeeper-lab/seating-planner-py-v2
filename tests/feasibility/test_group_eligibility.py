"""bean-022: the oversized-group pre-flight check counts guests who will be seated.

The oversized-group finding compares a hard same-table group with the largest
table capacity, so it must count only the members the solver will seat — the
event's ``Guest.eligible`` guests (confirmed, or pending with a reserved
seat). Declined and unreserved-pending members must not make a feasible
event look impossible, and when the finding does fire its reported size is
the eligible count, not the raw membership.

Plain asserts only: every fixture is built through the bean-002/bean-003
constructors with explicit ids and capacities, and every assertion reads a
Finding the project returned — its kind, its rule_ids, its exact message —
never the test's own fixture arithmetic.
"""

from __future__ import annotations

from seating_planner.domain import Event, Group, Guest, RsvpStatus, Table
from seating_planner.feasibility import Finding, run_preflight
from seating_planner.rules import Hardness, Rule, RuleKind


def guest(guest_id: str, status: RsvpStatus, seat_reserved: bool = False) -> Guest:
    """A guest at the given RSVP status, name derived from the id."""
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=status,
        seat_reserved=seat_reserved,
    )


def table(table_id: str, capacity: int) -> Table:
    """A round table at the origin with the given capacity."""
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0, 0),
    )


_FAMILY_RULE = Rule(
    id="r-family",
    kind=RuleKind.SAME_TABLE,
    hardness=Hardness.HARD,
    group_id="grp1",
)


def test_ineligible_members_do_not_count() -> None:
    """ac1: the bean-022 measured scenario. A ten-member family group
    (six confirmed, four declined) must stay together at one table that
    seats eight. Six seats are needed and eight exist, so the event is
    feasible and the check must say so: no oversized-group finding, and
    no finding of any kind."""
    event = Event(
        id="e1",
        name="Family wedding",
        guests=[
            *[guest(f"g{i}", RsvpStatus.CONFIRMED) for i in range(1, 7)],
            *[guest(f"gd{i}", RsvpStatus.DECLINED) for i in range(1, 5)],
        ],
        tables=[table("t1", 8)],
        groups=[
            Group(
                id="grp1",
                name="Family",
                member_ids=[
                    *[f"g{i}" for i in range(1, 7)],
                    *[f"gd{i}" for i in range(1, 5)],
                ],
            )
        ],
        rules=[_FAMILY_RULE],
    )
    findings = run_preflight(event)
    assert findings == []


def test_eligible_members_are_the_size() -> None:
    """ac2: a nine-member family group must stay together — six confirmed,
    one pending with a reserved seat (eligible: seven), one declined and
    one unreserved pending (ineligible: two) — against tables seating five
    and three. The finding must fire and report the eligible size of 7,
    never the raw membership of 9; the total capacity (8) must not trip
    the sum check, so this is the only finding."""
    event = Event(
        id="e2",
        name="Family wedding",
        guests=[
            *[guest(f"g{i}", RsvpStatus.CONFIRMED) for i in range(1, 7)],
            guest("g7", RsvpStatus.PENDING, seat_reserved=True),
            guest("gd1", RsvpStatus.DECLINED),
            guest("gp1", RsvpStatus.PENDING),
        ],
        tables=[table("t1", 5), table("t2", 3)],
        groups=[
            Group(
                id="grp1",
                name="Family",
                member_ids=[
                    *[f"g{i}" for i in range(1, 8)],
                    "gd1",
                    "gp1",
                ],
            )
        ],
        rules=[_FAMILY_RULE],
    )
    findings = run_preflight(event)
    assert len(findings) == 1
    finding: Finding = findings[0]
    assert finding.kind == "group_larger_than_any_table"
    assert finding.rule_ids == ("r-family",)
    assert (
        finding.message
        == "group grp1 (Family) must stay together at 7, but the largest "
        "table seats 5"
    )


if __name__ == "__main__":
    tests = (
        test_ineligible_members_do_not_count,
        test_eligible_members_are_the_size,
    )
    for test in tests:
        test()
        print(f"{test.__name__}: ok")
    print(f"{len(tests)}/{len(tests)} group-eligibility tests passed")
