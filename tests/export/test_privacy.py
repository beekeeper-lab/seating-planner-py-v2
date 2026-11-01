"""Privacy tests for the guest-to-table CSV export (ac1–ac4).

An export may only contain what is explicitly named in ``DEFAULT_COLUMNS``;
the tests assert directions — header equality against the allow-list and
absence of known-private strings — not the shape of one happy CSV.
"""

import csv
import io
import json

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.export import (
    DEFAULT_COLUMNS,
    guest_to_table_export,
)
from seating_planner.rules import Hardness, Rule, RuleKind

# Note text chosen so no guest identifier, table name or rule id appears in
# it; if it showed up in a default export it could not be mistaken for data
# the public columns legitimately carry.
NOTE_TEXT = "The two cousins do not speak to each other"


def make_event() -> tuple[Event, dict[str, str]]:
    """A small event: three tables, three guests; one locked to a table the
    guest is not assigned to, and a rule definition present but excluded."""
    event = Event(
        id="ev-sunset",
        name="Sunset Venue",
        tables=[
            Table(id="t-a", name="Alpha", capacity=8, shape="round", position=(0, 0)),
            Table(id="t-b", name="Bravo", capacity=8, shape="round", position=(10, 0)),
            Table(
                id="t-head",
                name="Head of Room",
                capacity=6,
                shape="oval",
                position=(5, 10),
            ),
        ],
        guests=[
            Guest(id="g-ada", name="Ada Lin", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g-bea", name="Bea Chen", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g-cleo", name="Cleo Park", rsvp_status=RsvpStatus.PENDING),
        ],
        rules=[
            Rule(
                id="r-no-speaking",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                guests=("g-ada", "g-bea"),
            ),
        ],
    )
    # Bea is locked by the organizer to Head of Room, but the chart places
    # her at Bravo: the lock is override data the default export hides.
    event.lock_guest("g-bea", "t-head")
    event.guests[1].private_note = NOTE_TEXT  # type: ignore[attr-defined]
    assignments = {"g-ada": "t-a", "g-bea": "t-b"}
    return event, assignments


def parse_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_default_export_excludes_private_fields() -> None:
    # ac1: the default CSV carries no private note, rule definition or
    # override explanation; the public note field is not on the guest yet,
    # so everything that would leak is the note, the lock and the rule.
    event, assignments = make_event()
    bundle = guest_to_table_export(event, assignments)
    rows = parse_rows(bundle.csv_text)
    assert rows[0] == list(DEFAULT_COLUMNS)
    assert NOTE_TEXT not in bundle.csv_text
    assert "t-head" not in bundle.csv_text
    assert "Head of Room" not in bundle.csv_text
    assert "r-no-speaking" not in bundle.csv_text


def test_export_uses_allowlist_not_serialization() -> None:
    # ac2: a field added to the model is excluded by default; a row is the
    # allow-list, not the model's field list.
    event, assignments = make_event()
    event.guests[0].later_model_field = (  # type: ignore[attr-defined]
        "a fresh field to export or not"
    )
    bundle = guest_to_table_export(event, assignments)
    assert "later_model_field" not in bundle.csv_text
    assert "a fresh field to export or not" not in bundle.csv_text
    assert "private_note" not in bundle.csv_text
    assert NOTE_TEXT not in bundle.csv_text
    assert parse_rows(bundle.csv_text)[0] == list(DEFAULT_COLUMNS)


def test_private_export_warns_and_names_fields() -> None:
    # ac3: the warning naming each requested field is part of the return
    # value — in hand before any file could have been written.
    event, assignments = make_event()
    bundle = guest_to_table_export(
        event,
        assignments,
        include_private=("locked_to_table", "private_note"),
    )
    assert bundle.warning
    assert "locked_to_table" in bundle.warning
    assert "private_note" in bundle.warning
    with pytest.raises(ValueError):
        guest_to_table_export(event, assignments, include_private=("no_such_field",))


def test_private_export_is_audited(tmp_path) -> None:
    # ac4: the private export reaches disk with an audit line recording it,
    # and refuses to reach disk without one.
    event, assignments = make_event()
    bundle = guest_to_table_export(
        event,
        assignments,
        include_private=("locked_to_table", "private_note"),
        actor="organizer@example.com",
    )
    csv_path = tmp_path / "guests.csv"
    audit_log = tmp_path / "audit.jsonl"
    written = bundle.write(csv_path, audit_log)
    assert written == csv_path
    assert csv_path.is_file()
    rows = parse_rows(csv_path.read_text(encoding="utf-8"))
    assert "locked_to_table" in rows[0]
    assert "private_note" in rows[0]
    lines = audit_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "private_guest_export"
    assert record["private_fields"] == ["locked_to_table", "private_note"]
    assert record["event_id"] == "ev-sunset"
    assert record["actor"] == "organizer@example.com"

    refused = tmp_path / "no-audit.csv"
    with pytest.raises(ValueError):
        bundle.write(refused)
    assert not refused.exists()

    public = guest_to_table_export(event, assignments)
    public_csv = tmp_path / "public.csv"
    public_audit = tmp_path / "public-audit.jsonl"
    public.write(public_csv, public_audit)
    assert public_csv.is_file()
    assert not public_audit.exists()
