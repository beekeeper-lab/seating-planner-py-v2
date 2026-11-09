"""Privacy tests for the guest-to-table CSV export: the allow-list, not the model, decides what goes in a CSV."""

import csv
import io
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.export import (
    DEFAULT_COLUMNS,
    guest_to_table_export,
)
from seating_planner.rules import Hardness, Rule, RuleKind

# Chosen so that neither an identifier nor a table name below appears in it.
NOTE_TEXT = "do not seat near the in-laws"
LATER_MODEL_VALUE = "zqx-9941"

ASSIGNMENTS: Mapping[str, str] = {"g1": "t1"}
PRIVATE_REQUEST = ("locked_to_table", "private_note")


def make_event() -> Event:
    # Bob is locked to t3 ("Reserved") and is NOT assigned to it; t3
    # appears nowhere in ASSIGNMENTS, so the only route its id or name
    # could take into the CSV is through the lock field.
    event = Event(
        id="e1",
        name="Wedding",
        guests=[
            Guest(id="g1", name="Alice", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(
                id="g2",
                name="Bob",
                rsvp_status=RsvpStatus.PENDING,
                seat_reserved=True,
            ),
        ],
        tables=[
            Table(id="t1", name="Family", capacity=8, shape="round", position=(0, 0)),
            Table(id="t2", name="Friends", capacity=8, shape="round", position=(2, 0)),
            Table(id="t3", name="Reserved", capacity=8, shape="round", position=(0, 2)),
        ],
    )
    event.lock_guest("g2", "t3")
    event.rules.append(
        Rule(
            id="r1",
            kind=RuleKind.SAME_TABLE,
            hardness=Hardness.HARD,
            guests=("g1", "g2"),
        )
    )
    # Guest is a plain dataclass with no __slots__: stand in for a
    # private field the domain does not have yet.
    bob = next(g for g in event.guests if g.id == "g2")
    bob.private_note = NOTE_TEXT  # type: ignore[attr-defined]
    return event


def header_of(csv_text: str) -> list[str]:
    return next(csv.reader(io.StringIO(csv_text)))


def test_default_export_excludes_private_fields() -> None:
    event = make_event()
    bundle = guest_to_table_export(event, ASSIGNMENTS)
    rows = list(csv.reader(io.StringIO(bundle.csv_text)))
    assert rows[0] == list(DEFAULT_COLUMNS)
    assert NOTE_TEXT not in bundle.csv_text  # the private note never appears
    assert "t3" not in bundle.csv_text  # the locked-only table's id
    assert "Reserved" not in bundle.csv_text  # ... and its name
    assert "r1" not in bundle.csv_text  # the rule definition is excluded


def test_export_uses_allowlist_not_serialization() -> None:
    event = make_event()
    alice = next(g for g in event.guests if g.id == "g1")
    alice.later_model_field = LATER_MODEL_VALUE  # type: ignore[attr-defined]
    alice.private_note = "a note value nobody asked for"  # type: ignore[attr-defined]
    bundle = guest_to_table_export(event, ASSIGNMENTS)
    assert header_of(bundle.csv_text) == list(DEFAULT_COLUMNS)
    assert "later_model_field" not in bundle.csv_text
    assert LATER_MODEL_VALUE not in bundle.csv_text
    assert "private_note" not in bundle.csv_text
    assert "a note value nobody asked for" not in bundle.csv_text


def test_private_export_warns_and_names_fields() -> None:
    event = make_event()
    bundle = guest_to_table_export(event, ASSIGNMENTS, include_private=PRIVATE_REQUEST)
    assert bundle.warning
    for name in PRIVATE_REQUEST:
        assert name in bundle.warning
    with pytest.raises(ValueError):
        guest_to_table_export(event, ASSIGNMENTS, include_private=("phone_number",))


def test_private_export_is_audited(tmp_path: Path) -> None:
    event = make_event()
    bundle = guest_to_table_export(
        event,
        ASSIGNMENTS,
        include_private=PRIVATE_REQUEST,
        actor="organizer",
    )
    csv_path = tmp_path / "export.csv"
    audit_path = tmp_path / "audit.jsonl"
    bundle.write(csv_path, audit_path)

    assert csv_path.exists()
    header = header_of(csv_path.read_text("utf-8"))
    for name in PRIVATE_REQUEST:
        assert name in header

    lines = audit_path.read_text("utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "private_guest_export"
    assert record["private_fields"] == list(PRIVATE_REQUEST)
    assert record["event_id"] == "e1"
    assert record["actor"] == "organizer"

    # A private write without an audit record is refused, leaving nothing.
    refused = tmp_path / "no-audit.csv"
    with pytest.raises(ValueError):
        bundle.write(refused)
    assert not refused.exists()

    # A default export writes only the CSV and creates no audit file.
    default = guest_to_table_export(event, ASSIGNMENTS)
    public_csv = tmp_path / "default.csv"
    public_audit = tmp_path / "default-audit.jsonl"
    default.write(public_csv, public_audit)
    assert public_csv.exists()
    assert not public_audit.exists()


def test_unwritable_audit_path_leaves_no_private_csv(tmp_path: Path) -> None:
    event = make_event()
    bundle = guest_to_table_export(event, ASSIGNMENTS, include_private=PRIVATE_REQUEST)

    # Missing parent directory: the error surfaces before any CSV byte exists.
    csv_path = tmp_path / "private.csv"
    bad_audit = tmp_path / "no-such-dir" / "audit.jsonl"
    with pytest.raises(OSError):
        bundle.write(csv_path, bad_audit)
    assert not csv_path.exists()

    # The fix is an ordering, not a refusal: the same bundle with a
    # writable audit path still gets both file and record.
    good_csv = tmp_path / "private-ok.csv"
    good_audit = tmp_path / "audit-ok.jsonl"
    bundle.write(good_csv, good_audit)
    assert good_csv.exists()
    lines = good_audit.read_text("utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["private_fields"] == list(PRIVATE_REQUEST)
