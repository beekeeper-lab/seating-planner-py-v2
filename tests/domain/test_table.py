"""Acceptance test: table capacity validation and identifier uniqueness (ac1)."""

import pytest

from seating_planner.domain import Event, Table


def make_table(ident: str, capacity: int = 8) -> Table:
    return Table(
        id=ident,
        name=f"table-{ident}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def test_capacity_and_id_validation() -> None:
    """A Table refuses capacity 0 or negative, accepts 1, and an event
    refuses a second table with an identifier it already holds."""
    with pytest.raises(ValueError):
        make_table("t1", capacity=0)
    with pytest.raises(ValueError):
        make_table("t1", capacity=-3)
    assert make_table("t1", capacity=1).capacity == 1

    event = Event(id="e1", name="Wedding")
    event.add_table(make_table("t1"))
    with pytest.raises(ValueError):
        event.add_table(make_table("t1"))
    # The same identifiers are also rejected when the event is constructed
    # with both tables at once.
    with pytest.raises(ValueError):
        Event(
            id="e2",
            name="Wedding",
            tables=[make_table("t2"), make_table("t2")],
        )
