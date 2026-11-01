"""Tests for the table-by-table CSV export (ac5).

The contract is a counting one: every assigned guest exactly once and
nothing else — flat rows over a fixed four-column allow-list that has never
carried private data, so task-1's privacy discipline constrains it for free.
"""

import csv
import io
from collections import Counter

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.export import (
    DEFAULT_COLUMNS,
    TABLE_BY_TABLE_COLUMNS,
    guest_to_table_export,
    table_by_table_export,
)


def make_event() -> tuple[Event, dict[str, str]]:
    """Three tables, five guests; two assigned to the first table, one to
    the second, none to the third, and the two remaining guests
    unassigned."""
    event = Event(
        id="ev-garden",
        name="Garden Dinner",
        tables=[
            Table(id="t-a", name="Alpha", capacity=6, shape="round", position=(0, 0)),
            Table(id="t-b", name="Bravo", capacity=6, shape="round", position=(8, 0)),
            Table(id="t-c", name="Charlie", capacity=4, shape="oval", position=(4, 8)),
        ],
        guests=[
            Guest(id="g-ada", name="Ada Lin", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g-bea", name="Bea Chen", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g-cleo", name="Cleo Park", rsvp_status=RsvpStatus.PENDING),
            Guest(id="g-dan", name="Dan Ruiz", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g-eve", name="Eve Tran", rsvp_status=RsvpStatus.DECLINED),
        ],
    )
    assignments = {"g-ada": "t-a", "g-bea": "t-a", "g-cleo": "t-b"}
    return event, assignments


def parse_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_table_by_table_export_complete() -> None:
    # ac5: header is the allow-list exactly, and every assigned guest
    # appears on exactly one data row — the row of the table it was
    # assigned to — with the unassigned guests nowhere in the text.
    event, assignments = make_event()
    rows = parse_rows(table_by_table_export(event, assignments))
    assert rows[0] == list(TABLE_BY_TABLE_COLUMNS)
    data = rows[1:]
    assert len(data) == len(assignments)

    counts = Counter(row[2] for row in data)
    assert dict(counts) == {guest_id: 1 for guest_id in assignments}

    unassigned = [g.id for g in event.guests if g.id not in assignments]
    text = "\n".join(",".join(row) for row in data)
    for guest_id in unassigned:
        assert guest_id not in text

    tables = {table.id: table for table in event.tables}
    for row in data:
        table = tables[row[0]]
        assert row[1] == table.name
        assert assignments[row[2]] == row[0]

    guests = {guest.id: guest.name for guest in event.guests}
    for row in data:
        assert row[3] == guests[row[2]]


def test_guest_to_table_export_lists_every_guest_once() -> None:
    # Pins task-1's row contract that ac5 relies on: the same event and the
    # same assignments seen the same way — one data row per guest in event
    # order, right table cells when assigned, empty ones when not.
    event, assignments = make_event()
    rows = parse_rows(guest_to_table_export(event, assignments).csv_text)
    assert rows[0] == list(DEFAULT_COLUMNS)
    data = rows[1:]
    assert len(data) == len(event.guests)

    tables = {table.id: table for table in event.tables}
    for row, guest in zip(data, event.guests, strict=True):
        assert row[0] == guest.id
        assert row[1] == guest.name
        table_id = assignments.get(guest.id, "")
        assert row[3] == table_id
        assert row[4] == (tables[table_id].name if table_id else "")
