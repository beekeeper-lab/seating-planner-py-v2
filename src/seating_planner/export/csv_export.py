"""Guest-to-table CSV export.

Privacy direction: a row is assembled cell by cell from ``DEFAULT_COLUMNS``,
so a field the guest model gains later is excluded by default rather than
picked up by serialising the guest. The only route past the allow-list is to
name a field from ``PRIVATE_GUEST_FIELDS``, which names each requested field
in the returned warning before any file exists and refuses to reach disk
without an audit record.
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

#: Every column the default export carries, in header order. Nothing else
#: gets a column unless a caller names it in ``PRIVATE_GUEST_FIELDS``.
DEFAULT_COLUMNS: tuple[str, ...] = (
    "guest_id",
    "guest_name",
    "rsvp_status",
    "table_id",
    "table_name",
)

#: The registry of private guest fields, each naming what exposing it
#: reveals. The domain has the first field today; the others are named now
#: so the registry is complete when the domain grows them.
PRIVATE_GUEST_FIELDS: dict[str, str] = {
    "locked_to_table": (
        "the table the organizer locked the guest to — an override of the optimizer"
    ),
    "private_note": "the organizer's private free-text note about the guest",
    "relationship_note": (
        "the organizer's free-text note about the guest's relationships"
    ),
}


@dataclass(frozen=True)
class GuestToTableExport:
    """A finished export: the text, the disclosure warning, and the facts
    an audit record must carry. The warning travels with the value, so it
    is in hand before anything can have been written."""

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
        """Persist the CSV, and for a private export an audit line with it.

        A private export is never written to disk without its record: the
        refusal happens before any file is created.
        """
        path = Path(csv_path)
        private = self.private_fields
        if private and audit_log is None:
            raise ValueError(
                "this export includes private guest fields "
                f"({', '.join(private)}); an audit_log path is required "
                "before it can be written"
            )
        path.write_text(self.csv_text, encoding="utf-8")
        if private and audit_log is not None:
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
        return path


def guest_to_table_export(
    event: Event,
    assignments: Mapping[str, str],
    include_private: Sequence[str] = (),
    actor: str = "system",
) -> GuestToTableExport:
    """Build the guest-to-table CSV for ``event``, one row per guest.

    Public cells come only from ``DEFAULT_COLUMNS``; anything in
    ``include_private`` must name a key of ``PRIVATE_GUEST_FIELDS``, and
    doing so is what turns on the warning and the audit requirement.
    Fields the domain does not carry yet export as empty, never as an error.
    """
    unknown = [name for name in include_private if name not in PRIVATE_GUEST_FIELDS]
    if unknown:
        raise ValueError(
            "unknown private guest field(s) in include_private: " + ", ".join(unknown)
        )
    private = tuple(dict.fromkeys(include_private))
    included_fields = DEFAULT_COLUMNS + private
    if private:
        clauses = "; ".join(f"{name}: {PRIVATE_GUEST_FIELDS[name]}" for name in private)
        warning = f"private guest fields included in this export — {clauses}."
    else:
        warning = ""

    table_names = {table.id: table.name for table in event.tables}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(included_fields)
    for guest in event.guests:
        table_id = assignments.get(guest.id, "")
        row = [
            guest.id,
            guest.name,
            guest.rsvp_status.value,
            table_id,
            table_names.get(table_id, ""),
        ]
        for name in private:
            value = getattr(guest, name, None)
            row.append("" if value is None else str(value))
        writer.writerow(row)

    return GuestToTableExport(
        csv_text=buffer.getvalue(),
        warning=warning,
        private_fields=private,
        included_fields=included_fields,
        event_id=event.id,
        actor=actor,
        guest_count=len(event.guests),
    )


#: Every column the table-by-table export carries, in header order. The
#: organizer's view — who is at which table — and, like the guest-to-table
#: export, nothing outside this allow-list ever gets a column.
TABLE_BY_TABLE_COLUMNS: tuple[str, ...] = (
    "table_id",
    "table_name",
    "guest_id",
    "guest_name",
)


def table_by_table_export(event: Event, assignments: Mapping[str, str]) -> str:
    """Build the table-by-table CSV: one flat row per assigned guest.

    Tables and guests run in event order; a guest on the event that
    ``assignments`` maps to a table on the event gets exactly one row and no
    other rows exist — unassigned guests have no row, empty tables no line,
    and assignments naming an unknown guest or table are skipped. Cells are
    allow-listed, so no privacy field reaches the text.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(TABLE_BY_TABLE_COLUMNS)
    for table in event.tables:
        for guest in event.guests:
            if assignments.get(guest.id) == table.id:
                writer.writerow([table.id, table.name, guest.id, guest.name])
    return buffer.getvalue()
