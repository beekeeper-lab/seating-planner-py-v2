"""Acceptance tests for EventRepository.save: refuses what a load could not
load (bean-030, ac4).

A save writes whatever it is handed while a load re-runs every constructor —
so a dangling lock or a broken soft weight lands as a row the event can no
longer open. ac4: a save refuses what the load could not load, names the
offending table or rule, and leaves the previously saved event exactly as it
was — the load returns the earlier state and the audit log gains no rows;
and a rule naming a group not yet in the event still saves, because a group
binding needs no guests — a template event lives before its groups exist.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import (
    Event,
    EventValidationError,
    Group,
    Guest,
    RsvpStatus,
    Table,
)
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.store import EventRepository


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id, name=f"Guest {guest_id}", rsvp_status=RsvpStatus.CONFIRMED
    )


def table(table_id: str) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=8,
        shape="round",
        position=(0, 0),
    )


def two_guest_event() -> Event:
    """Two guests, two tables, one group holding both, one soft rule r1
    over both guests with weight 10 — built validly through the
    constructor, so every mutation below is a plain field assignment on a
    live object."""
    return Event(
        id="e1",
        name="Wedding",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1"), table("t2")],
        groups=[Group(id="grp1", name="Family", member_ids=["g1", "g2"])],
        rules=[
            Rule(
                id="r1",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                guests=("g1", "g2"),
                weight=10,
            )
        ],
    )


def test_save_refuses_what_cannot_load(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"
    event = two_guest_event()

    repo = EventRepository(db_path)
    # 1: a first save of the valid event succeeds.
    repo.save(event, "alice")
    saved_audit = list(repo.audit_entries("e1"))
    first_save = repo.load("e1")

    # 2: a lock left dangling — g2 is pointed at a table id that is no
    # longer (and never was, after the removal) in event.tables.
    g2 = next(g for g in event.guests if g.id == "g2")
    g2.locked_to_table = "t-gone"
    with pytest.raises(EventValidationError) as lock_exc:
        repo.save(event, "bob")
    assert "t-gone" in str(lock_exc.value)

    # 3: a rule whose construction-era shape broke — the lock restored,
    # then r1's soft weight set past the 1..100 bound.
    g2.locked_to_table = None
    r1 = next(r for r in event.rules if r.id == "r1")
    r1.weight = 10**6
    with pytest.raises(EventValidationError) as weight_exc:
        repo.save(event, "bob")
    assert "r1" in str(weight_exc.value)

    # 4: the refused saves added no rows — the saved event is exactly as
    # it was: g2 unlocked, weight 10, both tables, no new audit entries.
    reloaded = repo.load("e1")
    assert reloaded == first_save
    reloaded_g2 = next(g for g in reloaded.guests if g.id == "g2")
    assert reloaded_g2.locked_to_table is None
    reloaded_r1 = next(r for r in reloaded.rules if r.id == "r1")
    assert reloaded_r1.weight == 10
    assert {t.id for t in reloaded.tables} == {"t1", "t2"}
    assert repo.audit_entries("e1") == saved_audit
    repo.close()

    # 5: a rule naming a group not yet in the event still saves: the
    # group binding needs no guests, the constructors never checked group
    # existence and the load never will.
    template_db = tmp_path / "template.sqlite3"
    template = Event(
        id="e2",
        name="Rehearsal",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1")],
        rules=[
            Rule(
                id="r-future",
                kind=RuleKind.SAME_TABLE,
                hardness=Hardness.SOFT,
                group_id="grp-future",
                weight=10,
            )
        ],
    )
    expected = next(r for r in template.rules if r.id == "r-future")
    fresh = EventRepository(template_db)
    fresh.save(template, "carol")
    round_trip = next(r for r in fresh.load("e2").rules if r.id == "r-future")
    assert round_trip.id == expected.id
    assert round_trip.kind == expected.kind
    assert round_trip.hardness == expected.hardness
    assert round_trip.group_id == expected.group_id == "grp-future"
    assert round_trip.to_dict() == expected.to_dict()
    fresh.close()
