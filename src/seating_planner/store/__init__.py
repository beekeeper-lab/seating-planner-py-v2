"""SQLite-backed persistence for events, with an append-only audit log."""

from .repository import AuditEntry, EventRepository

__all__ = ["AuditEntry", "EventRepository"]
