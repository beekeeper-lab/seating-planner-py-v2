"""Domain models for events, tables, guests and groups.

The entire source of this bean lives in this one module: standard library only
(`dataclasses`, `enum`) — no persistence, no ortools. The rule model is owned
by a later bean; rules are stored here as opaque items.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Production limits; each bound is inclusive (the last item is accepted).
MAX_GUESTS: int = 500
MAX_TABLES: int = 60
MAX_RULES: int = 5000


class RsvpStatus(str, Enum):
    """Exactly four accepted values; anything else raises on construction."""

    CONFIRMED = "Confirmed"
    PENDING = "Pending"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"


@dataclass
class Table:
    """A physical table with a capacity, a shape and an (x, y) position.

    Position lives on an arbitrary unit plane; it is validated on
    construction and stored normalised to ``tuple[float, float]``.
    """

    id: str
    name: str
    capacity: int
    shape: str
    position: tuple[float, float]

    def __post_init__(self) -> None:
        if type(self.capacity) is not int:
            raise ValueError(f"capacity must be an int, got {self.capacity!r}")
        if self.capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {self.capacity}")
        if (
            not isinstance(self.position, (tuple, list))
            or len(self.position) != 2
            or not all(
                isinstance(p, (int, float)) and not isinstance(p, bool)
                for p in self.position
            )
        ):
            raise ValueError(
                "position must be a two-item sequence of int-or-float, "
                f"got {self.position!r}"
            )
        self.position = (float(self.position[0]), float(self.position[1]))


@dataclass
class Guest:
    """A wedding guest; ``eligible`` is derived, never stored (FR-019)."""

    id: str
    name: str
    rsvp_status: RsvpStatus
    household: str | None = None
    seat_reserved: bool = False

    @property
    def eligible(self) -> bool:
        """Confirmed, or Pending with an explicitly reserved seat."""
        if self.rsvp_status is RsvpStatus.CONFIRMED:
            return True
        return self.rsvp_status is RsvpStatus.PENDING and self.seat_reserved


@dataclass
class Group:
    """An ordered collection of member guest ids.

    A guest id may not appear twice in the same group, but may appear in any
    number of different groups.
    """

    id: str
    name: str
    member_ids: list[str] = field(default_factory=list)

    def add_guest(self, guest_id: str) -> None:
        if guest_id in self.member_ids:
            raise ValueError(f"guest {guest_id!r} is already in group {self.id!r}")
        self.member_ids.append(guest_id)


def _validate_event_contents(
    guests: Sequence[Guest],
    tables: Sequence[Table],
    rules: Sequence[object],
) -> None:
    """Shared rules for add_* methods and direct construction."""
    if len(guests) > MAX_GUESTS:
        raise ValueError(f"an event holds at most {MAX_GUESTS} guests")
    if len(tables) > MAX_TABLES:
        raise ValueError(f"an event holds at most {MAX_TABLES} tables")
    if len(rules) > MAX_RULES:
        raise ValueError(f"an event holds at most {MAX_RULES} rules")
    seen_guest_ids = set[object]()
    for guest in guests:
        if guest.id in seen_guest_ids:
            raise ValueError(f"duplicate guest identifier {guest.id!r}")
        seen_guest_ids.add(guest.id)
    seen_table_ids = set[object]()
    for table in tables:
        if table.id in seen_table_ids:
            raise ValueError(f"duplicate table identifier {table.id!r}")
        seen_table_ids.add(table.id)


@dataclass
class Event:
    """A wedding event: ordered collections of guests, tables, groups, rules.

    Duplicate guest or table identifiers are rejected, as is any collection
    that would exceed the production limits. The same rules apply whether an
    ``Event`` is built by repeated ``add_*`` calls or constructed with its
    collections directly.
    """

    id: str
    name: str
    guests: list[Guest] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    rules: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_event_contents(self.guests, self.tables, self.rules)

    def add_guest(self, guest: Guest) -> None:
        if len(self.guests) >= MAX_GUESTS:
            raise ValueError(f"an event holds at most {MAX_GUESTS} guests")
        if any(g.id == guest.id for g in self.guests):
            raise ValueError(f"duplicate guest identifier {guest.id!r}")
        self.guests.append(guest)

    def add_table(self, table: Table) -> None:
        if len(self.tables) >= MAX_TABLES:
            raise ValueError(f"an event holds at most {MAX_TABLES} tables")
        if any(t.id == table.id for t in self.tables):
            raise ValueError(f"duplicate table identifier {table.id!r}")
        self.tables.append(table)

    def add_group(self, group: Group) -> None:
        self.groups.append(group)

    def add_rule(self, rule: Any) -> None:
        if len(self.rules) >= MAX_RULES:
            raise ValueError(f"an event holds at most {MAX_RULES} rules")
        self.rules.append(rule)
