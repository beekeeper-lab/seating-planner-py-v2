"""CSV guest import preview: report what an import would do, mutating nothing.

Standard library only (``csv`` and ``dataclasses``); no Excel or Sheets
library. The preview is a pure function of the event and the text, so
cancelling it is a no-op by construction.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from seating_planner.domain import Event, RsvpStatus

#: Plain-text statement of the rule the preview applies (FR-022).
_DUPLICATE_RULE = (
    "A row is a likely duplicate when its explicit id was already carried by "
    "an earlier row of the same file, or when its name matches a guest "
    "already on the event by name and household: names are compared after "
    "stripping, case-folding and collapsing internal whitespace runs to a "
    "single space, and households count as the same only when both are "
    "non-empty and equal after that same normalisation."
)

_STATUSES = {member.value.casefold() for member in RsvpStatus}
_SEAT_TRUE = {"true", "yes", "1"}
_SEAT_FALSE = {"false", "no", "0"}
_KNOWN_COLUMNS = {"name", "status", "id", "household", "seat_reserved"}


@dataclass(frozen=True)
class ImportPreview:
    """What an import would do; every problem bucket is (row, reason)."""

    invalid: tuple[tuple[int, str], ...]
    missing: tuple[tuple[int, str], ...]
    duplicates: tuple[tuple[int, str], ...]
    would_create: int
    would_update: int
    duplicate_rule: str


@dataclass(frozen=True)
class _Row:
    """One data row; cells stripped, '' when absent or a short row."""

    number: int
    name: str
    status: str
    guest_id: str
    household: str
    seat_reserved: str


def _normalise(text: str) -> str:
    """Strip, collapse internal whitespace runs to one space, case-fold."""
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _parse(csv_text: str) -> list[_Row]:
    """Split the text into data rows; an empty file yields no rows."""
    if not csv_text.strip():
        return []
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return []

    columns: dict[str, int] = {}
    for position, title in enumerate(rows[0]):
        key = title.strip().casefold()
        if key in _KNOWN_COLUMNS:
            columns.setdefault(key, position)

    def cell(data: list[str], key: str) -> str:
        position = columns.get(key)
        if position is None or position >= len(data):
            return ""
        return data[position].strip()

    return [
        _Row(
            number=number,
            name=cell(data, "name"),
            status=cell(data, "status"),
            guest_id=cell(data, "id"),
            household=cell(data, "household"),
            seat_reserved=cell(data, "seat_reserved"),
        )
        for number, data in enumerate(rows[1:], start=1)
    ]


def _first_use(rows: list[_Row]) -> dict[str, int]:
    """Explicit id -> first data row of this file that carries it."""
    first: dict[str, int] = {}
    for row in rows:
        if row.guest_id:
            first.setdefault(row.guest_id, row.number)
    return first


def _event_duplicate(event: Event, row: _Row) -> str | None:
    """Guest id of an event guest matching name and household, else None."""
    household = _normalise(row.household)
    if not household:
        return None
    name = _normalise(row.name)
    for guest in event.guests:
        if _normalise(guest.name) != name:
            continue
        if _normalise(guest.household or "") == household:
            return guest.id
    return None


def _classify(event: Event, rows: list[_Row]) -> ImportPreview:
    """Classify each row exactly once: missing, invalid, duplicate, or
    create/update. The event is only read."""
    event_ids = {guest.id for guest in event.guests}
    id_first_use = _first_use(rows)
    invalid: list[tuple[int, str]] = []
    missing: list[tuple[int, str]] = []
    duplicates: list[tuple[int, str]] = []
    would_create = 0
    would_update = 0

    for row in rows:
        if not row.name:
            missing.append((row.number, "name is missing or blank"))
            continue
        if not row.status:
            missing.append((row.number, "status is missing or blank"))
            continue
        if row.status.casefold() not in _STATUSES:
            reason = (
                f"status {row.status!r} is not one of Confirmed, Pending, "
                "Declined or Cancelled"
            )
            invalid.append((row.number, reason))
            continue
        if row.seat_reserved:
            word = row.seat_reserved.casefold()
            if word not in _SEAT_TRUE and word not in _SEAT_FALSE:
                reason = (
                    f"seat_reserved {row.seat_reserved!r} is not one of "
                    "true/yes/1/false/no/0"
                )
                invalid.append((row.number, reason))
                continue
        if row.guest_id and id_first_use[row.guest_id] != row.number:
            earlier = id_first_use[row.guest_id]
            reason = (
                f"explicit id was already carried by an earlier row of this "
                f"file (row {earlier})"
            )
            duplicates.append((row.number, reason))
            continue
        matched = _event_duplicate(event, row)
        if matched is not None:
            reason = (
                "name and household match a guest already on the event "
                f"(guest {matched}), per the stated duplicate rule"
            )
            duplicates.append((row.number, reason))
            continue
        if row.guest_id and row.guest_id in event_ids:
            would_update += 1
        else:
            would_create += 1

    return ImportPreview(
        invalid=tuple(invalid),
        missing=tuple(missing),
        duplicates=tuple(duplicates),
        would_create=would_create,
        would_update=would_update,
        duplicate_rule=_DUPLICATE_RULE,
    )


def preview_import(event: Event, csv_text: str) -> ImportPreview:
    """Report what an import would do. Pure: no mutation, no I/O.

    Data rows are numbered from 1; the header line is not counted. Rows in
    the problem buckets are never counted as creates or updates.
    """
    return _classify(event, _parse(csv_text))


def cancel_import(preview: ImportPreview) -> None:
    """Discard a preview. A no-op by construction: the preview mutated
    nothing, so there is nothing to roll back."""
    del preview
