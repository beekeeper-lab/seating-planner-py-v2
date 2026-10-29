"""Task-1 tests: table locks as domain data (ac3, ac4)."""

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table


def make_guest(guest_id: str = "g1", locked_to_table: str | None = None) -> Guest:
    return Guest(
        id=guest_id,
        name="Ada",
        rsvp_status=RsvpStatus.CONFIRMED,
        locked_to_table=locked_to_table,
    )


def make_table(table_id: str = "t1") -> Table:
    return Table(
        id=table_id, name=table_id, capacity=8, shape="round", position=(0.0, 0.0)
    )


def make_event() -> Event:
    event = Event(id="e1", name="Wedding")
    event.add_guest(make_guest())
    event.add_table(make_table())
    return event


def test_lock_unlock_roundtrip() -> None:
    """Locking stores the table id on the guest; unlocking sets it back to None."""
    event = make_event()
    event.lock_guest("g1", "t1")
    assert event.guests[0].locked_to_table == "t1"
    event.unlock_guest("g1")
    assert event.guests[0].locked_to_table is None


def test_lock_and_unlock_reject_unknown_ids() -> None:
    """Unknown guest or table ids each raise: locking with an unknown guest,
    locking with an unknown table, and unlocking an unknown guest."""
    event = make_event()
    with pytest.raises(ValueError):
        event.lock_guest("g-missing", "t1")
    with pytest.raises(ValueError):
        event.lock_guest("g1", "t-missing")
    with pytest.raises(ValueError):
        event.unlock_guest("g-missing")
    # The failed calls must not have changed anything.
    assert event.guests[0].locked_to_table is None


def test_lock_reference_must_name_a_table_in_the_event() -> None:
    """A guest whose locked_to_table points outside the event is rejected by
    the constructor and by add_guest, mirroring the duplicate-id checks."""
    with pytest.raises(ValueError):
        Event(
            id="e1",
            name="Wedding",
            guests=[make_guest(locked_to_table="t-missing")],
            tables=[make_table()],
        )
    event = make_event()
    with pytest.raises(ValueError):
        event.add_guest(make_guest("g2", locked_to_table="t-missing"))
    # The rejected guest must not have been added.
    assert [g.id for g in event.guests] == ["g1"]
