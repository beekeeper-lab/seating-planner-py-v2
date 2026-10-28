"""Acceptance test: production limits on guests, tables and rules (ac5)."""

import pytest

from seating_planner.domain import (
    MAX_GUESTS,
    MAX_RULES,
    MAX_TABLES,
    Event,
    Guest,
    RsvpStatus,
    Table,
)


def make_event() -> Event:
    return Event(id="e1", name="Wedding")


def fill_to_limit(event: Event, count: int, kind: str) -> None:
    for i in range(count):
        if kind == "guest":
            event.add_guest(
                Guest(id=f"g{i}", name="G", rsvp_status=RsvpStatus.CONFIRMED)
            )
        elif kind == "table":
            event.add_table(
                Table(
                    id=f"t{i}",
                    name=f"t{i}",
                    capacity=8,
                    shape="round",
                    position=(0.0, 0.0),
                )
            )
        else:
            event.add_rule(object())


def next_item(event: Event, kind: str) -> None:
    if kind == "guest":
        event.add_guest(Guest(id="g-final", name="G", rsvp_status=RsvpStatus.CONFIRMED))
    elif kind == "table":
        event.add_table(
            Table(
                id="t-final",
                name="t-final",
                capacity=8,
                shape="round",
                position=(0.0, 0.0),
            )
        )
    else:
        event.add_rule(object())


def test_production_limits() -> None:
    """The 500th guest, 60th table and 5000th rule are accepted; the next
    guest, table and rule each raise ValueError."""
    for count, kind in (
        (MAX_GUESTS, "guest"),
        (MAX_TABLES, "table"),
        (MAX_RULES, "rule"),
    ):
        event = make_event()
        fill_to_limit(event, count, kind)
        assert len(getattr(event, kind + "s")) == count
        with pytest.raises(ValueError):
            next_item(event, kind)
