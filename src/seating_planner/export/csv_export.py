"""Guest-to-table CSV export, assembled from an explicit field allow-list.

Privacy direction: a CSV row is built cell by cell from ``DEFAULT_COLUMNS``,
so a field added to the guest model never appears in an export unless it is
explicitly named in ``PRIVATE_GUEST_FIELDS``. Naming a private field attaches
a warning to the returned bundle before any file can be written, and
``write`` appends the audit record before the CSV is written — so a private
file is never left on disk without its record.

Standard library only; nothing in this module serializes a ``Guest`` or
``Event`` in bulk.
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from seating_planner.domain import Event

#: Every column the default export contains, in header order. A column
#: exists only if it is named here; nothing else ever gets a cell.
DEFAULT_COLUMNS: tuple[str, ...] = (
    "guest_id",
    "guest_name",
    "rsvp_status",
    "table_id",
    "table_name",
)

#: The only names that may cross the allow-list, each with a plain-English
#: sentence of what exposing it reveals.
#: Every column in the table-by-table export, in header order. A column
#: exists only if it is named here; nothing else ever gets a cell.
TABLE_BY_TABLE_COLUMNS: tuple[str, ...] = (
    "table_id",
    "table_name",
    "guest_id",
    "guest_name",
)

#: The only names that may cross the allow-list, each with a plain-English
#: sentence of what exposing it reveals.
PRIVATE_GUEST_FIELDS: dict[str, str] = {
    "locked_to_table": (
        "the table the organizer locked the guest to - an override of the optimizer"
    ),
    "private_note": "the organizer's private free-text note about the guest",
    "relationship_note": (
        "the organizer's free-text note about the guest's relationships"
    ),
}


@dataclass(frozen=True)
class GuestToTableExport:
    """A guest-to-table CSV, fully built but not yet on disk.

    ``warning`` is part of the return value, so for a private export the
    caller holds it before any file can have been written. ``write``
    honours the ordering: the audit record is appended before the private
    CSV becomes visible at its target path.
    """

    csv_text: str
    warning: str
    private_fields: tuple[str, ...]
    included_fields: tuple[str, ...]
    event_id: str
    actor: str
    guest_count: int

    def write(
        self,
        csv_path: str | os.PathLike[str],
        audit_log: str | os.PathLike[str] | None = None,
    ) -> Path:
        """Write the CSV to ``csv_path``; record a private write first.

        A private export refuses to be written without ``audit_log``; for a
        private write the audit line is appended before any byte of the CSV
        is created, so a failed log leaves nothing at the CSV path.
        """
        path = Path(csv_path)
        if self.private_fields:
            if audit_log is None:
                raise ValueError(
                    "this export includes private fields ("
                    + ", ".join(self.private_fields)
                    + ") and is refused without an audit_log"
                )
            record = {
                "event": "private_guest_export",
                "event_id": self.event_id,
                "actor": self.actor,
                "private_fields": list(self.private_fields),
                "guest_count": self.guest_count,
                "csv_file": str(path),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            with open(Path(audit_log), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        path.write_text(self.csv_text, encoding="utf-8")
        return path


def _dedupe_keep_order(names: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def guest_to_table_export(
    event: Event,
    assignments: Mapping[str, str],
    include_private: Sequence[str] = (),
    actor: str = "system",
) -> GuestToTableExport:
    """Build the guest-to-table CSV text plus its privacy envelope.

    One data row per guest in event order, cells read one by one from
    ``DEFAULT_COLUMNS`` and then the requested private fields via
    ``getattr(guest, field, None)`` — a field the domain does not have yet
    exports as empty rather than crashing. The returned ``warning`` names
    every requested private field and what it reveals; it is ``""`` for the
    default export.
    """
    unknown = [
        name
        for name in _dedupe_keep_order(include_private)
        if name not in PRIVATE_GUEST_FIELDS
    ]
    if unknown:
        raise ValueError(f"unknown private field name(s): {', '.join(unknown)}")
    private = _dedupe_keep_order(include_private)
    included = DEFAULT_COLUMNS + private
    table_names = {table.id: table.name for table in event.tables}

    rows: list[list[str]] = [list(included)]
    for guest in event.guests:
        table_id = assignments.get(guest.id, "")
        rows.append(
            [
                guest.id,
                guest.name,
                guest.rsvp_status.value,
                table_id,
                table_names.get(table_id, ""),
                *(_cell(getattr(guest, name, None)) for name in private),
            ]
        )

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)

    if private:
        warning = (
            "This export includes private guest fields: "
            + "; ".join(f"{name} - {PRIVATE_GUEST_FIELDS[name]}" for name in private)
            + "."
        )
    else:
        warning = ""

    return GuestToTableExport(
        csv_text=buffer.getvalue(),
        warning=warning,
        private_fields=private,
        included_fields=included,
        event_id=event.id,
        actor=actor,
        guest_count=len(event.guests),
    )


def table_by_table_export(event: Event, assignments: Mapping[str, str]) -> str:
    """Build the table-by-table CSV text: who is at which table.

    One data row per assigned guest — every assigned guest exactly once,
    unassigned guests nowhere — in table order (``event.tables``) and,
    within a table, guest order (``event.guests``). Cells are read one by
    one from ``TABLE_BY_TABLE_COLUMNS``; none carries private data by
    construction, so no audit or warning is attached.
    """
    rows: list[list[str]] = [list(TABLE_BY_TABLE_COLUMNS)]
    for table in event.tables:
        for guest in event.guests:
            if assignments.get(guest.id) != table.id:
                continue
            rows.append([table.id, table.name, guest.id, guest.name])

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()
