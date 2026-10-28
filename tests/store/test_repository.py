"""Acceptance tests for EventRepository: round trip (ac1) and atomic saves (ac3)."""

import pytest

from seating_planner.domain import Event, Group, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.store import EventRepository


def _populated_event() -> Event:
    """A chart mixing RSVP statuses, int/float positions, a group and rule kinds."""
    return Event(
        id="e1",
        name="Wedding",
        guests=[
            Guest(
                id="g1",
                name="Ann",
                rsvp_status=RsvpStatus.PENDING,
                household="The Anns",
                seat_reserved=True,
            ),
            Guest(id="g2", name="Bob", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g3", name="Cid", rsvp_status=RsvpStatus.DECLINED),
        ],
        tables=[
            Table(
                id="t1", name="Main round", capacity=8, shape="round", position=(2, 3)
            ),
            Table(
                id="t2", name="Long", capacity=12, shape="rect", position=(4.5, 6.25)
            ),
        ],
        groups=[Group(id="grp1", name="Family", member_ids=["g1", "g2"])],
        rules=[
            Rule(
                id="r1",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=10,
            ),
            Rule(
                id="r2",
                kind=RuleKind.DIFFERENT_TABLE,
                hardness=Hardness.HARD,
                group_id="grp1",
            ),
            Rule(
                id="r3",
                kind=RuleKind.MIN_DISTANCE,
                hardness=Hardness.SOFT,
                guests=("g1", "g3"),
                weight=50,
                distance_m=5.0,
                min_zones=2,
            ),
        ],
    )


class _BoomRule(Rule):
    """A legal rule whose ``to_dict`` raises, so a save dies mid-transaction."""

    def __init__(self) -> None:
        super().__init__(
            id="r-boom",
            kind=RuleKind.SAME_TABLE,
            hardness=Hardness.HARD,
            guests=("g1", "g2"),
        )

    def to_dict(self) -> dict[str, object]:
        raise RuntimeError("boom rule cannot serialize")


def test_event_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"
    original = _populated_event()

    repo = EventRepository(db_path)
    repo.save(original, "alice")
    repo.close()

    reopened = EventRepository(db_path)
    loaded = reopened.load("e1")
    reloaded = reopened.load("e1")
    reopened.close()

    assert loaded == original
    assert reloaded == loaded


def test_failed_write_is_atomic(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"
    first = Event(
        id="e1",
        name="Wedding",
        guests=[Guest(id="g1", name="Ann", rsvp_status=RsvpStatus.CONFIRMED)],
        tables=[
            Table(
                id="t1", name="Main round", capacity=8, shape="round", position=(1, 1)
            )
        ],
    )

    repo = EventRepository(db_path)
    repo.save(first, "alice")
    repo.close()

    repo = EventRepository(db_path)
    working = repo.load("e1")
    working.guests[0].name = "Ann (renamed)"
    working.rules.append(_BoomRule())
    with pytest.raises(RuntimeError):
        repo.save(working, "bob")
    repo.close()

    fresh = EventRepository(db_path)
    reloaded = fresh.load("e1")
    assert reloaded == first
    assert all(entry.entity_id != "r-boom" for entry in fresh.audit_entries("e1"))
    fresh.close()
