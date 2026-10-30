"""The event repository: SQLite persistence plus an append-only audit log.

One ``EventRepository`` owns one ``sqlite3`` connection to one database file
(``:memory:`` works too). ``save`` is the heart of NFR-013: the event row,
every collection and every audit row are written in ONE transaction, so a
save that fails partway leaves the previously committed state — audit rows
included — readable and unchanged. ``audit_log`` is append-only by triggers
in the schema itself, which bind every process that opens the file, not just
this one (an attempted UPDATE or DELETE surfaces as ``sqlite3.IntegrityError``).
Collection rows carry a ``seq`` column because a SQL table is an unordered
set while the event's list order is part of what "equal" means after a
round trip.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..domain import Event, Group, Guest, RsvpStatus, Table
from ..rules import Rule

if TYPE_CHECKING:
    # Type-only: ``accept`` checks the solver-stamped status on the way in,
    # but the store adds no runtime dependency on the solver layer (which
    # imports nothing from the store), so there is no cycle.
    from ..solver.proposals import Proposal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS "event" (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS "guest" (
    id TEXT,
    event_id TEXT,
    name TEXT,
    rsvp_status TEXT,
    household TEXT,
    seat_reserved INTEGER,
    locked_to_table TEXT,
    seq INTEGER,
    PRIMARY KEY (event_id, id)
);
CREATE TABLE IF NOT EXISTS "tables" (
    id TEXT,
    event_id TEXT,
    name TEXT,
    capacity INTEGER,
    shape TEXT,
    x REAL,
    y REAL,
    seq INTEGER,
    PRIMARY KEY (event_id, id)
);
CREATE TABLE IF NOT EXISTS "groups" (
    id TEXT,
    event_id TEXT,
    name TEXT,
    seq INTEGER,
    PRIMARY KEY (event_id, id)
);
CREATE TABLE IF NOT EXISTS group_members (
    event_id TEXT,
    group_id TEXT,
    guest_id TEXT,
    seq INTEGER,
    PRIMARY KEY (event_id, group_id, seq)
);
CREATE TABLE IF NOT EXISTS rules (
    id TEXT,
    event_id TEXT,
    data TEXT NOT NULL,
    seq INTEGER,
    PRIMARY KEY (event_id, id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id TEXT,
    actor TEXT,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chart (
    event_id TEXT,
    guest_id TEXT,
    table_id TEXT,
    PRIMARY KEY (event_id, guest_id)
);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""


@dataclass(frozen=True)
class AuditEntry:
    """One row of the append-only audit log, read back as a value."""

    action: str
    entity_type: str
    entity_id: str
    actor: str
    timestamp: str


def _guest_signature(
    guest: Guest,
) -> tuple[str | None, str, str | None, bool, str | None]:
    return (
        guest.name,
        guest.rsvp_status.value,
        guest.household,
        guest.seat_reserved,
        guest.locked_to_table,
    )


def _stored_guest(
    row: sqlite3.Row,
) -> tuple[str | None, str, str | None, bool, str | None]:
    return (
        row["name"],
        row["rsvp_status"],
        row["household"],
        bool(row["seat_reserved"]),
        row["locked_to_table"],
    )


def _table_signature(table: Table) -> tuple[str, int, str, float, float]:
    return (
        table.name,
        table.capacity,
        table.shape,
        table.position[0],
        table.position[1],
    )


def _stored_table(row: sqlite3.Row) -> tuple[str, int, str, float, float]:
    return (
        row["name"],
        row["capacity"],
        row["shape"],
        float(row["x"]),
        float(row["y"]),
    )


class EventRepository:
    """Load and save :class:`~seating_planner.domain.Event` objects in SQLite."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def save_chart(
        self, event_id: str, assignments: Mapping[str, str], actor: str
    ) -> None:
        """Replace the event's stored chart, *assignments* mapped guest id to
        table id, and append one ``chart_saved`` audit row.

        A stored chart is historical organizer state, not a solver output: it
        is deliberately written without re-checking capacities or table
        existence, because a chart that overfills a shrunken table is exactly
        what must remain savable. Unknown event ids raise ``KeyError``, like
        ``load`` does. The delete, the inserts and the audit row commit
        together or roll back together (NFR-013).
        """
        row = self._conn.execute(
            'SELECT id FROM "event" WHERE id = ?', (event_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no stored event with id {event_id!r}")

        timestamp = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute("DELETE FROM chart WHERE event_id = ?", (event_id,))
            for guest_id, table_id in assignments.items():
                self._conn.execute(
                    "INSERT INTO chart (event_id, guest_id, table_id) VALUES (?, ?, ?)",
                    (event_id, guest_id, table_id),
                )
            self._conn.execute(
                "INSERT INTO audit_log "
                "(event_id, action, entity_type, entity_id, actor, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, "chart_saved", "chart", event_id, actor, timestamp),
            )

    def load_chart(self, event_id: str) -> dict[str, str]:
        """Return the event's stored chart as a guest id to table id mapping.

        Raises ``KeyError`` when no event with that id is stored; a stored
        event whose chart was never saved loads as an empty dict.
        """
        row = self._conn.execute(
            'SELECT id FROM "event" WHERE id = ?', (event_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no stored event with id {event_id!r}")
        return {
            r["guest_id"]: r["table_id"]
            for r in self._conn.execute(
                "SELECT guest_id, table_id FROM chart WHERE event_id = ?",
                (event_id,),
            )
        }

    def accept(self, proposal: Proposal, actor: str) -> None:
        """Apply a proposal's chart through ``save_chart``, naming *actor*.

        The check comes before any write at all: a proposal whose
        ``status`` is not ``"feasible"`` raises ``ValueError`` naming the
        event id and the status, touching nothing — no chart row, no audit
        row. ``status`` is data the solver stamped on the value, not
        something the store re-derives; a feasible proposal is never
        refused, however small its ``comparison``.
        """
        if proposal.status != "feasible":
            raise ValueError(
                f"refusing to accept the proposal for event "
                f"{proposal.event_id!r} with status {proposal.status!r}: "
                "nothing was written"
            )
        self.save_chart(proposal.event_id, proposal.assignments, actor)

    def save(self, event: Event, actor: str) -> None:
        """Persist *event* (replacing any stored version), in one transaction.

        The event row and every collection are rewritten in seq order, and one
        ``audit_log`` row is written per entity whose state changed against
        the previously stored state — ``created`` for an id not stored
        before, ``updated`` for a stored id whose data now differs,
        ``deleted`` for a stored id that is gone; unchanged entities get no
        entry. All rows of one save, audit rows included, commit together or
        roll back together (NFR-013).

        ``event.rules`` is ``list[Any]`` in the domain and allows opaque
        items, but only structured :class:`~seating_planner.rules.Rule`
        instances are persistable: any other item raises ``TypeError``
        before the database is touched.
        """
        for rule in event.rules:
            if not isinstance(rule, Rule):
                raise TypeError(
                    "only Rule instances are persistable; event.rules holds "
                    f"{type(rule).__name__} {rule!r}"
                )

        # Previously stored state, read outside the transaction.
        event_row = self._conn.execute(
            'SELECT * FROM "event" WHERE id = ?', (event.id,)
        ).fetchone()
        stored_guests = self._rows_by_id(
            'SELECT * FROM "guest" WHERE event_id = ?', event.id
        )
        stored_tables = self._rows_by_id(
            'SELECT * FROM "tables" WHERE event_id = ?', event.id
        )
        stored_groups = self._rows_by_id(
            'SELECT * FROM "groups" WHERE event_id = ?', event.id
        )
        stored_members = self._members_by_group(event.id)
        stored_rules = self._rows_by_id(
            "SELECT * FROM rules WHERE event_id = ?", event.id
        )

        timestamp = datetime.now(UTC).isoformat()
        entries = self._changed_entities(
            event,
            event_row,
            stored_guests,
            stored_tables,
            stored_groups,
            stored_members,
            stored_rules,
        )

        with self._conn:
            self._conn.execute(
                'INSERT INTO "event" (id, name) VALUES (?, ?) '
                "ON CONFLICT (id) DO UPDATE SET name = excluded.name",
                (event.id, event.name),
            )
            for collection in (
                '"guest"',
                '"tables"',
                '"groups"',
                "group_members",
                "rules",
            ):
                self._conn.execute(
                    f"DELETE FROM {collection} WHERE event_id = ?", (event.id,)
                )
            for seq, guest in enumerate(event.guests):
                self._conn.execute(
                    'INSERT INTO "guest" '
                    "(id, event_id, name, rsvp_status, household, seat_reserved, "
                    "locked_to_table, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        guest.id,
                        event.id,
                        guest.name,
                        guest.rsvp_status.value,
                        guest.household,
                        int(guest.seat_reserved),
                        guest.locked_to_table,
                        seq,
                    ),
                )
            for seq, table in enumerate(event.tables):
                self._conn.execute(
                    'INSERT INTO "tables" '
                    "(id, event_id, name, capacity, shape, x, y, seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        table.id,
                        event.id,
                        table.name,
                        table.capacity,
                        table.shape,
                        table.position[0],
                        table.position[1],
                        seq,
                    ),
                )
            for seq, group in enumerate(event.groups):
                self._conn.execute(
                    'INSERT INTO "groups" (id, event_id, name, seq) '
                    "VALUES (?, ?, ?, ?)",
                    (group.id, event.id, group.name, seq),
                )
                for member_seq, member_id in enumerate(group.member_ids):
                    self._conn.execute(
                        "INSERT INTO group_members "
                        "(event_id, group_id, guest_id, seq) "
                        "VALUES (?, ?, ?, ?)",
                        (event.id, group.id, member_id, member_seq),
                    )
            for seq, rule in enumerate(event.rules):
                self._conn.execute(
                    "INSERT INTO rules (id, event_id, data, seq) VALUES (?, ?, ?, ?)",
                    (rule.id, event.id, json.dumps(rule.to_dict()), seq),
                )
            for action, entity_type, entity_id in entries:
                self._conn.execute(
                    "INSERT INTO audit_log "
                    "(event_id, action, entity_type, entity_id, actor, ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (event.id, action, entity_type, entity_id, actor, timestamp),
                )

    def load(self, event_id: str) -> Event:
        """Rebuild the stored event, collections in seq order.

        Raises ``KeyError`` when no event with that id is stored. Rules are
        rebuilt through ``Rule.from_dict``, which re-validates every rule on
        every load by design.
        """
        row = self._conn.execute(
            'SELECT * FROM "event" WHERE id = ?', (event_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no stored event with id {event_id!r}")

        guests = [
            Guest(
                id=r["id"],
                name=r["name"],
                rsvp_status=RsvpStatus(r["rsvp_status"]),
                household=r["household"],
                seat_reserved=bool(r["seat_reserved"]),
                locked_to_table=r["locked_to_table"],
            )
            for r in self._conn.execute(
                'SELECT * FROM "guest" WHERE event_id = ? ORDER BY seq', (event_id,)
            )
        ]
        tables = [
            Table(
                id=r["id"],
                name=r["name"],
                capacity=r["capacity"],
                shape=r["shape"],
                position=(float(r["x"]), float(r["y"])),
            )
            for r in self._conn.execute(
                'SELECT * FROM "tables" WHERE event_id = ? ORDER BY seq', (event_id,)
            )
        ]
        groups = []
        for r in self._conn.execute(
            'SELECT * FROM "groups" WHERE event_id = ? ORDER BY seq', (event_id,)
        ):
            member_ids = [
                m["guest_id"]
                for m in self._conn.execute(
                    "SELECT guest_id FROM group_members "
                    "WHERE event_id = ? AND group_id = ? ORDER BY seq",
                    (event_id, r["id"]),
                )
            ]
            groups.append(Group(id=r["id"], name=r["name"], member_ids=member_ids))
        rules = [
            Rule.from_dict(json.loads(r["data"]))
            for r in self._conn.execute(
                "SELECT * FROM rules WHERE event_id = ? ORDER BY seq", (event_id,)
            )
        ]
        return Event(
            id=row["id"],
            name=row["name"],
            guests=guests,
            tables=tables,
            groups=groups,
            rules=rules,
        )

    def audit_entries(self, event_id: str | None = None) -> list[AuditEntry]:
        """Audit rows in seq order, restricted to one event's rows or all rows."""
        if event_id is None:
            rows = self._conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_log WHERE event_id = ? ORDER BY seq", (event_id,)
            ).fetchall()
        return [
            AuditEntry(
                action=r["action"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                actor=r["actor"],
                timestamp=r["ts"],
            )
            for r in rows
        ]

    def _rows_by_id(self, query: str, event_id: str) -> dict[str, sqlite3.Row]:
        return {row["id"]: row for row in self._conn.execute(query, (event_id,))}

    def _members_by_group(self, event_id: str) -> dict[str, tuple[str, ...]]:
        ordered = self._conn.execute(
            "SELECT group_id, guest_id FROM group_members "
            "WHERE event_id = ? ORDER BY group_id, seq",
            (event_id,),
        ).fetchall()
        members: dict[str, list[str]] = {}
        for row in ordered:
            members.setdefault(row["group_id"], []).append(row["guest_id"])
        return {group_id: tuple(ids) for group_id, ids in members.items()}

    @staticmethod
    def _changed_entities(
        event: Event,
        event_row: sqlite3.Row | None,
        stored_guests: dict[str, sqlite3.Row],
        stored_tables: dict[str, sqlite3.Row],
        stored_groups: dict[str, sqlite3.Row],
        stored_members: dict[str, tuple[str, ...]],
        stored_rules: dict[str, sqlite3.Row],
    ) -> list[tuple[str, str, str]]:
        """One (action, entity_type, entity_id) per entity whose state changed."""
        changes: list[tuple[str, str, str]] = []

        if event_row is None:
            changes.append(("created", "event", event.id))
        elif event_row["name"] != event.name:
            changes.append(("updated", "event", event.id))

        current_guests = {guest.id: guest for guest in event.guests}
        for guest in event.guests:
            stored = stored_guests.get(guest.id)
            if stored is None:
                changes.append(("created", "guest", guest.id))
            elif _stored_guest(stored) != _guest_signature(guest):
                changes.append(("updated", "guest", guest.id))
        for stored_id in stored_guests:
            if stored_id not in current_guests:
                changes.append(("deleted", "guest", stored_id))

        current_tables = {table.id: table for table in event.tables}
        for table in event.tables:
            stored = stored_tables.get(table.id)
            if stored is None:
                changes.append(("created", "table", table.id))
            elif _stored_table(stored) != _table_signature(table):
                changes.append(("updated", "table", table.id))
        for stored_id in stored_tables:
            if stored_id not in current_tables:
                changes.append(("deleted", "table", stored_id))

        current_groups = {group.id: group for group in event.groups}
        for group in event.groups:
            stored = stored_groups.get(group.id)
            if stored is None:
                changes.append(("created", "group", group.id))
            elif (
                stored["name"],
                stored_members.get(group.id, ()),
            ) != (group.name, tuple(group.member_ids)):
                changes.append(("updated", "group", group.id))
        for stored_id in stored_groups:
            if stored_id not in current_groups:
                changes.append(("deleted", "group", stored_id))

        current_rules = {rule.id: rule for rule in event.rules}
        for rule in event.rules:
            stored = stored_rules.get(rule.id)
            if stored is None:
                changes.append(("created", "rule", rule.id))
            elif Rule.from_dict(json.loads(stored["data"])) != rule:
                changes.append(("updated", "rule", rule.id))
        for stored_id in stored_rules:
            if stored_id not in current_rules:
                changes.append(("deleted", "rule", stored_id))

        return changes
