"""CSV export row contracts: the per-guest row export and the table-by-table view."""

import csv
from collections import Counter
from collections.abc import Mapping

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.export import (
    TABLE_BY_TABLE_COLUMNS,
    guest_to_table_export,
    table_by_table_export,
)

# Four of the five guests are assigned: two to the first table, one to the
# second, none to the third; the rest stay unassigned.
ASSIGNMENTS: Mapping[str, str] = {"g1": "t1", "g2": "t1", "g3": "t2"}


def make_event() -> Event:
    return Event(
        id="e1",
        name="Wedding",
        guests=[
            Guest(id="g1", name="Alice", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g2", name="Bob", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g3", name="Carol", rsvp_status=RsvpStatus.PENDING),
            Guest(id="g4", name="Dan", rsvp_status=RsvpStatus.PENDING),
            Guest(id="g5", name="Erin", rsvp_status=RsvpStatus.DECLINED),
        ],
        tables=[
            Table(id="t1", name="Family", capacity=8, shape="round", position=(0, 0)),
            Table(id="t2", name="Friends", capacity=8, shape="round", position=(2, 0)),
            Table(id="t3", name="Reserved", capacity=8, shape="round", position=(0, 2)),
        ],
    )


def test_table_by_table_export_complete() -> None:
    event = make_event()
    csv_text = table_by_table_export(event, ASSIGNMENTS)
    rows = list(csv.reader(csv_text.splitlines(True)))
    assert rows[0] == list(TABLE_BY_TABLE_COLUMNS)

    data = rows[1:]
    assert len(data) == len(ASSIGNMENTS)  # each assigned guest exactly once

    table_by_id = {table.id: table.name for table in event.tables}
    guest_by_id = {guest.id: guest.name for guest in event.guests}
    counted: Counter[str] = Counter()
    for table_id, table_name, guest_id, guest_name in data:
        assert table_name == table_by_id[table_id]
        assert guest_name == guest_by_id[guest_id]
        assert ASSIGNMENTS[guest_id] == table_id
        counted[guest_id] += 1
    assert dict(counted) == {guest_id: 1 for guest_id in ASSIGNMENTS}
    unassigned = [guest.id for guest in event.guests if guest.id not in ASSIGNMENTS]
    assert unassigned  # the event keeps unassigned guests
    for guest_id in unassigned:
        assert guest_id not in {row[2] for row in data}


def test_guest_to_table_export_lists_every_guest_once() -> None:
    event = make_event()
    csv_text = guest_to_table_export(event, ASSIGNMENTS).csv_text
    rows = list(csv.reader(csv_text.splitlines(True)))
    data = rows[1:]
    table_by_id = {table.id: table.name for table in event.tables}

    assert [row[0] for row in data] == [guest.id for guest in event.guests]
    for guest, row in zip(event.guests, data, strict=True):
        assert row[1] == guest.name
        table_id = row[3]
        if guest.id in ASSIGNMENTS:
            assert table_id == ASSIGNMENTS[guest.id]
            assert row[4] == table_by_id[table_id]
        else:
            assert table_id == ""
            assert row[4] == ""
