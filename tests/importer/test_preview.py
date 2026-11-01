"""Task-1 tests: the import preview and its no-op cancel (FR-022/FR-023)."""

import dataclasses

from seating_planner.domain import Event, Guest
from seating_planner.importer import cancel_import, preview_import

_CATEGORIES_CSV = """name,status,household,id,seat_reserved
Ada  lovelace,confirmed,Lovelace  Manor,imported-99,
Bob Stone,confirmed,Stone Villa,,yes
,confirmed,Orphan Row,,
Cara Vale,Attending,Vale Hall,,
Dave Ross,Confirmed,Ross Court,,
Erin Moss,declined,Moss Lane,,
"""

_MIXED_CSV = """name,status,household,id
Ada  Lovelace,Pending,Lovelace Manor,x1
Zed   Byrne,Cancelled,,g3
Nova Kim,confirmed,,
Bad Row,?,
"""


def make_event() -> Event:
    """An event with the two guests the CSVs above reference."""
    event = Event(id="e1", name="Wedding")
    event.add_guest(
        Guest(
            id="g1",
            name="Ada Lovelace",
            rsvp_status="Confirmed",
            household="Lovelace Manor",
        )
    )
    event.add_guest(
        Guest(
            id="g3",
            name="Zed Byrne",
            rsvp_status="Pending",
            household="Byrne Cottage",
        )
    )
    return event


def snapshot(event: Event) -> list[dict[str, object]]:
    """Deep snapshot of every guest; equality means nothing changed."""
    return [dataclasses.asdict(guest) for guest in event.guests]


def test_preview_reports_all_four_categories() -> None:
    """One row per problem bucket plus clean rows; counts and rule stated."""
    preview = preview_import(make_event(), _CATEGORIES_CSV)
    assert [row for row, _ in preview.duplicates] == [1]
    assert "g1" in preview.duplicates[0][1]
    assert [row for row, _ in preview.missing] == [3]
    assert [row for row, _ in preview.invalid] == [4]
    assert preview.would_create == 3
    assert preview.would_update == 0
    assert preview.duplicate_rule
    lowered = preview.duplicate_rule.casefold()
    assert "name" in lowered and "household" in lowered


def test_preview_is_read_only() -> None:
    """A file with creates, updates and bad rows changes nothing."""
    event = make_event()
    before = snapshot(event)
    preview = preview_import(event, _MIXED_CSV)
    assert preview.would_create == 1
    assert preview.would_update == 1
    assert len(preview.invalid) == 1
    assert len(preview.duplicates) == 1
    assert snapshot(event) == before


def test_cancel_changes_nothing() -> None:
    """Preview then cancel: the event still holds its original guests."""
    event = make_event()
    before = snapshot(event)
    original_ids = [guest.id for guest in event.guests]
    preview = preview_import(event, _MIXED_CSV)
    cancel_import(preview)
    assert [guest.id for guest in event.guests] == original_ids
    assert snapshot(event) == before
