"""Acceptance test: a guest may belong to more than one group (ac4)."""

from seating_planner.domain import Group


def test_guest_in_multiple_groups() -> None:
    """A guest id added to two distinct groups is accepted into both, and
    each group's members report it."""
    family = Group(id="g1", name="Family")
    friends = Group(id="g2", name="Friends")
    family.add_guest("guest-1")
    friends.add_guest("guest-1")
    assert "guest-1" in family.member_ids
    assert "guest-1" in friends.member_ids
