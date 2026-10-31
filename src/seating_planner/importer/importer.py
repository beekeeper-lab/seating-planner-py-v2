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

from seating_planner.domain import MAX_GUESTS, Event, Guest, RsvpStatus

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
class ImportReport:
    """The counts of rows an apply actually applied."""

    created: int
    updated: int


@dataclass(frozen=True)
class _Row:
    """One data row; cells stripped, '' when absent or a short row."""

    number: int
    name: str
    status: str
    guest_id: str
    household: str
    seat_reserved: str


@dataclass(frozen=True)
class _Decision:
    """One row's classification: its bucket, plus a reason for problem rows."""

    row: _Row
    bucket: str  # "missing", "invalid", "duplicate", "create" or "update"
    reason: str = ""


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


def _classify(event: Event, rows: list[_Row]) -> list[_Decision]:
    """Classify each row exactly once: missing, invalid, duplicate, or
    create/update. The preview and the apply both use this; the event is
    only read."""
    event_ids = {guest.id for guest in event.guests}
    id_first_use = _first_use(rows)
    decisions: list[_Decision] = []

    for row in rows:
        if not row.name:
            decisions.append(_Decision(row, "missing", "name is missing or blank"))
            continue
        if not row.status:
            decisions.append(_Decision(row, "missing", "status is missing or blank"))
            continue
        if row.status.casefold() not in _STATUSES:
            reason = (
                f"status {row.status!r} is not one of Confirmed, Pending, "
                "Declined or Cancelled"
            )
            decisions.append(_Decision(row, "invalid", reason))
            continue
        if row.seat_reserved:
            word = row.seat_reserved.casefold()
            if word not in _SEAT_TRUE and word not in _SEAT_FALSE:
                reason = (
                    f"seat_reserved {row.seat_reserved!r} is not one of "
                    "true/yes/1/false/no/0"
                )
                decisions.append(_Decision(row, "invalid", reason))
                continue
        if row.guest_id and id_first_use[row.guest_id] != row.number:
            earlier = id_first_use[row.guest_id]
            reason = (
                f"explicit id was already carried by an earlier row of this "
                f"file (row {earlier})"
            )
            decisions.append(_Decision(row, "duplicate", reason))
            continue
        matched = _event_duplicate(event, row)
        if matched is not None:
            reason = (
                "name and household match a guest already on the event "
                f"(guest {matched}), per the stated duplicate rule"
            )
            decisions.append(_Decision(row, "duplicate", reason))
            continue
        if row.guest_id and row.guest_id in event_ids:
            decisions.append(_Decision(row, "update"))
        else:
            decisions.append(_Decision(row, "create"))

    return decisions


def _bucket(decisions: list[_Decision], bucket: str) -> list[tuple[int, str]]:
    """The (row, reason) pairs of one problem bucket, in row order."""
    return [(d.row.number, d.reason) for d in decisions if d.bucket == bucket]


def preview_import(event: Event, csv_text: str) -> ImportPreview:
    """Report what an import would do. Pure: no mutation, no I/O.

    Data rows are numbered from 1; the header line is not counted. Rows in
    the problem buckets are never counted as creates or updates.
    """
    decisions = _classify(event, _parse(csv_text))
    return ImportPreview(
        invalid=tuple(_bucket(decisions, "invalid")),
        missing=tuple(_bucket(decisions, "missing")),
        duplicates=tuple(_bucket(decisions, "duplicate")),
        would_create=sum(d.bucket == "create" for d in decisions),
        would_update=sum(d.bucket == "update" for d in decisions),
        duplicate_rule=_DUPLICATE_RULE,
    )


def cancel_import(preview: ImportPreview) -> None:
    """Discard a preview. A no-op by construction: the preview mutated
    nothing, so there is nothing to roll back."""
    del preview


_STATUS_BY_WORD = {member.value.casefold(): member for member in RsvpStatus}


def _resolve_status(word: str) -> RsvpStatus:
    """Map case-folded row text onto the domain enum; rows reaching this
    point already passed the preview's status check."""
    return _STATUS_BY_WORD[word.casefold()]


def _resolve_seat(word: str) -> bool | None:
    """Parse a seat_reserved cell; None means the cell was blank."""
    lowered = word.casefold()
    if lowered in _SEAT_TRUE:
        return True
    if lowered in _SEAT_FALSE:
        return False
    return None


def _next_auto_id(reserved: set[str]) -> str:
    """The lowest ``imported-N`` not already in the reserved set."""
    counter = 1
    while f"imported-{counter}" in reserved:
        counter += 1
    return f"imported-{counter}"


def _update_guest(guest: Guest, row: _Row) -> None:
    """Rewrite the fields an import may touch; a blank optional cell leaves
    the field as it was, and ``locked_to_table`` is never written."""
    guest.name = row.name
    guest.rsvp_status = _resolve_status(row.status)
    if row.household:
        guest.household = row.household
    seat = _resolve_seat(row.seat_reserved)
    if seat is not None:
        guest.seat_reserved = seat


def _problem_message(
    invalid: list[tuple[int, str]], missing: list[tuple[int, str]]
) -> str:
    parts = []
    if invalid:
        parts.append("invalid rows: " + "; ".join(f"row {n}: {r}" for n, r in invalid))
    if missing:
        parts.append(
            "missing-field rows: " + "; ".join(f"row {n}: {r}" for n, r in missing)
        )
    return (
        "cannot apply the import, these rows need fixing ("
        + "; ".join(parts)
        + "); re-run with allow_partial=True to import the remaining rows only"
    )


def apply_import(
    event: Event,
    csv_text: str,
    allow_partial: bool = False,
) -> ImportReport:
    """Apply an import, mutating ``event`` only when it is safe to.

    Re-derives the preview's classification from the same module
    internals. Invalid or missing rows raise ``ValueError`` before any
    mutation unless ``allow_partial`` is True, in which case only rows in
    no problem bucket are applied; duplicate rows are never applied.
    A file whose creates would push the event past ``MAX_GUESTS`` also
    raises before any mutation. Auto ids are reserved up front against
    the event's ids plus every explicit id in the file, so a later row's
    explicit id can never collide with an earlier row's generated id.
    """
    decisions = _classify(event, _parse(csv_text))
    if not allow_partial:
        invalid = _bucket(decisions, "invalid")
        missing = _bucket(decisions, "missing")
        if invalid or missing:
            raise ValueError(_problem_message(invalid, missing))

    creates = [d.row for d in decisions if d.bucket == "create"]
    if len(event.guests) + len(creates) > MAX_GUESTS:
        raise ValueError(
            f"an event holds at most {MAX_GUESTS} guests; applying "
            f"{len(creates)} creates would bring it to "
            f"{len(event.guests) + len(creates)}"
        )

    # Reserved once, up front, before any row is applied: every id already
    # on the event plus every explicit id carried anywhere in this file.
    reserved = {guest.id for guest in event.guests}
    reserved.update(d.row.guest_id for d in decisions if d.row.guest_id)
    by_id = {guest.id: guest for guest in event.guests}

    created = 0
    updated = 0
    for decision in decisions:
        if decision.bucket not in ("create", "update"):
            continue
        row = decision.row
        if decision.bucket == "update":
            _update_guest(by_id[row.guest_id], row)
            updated += 1
            continue
        guest_id = row.guest_id
        if not guest_id:
            guest_id = _next_auto_id(reserved)
            reserved.add(guest_id)
        seat = _resolve_seat(row.seat_reserved)
        event.add_guest(
            Guest(
                id=guest_id,
                name=row.name,
                rsvp_status=_resolve_status(row.status),
                household=row.household if row.household else None,
                seat_reserved=seat if seat is not None else False,
            )
        )
        created += 1

    return ImportReport(created=created, updated=updated)
