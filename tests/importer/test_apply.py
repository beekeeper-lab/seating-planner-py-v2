"""Task-2 tests: applying an import, opt-in partials, and up-front
auto-id reservation (FR-022/FR-023)."""

import dataclasses

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus
from seating_planner.importer import apply_import, preview_import


def _event_with_ada() -> Event:
    """An event holding one existing guest the apply targets."""
    event = Event(id="e1", name="Wedding")
    event.add_guest(
        Guest(
            id="g1",
            name="Ada Lovelace",
            rsvp_status=RsvpStatus.CONFIRMED,
            household="Lovelace Manor",
        )
    )
    return event


def _snapshot(event: Event) -> list[dict[str, object]]:
    """Deep snapshot of every guest; equality means nothing changed."""
    return [dataclasses.asdict(guest) for guest in event.guests]


def _guest_by_id(event: Event, guest_id: str) -> Guest:
    return next(guest for guest in event.guests if guest.id == guest_id)


def test_apply_matches_preview_counts() -> None:
    """Apply creates and updates exactly what the preview predicted."""
    csv_text = (
        "name,status,id\n"
        "Ada Lovelace,pending,g1\n"
        "Bob Stone,confirmed,\n"
        "Carl Mace,confirmed,imported-7\n"
    )
    event = _event_with_ada()
    preview = preview_import(event, csv_text)
    assert preview.invalid == () and preview.missing == ()
    assert preview.duplicates == ()
    assert preview.would_create == 2
    assert preview.would_update == 1

    report = apply_import(event, csv_text)
    assert report.created == preview.would_create
    assert report.updated == preview.would_update

    # The update: new status, blank optionals left as they were.
    ada = _guest_by_id(event, "g1")
    assert ada.rsvp_status is RsvpStatus.PENDING
    assert ada.household == "Lovelace Manor"
    assert ada.seat_reserved is False
    assert ada.locked_to_table is None

    # The creates: the explicit id kept, the no-id row got an auto id.
    bob = next(g for g in event.guests if g.name == "Bob Stone")
    assert bob.id != "imported-7" and bob.id.startswith("imported-")
    assert bob.rsvp_status is RsvpStatus.CONFIRMED
    carl = _guest_by_id(event, "imported-7")
    assert carl.name == "Carl Mace"
    assert [guest.id for guest in event.guests] == ["g1", bob.id, "imported-7"]


def test_partial_import_requires_opt_in() -> None:
    """Bad rows block a plain apply and are skipped only when opted in."""
    csv_text = (
        "name,status,household\n"
        "Fay Reed,confirmed,Reed Court\n"
        "Gus Hale,whenever,\n"
        "Heidi Poole,confirmed,\n"
        "Ivan Shaw,confirmed,\n"
    )
    event = _event_with_ada()
    before = _snapshot(event)
    with pytest.raises(ValueError, match="row 2"):
        apply_import(event, csv_text)
    assert _snapshot(event) == before
    assert [guest.id for guest in event.guests] == ["g1"]

    event2 = _event_with_ada()
    report = apply_import(event2, csv_text, allow_partial=True)
    assert report.created == 3
    assert report.updated == 0
    assert [guest.name for guest in event2.guests] == [
        "Ada Lovelace",
        "Fay Reed",
        "Heidi Poole",
        "Ivan Shaw",
    ]
    assert all(guest.name != "Gus Hale" for guest in event2.guests)


def test_an_explicit_id_never_collides_with_an_earlier_auto_generated_one() -> None:
    """The bean's fixture: a later row carrying the literal id an earlier
    auto-id assignment would have produced, previews clean and applies."""
    csv_text = "name,status,id\nAlice,confirmed,\nBob,confirmed,imported-1\n"
    event = Event(id="e1", name="Wedding")
    preview = preview_import(event, csv_text)
    assert preview.would_create == 2
    assert preview.invalid == ()
    assert preview.missing == ()
    assert preview.duplicates == ()

    report = apply_import(event, csv_text)
    assert report.created == 2
    assert report.updated == 0
    assert len(event.guests) == 2

    alice = next(g for g in event.guests if g.name == "Alice")
    bob = next(g for g in event.guests if g.name == "Bob")
    assert bob.id == "imported-1"
    assert alice.id != "imported-1"
    assert alice.id != bob.id
