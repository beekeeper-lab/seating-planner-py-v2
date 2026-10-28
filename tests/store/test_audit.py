"""Acceptance tests for the append-only audit log (ac2, ac4, ac5)."""

import sqlite3
from datetime import datetime

import pytest

from seating_planner.domain import Event, Group, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.store import AuditEntry, EventRepository


def _make_event() -> Event:
    """An event with two guests, one table, a group and one rule."""
    return Event(
        id="e1",
        name="Wedding",
        guests=[
            Guest(id="g1", name="Ann", rsvp_status=RsvpStatus.CONFIRMED),
            Guest(id="g2", name="Bob", rsvp_status=RsvpStatus.PENDING),
        ],
        tables=[
            Table(
                id="t1", name="Main round", capacity=8, shape="round", position=(2, 3)
            )
        ],
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


def _parseable(entry: AuditEntry) -> None:
    """Every one of an entry's four attributes is a non-empty string, and the
    timestamp parses with ``datetime.fromisoformat``."""
    for value in (entry.actor, entry.timestamp, entry.entity_type, entry.entity_id):
        assert isinstance(value, str) and value, (
            f"empty or non-string attribute: {value!r}"
        )
    datetime.fromisoformat(entry.timestamp)


def _entries_for(
    entries: list[AuditEntry],
    action: str,
    entity_type: str,
    entity_id: str,
) -> list[AuditEntry]:
    matches = [
        entry
        for entry in entries
        if entry.action == action
        and entry.entity_type == entity_type
        and entry.entity_id == entity_id
    ]
    assert len(matches) == 1, f"expected exactly one {action} entry for {entity_id}"
    return matches


def test_mutation_writes_audit_entry(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"
    event = _make_event()

    repo = EventRepository(db_path)
    repo.save(event, "alice")
    event.guests[0].name = "Ann (renamed)"
    event.tables = []
    repo.save(event, "bob")
    repo.close()

    # Fresh repository: the audit rows asserted on were committed, not merely
    # pending inside the previous connection's transaction.
    fresh = EventRepository(db_path)
    entries = fresh.audit_entries("e1")
    fresh.close()

    # Second save is attributed to "bob": the rename is an "updated" entry,
    # the dropped table is a "deleted" entry.
    updated = _entries_for(entries, "updated", "guest", "g1")
    assert updated[0].actor == "bob"
    _parseable(updated[0])
    deleted = _entries_for(entries, "deleted", "table", "t1")
    assert deleted[0].actor == "bob"
    _parseable(deleted[0])

    # First save wrote "created" entries: one per stored guest, table, group
    # and rule, plus the event itself — all under actor "alice".
    created = [entry for entry in entries if entry.action == "created"]
    expected_created = {
        ("event", "e1"),
        ("guest", "g1"),
        ("guest", "g2"),
        ("table", "t1"),
        ("group", "grp1"),
        ("rule", "r1"),
    }
    assert {
        (entry.entity_type, entry.entity_id) for entry in created
    } == expected_created
    for entry in created:
        assert entry.actor == "alice"
        _parseable(entry)


def test_audit_log_is_append_only(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"

    repo = EventRepository(db_path)
    repo.save(_make_event(), "alice")
    repo.close()

    snapshot_repo = EventRepository(db_path)
    snapshot: list[AuditEntry] = snapshot_repo.audit_entries("e1")
    snapshot_repo.close()
    assert len(snapshot) >= 1

    # Database level: the schema's BEFORE UPDATE / BEFORE DELETE triggers are
    # a fact about the file, so even raw SQL from another process is refused.
    raw = sqlite3.connect(str(db_path))
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("UPDATE audit_log SET actor = 'intruder' WHERE action = 'created'")
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("DELETE FROM audit_log")
    raw.close()

    # The committed log is exactly what it was before the attempts, in order.
    reopened = EventRepository(db_path)
    assert reopened.audit_entries("e1") == snapshot
    reopened.close()

    # API level: the public surface of EventRepository exposes no method that
    # would mutate or remove a logged entry — only the documented load/save/
    # audit/close methods exist.
    public_methods = {
        name
        for name in dir(EventRepository)
        if not name.startswith("_") and callable(getattr(EventRepository, name))
    }
    assert public_methods <= {"save", "load", "audit_entries", "close"}


def test_removal_writes_audit_entry(tmp_path) -> None:
    db_path = tmp_path / "wedding.sqlite3"
    event = _make_event()

    repo = EventRepository(db_path)
    repo.save(event, "alice")
    # The lists are plain Python lists; filter the four entities out.
    event.guests = [guest for guest in event.guests if guest.id != "g1"]
    event.tables = [table for table in event.tables if table.id != "t1"]
    event.groups = [group for group in event.groups if group.id != "grp1"]
    event.rules = [rule for rule in event.rules if getattr(rule, "id", None) != "r1"]
    repo.save(event, "carol")
    repo.close()

    fresh = EventRepository(db_path)
    entries = fresh.audit_entries("e1")
    fresh.close()

    # Removals are mutations with the same attribution rights as additions:
    # one "deleted" row per removed entity, named by the thing removed.
    removed = [
        entry
        for entry in entries
        if entry.action == "deleted" and entry.actor == "carol"
    ]
    assert {(entry.entity_type, entry.entity_id) for entry in removed} == {
        ("guest", "g1"),
        ("table", "t1"),
        ("group", "grp1"),
        ("rule", "r1"),
    }
    for entry in removed:
        _parseable(entry)
