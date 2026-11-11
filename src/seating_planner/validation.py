"""Use-time validation: the event as it stands, not as it was built.

The domain objects are mutable dataclasses, and their checks run once, at
construction — nothing re-checked the event between that moment and the solve
or save it is handed to. The walkers here re-run those checks on the event as
it stands, in one pass each, and refuse with ``EventValidationError`` (a
``ValueError`` subclass, so a caller catching the old type still catches
these), keeping the constructors' existing wording and naming the offending
guest, table, rule, group or limit wherever the wording does not already.

Level one — ``validate_event_for_save`` — is exactly the consequence of
construction: the event's limits, unique guest/table/rule ids, every guest's
fields, every table's capacity and position, every rule's own shape (through
the very ``Rule.from_dict``/``to_dict`` round trip a load performs), and
locks naming tables the event has. Whatever a save accepts, a load can
load; a rule naming a group not yet in the event is not a level-one breach,
because a group binding needs no guests.

Level two — ``validate_event_for_solve`` — adds what only a solve reads:
every group member a guest of the event, every enabled rule's named guests
and group present, and an enabled hard rule whose kind the solver will not
express (the hard ``adjacent_seat`` refusal, with its message). Disabled
rules are not walked beyond level one, and nothing here knows of an event's
eligibility.
"""

from __future__ import annotations

from seating_planner.domain import (
    MAX_GUESTS,
    MAX_RULES,
    MAX_TABLES,
    Event,
    EventValidationError,
    RsvpStatus,
    Table,
)
from seating_planner.rules import Hardness, Rule, RuleKind


def validate_event_for_save(event: Event) -> None:
    """Re-run, on the event as it stands, every check its constructors enforce.

    Refuses on the first breach, in construction order: the event's limits,
    duplicate guest/table/rule identifiers, every guest's fields, every
    table's capacity and position (rebuilding through ``Table(...)``), every
    rule's own shape on the round trip ``Rule.from_dict(rule.to_dict())``,
    and every lock naming a table the event has. Raises
    :class:`~seating_planner.domain.EventValidationError`, never a plain
    ``ValueError`` or anything else. A non-``Rule`` item in ``event.rules``
    is skipped: the store's own ``TypeError`` stands as it does today.
    Eligibility, group members and a rule's named guests or group are not
    level one — a template event must still save before its groups exist.
    """
    if len(event.guests) > MAX_GUESTS:
        raise EventValidationError(f"an event holds at most {MAX_GUESTS} guests")
    if len(event.tables) > MAX_TABLES:
        raise EventValidationError(f"an event holds at most {MAX_TABLES} tables")
    if len(event.rules) > MAX_RULES:
        raise EventValidationError(f"an event holds at most {MAX_RULES} rules")

    seen_guest_ids: set[str] = set()
    for guest in event.guests:
        if guest.id in seen_guest_ids:
            raise EventValidationError(f"duplicate guest identifier {guest.id!r}")
        seen_guest_ids.add(guest.id)

    seen_table_ids: set[str] = set()
    for table in event.tables:
        if table.id in seen_table_ids:
            raise EventValidationError(f"duplicate table identifier {table.id!r}")
        seen_table_ids.add(table.id)

    seen_rule_ids: set[str] = set()
    for rule in event.rules:
        if not isinstance(rule, Rule):
            continue
        if rule.id in seen_rule_ids:
            raise EventValidationError(
                f"duplicate rule identifier {rule.id!r}; the event's rules "
                "must have unique ids"
            )
        seen_rule_ids.add(rule.id)

    for guest in event.guests:
        if not isinstance(guest.rsvp_status, RsvpStatus):
            raise EventValidationError(
                f"guest {guest.id!r} has rsvp_status {guest.rsvp_status!r}, "
                "which is not a RsvpStatus member"
            )
        if type(guest.seat_reserved) is not bool:
            raise EventValidationError(
                f"guest {guest.id!r}: seat_reserved must be a bool, "
                f"got {guest.seat_reserved!r}"
            )

    for table in event.tables:
        try:
            Table(
                id=table.id,
                name=table.name,
                capacity=table.capacity,
                shape=table.shape,
                position=table.position,
            )
        except ValueError as exc:
            raise EventValidationError(f"table {table.id!r}: {exc}") from exc

    for rule in event.rules:
        if not isinstance(rule, Rule):
            continue
        try:
            Rule.from_dict(rule.to_dict())
        except (ValueError, TypeError, AttributeError) as exc:
            raise EventValidationError(f"rule {rule.id!r}: {exc}") from exc

    for guest in event.guests:
        if (
            guest.locked_to_table is not None
            and guest.locked_to_table not in seen_table_ids
        ):
            raise EventValidationError(
                f"guest {guest.id!r} is locked to table "
                f"{guest.locked_to_table!r}, which is not in the event"
            )


def validate_event_for_solve(event: Event) -> None:
    """Level one plus what only a solve reads, refusing on the first breach.

    Level one (limits, duplicate ids, entity fields, dangling locks) holds
    for a solve too, and runs before the checks here — so an event with a
    duplicate rule id and an unknown-guest rule is still refused by the
    duplicate, with the constructor's message. Then: every member of every
    event group is a guest id of the event; every enabled rule's named
    guests are guest ids of the event and its ``group_id``, when present,
    names an event group; and an enabled hard ``adjacent_seat`` rule is
    refused, because seat positions are not configured — a hard rule that
    cannot be evaluated is never treated as satisfied. Disabled rules are
    not walked beyond level one.
    """
    validate_event_for_save(event)

    guest_ids = frozenset(guest.id for guest in event.guests)
    for group in event.groups:
        for member_id in group.member_ids:
            if member_id not in guest_ids:
                raise EventValidationError(
                    f"group {group.id!r} names member {member_id!r}, "
                    "which is not a guest of the event"
                )

    group_ids = frozenset(group.id for group in event.groups)
    for rule in event.rules:
        if not isinstance(rule, Rule) or not rule.enabled:
            continue
        for guest_id in rule.guests:
            if guest_id not in guest_ids:
                raise EventValidationError(
                    f"rule {rule.id!r} names guest {guest_id!r}, "
                    "which is not a guest of the event"
                )
        if rule.group_id is not None and rule.group_id not in group_ids:
            raise EventValidationError(
                f"rule {rule.id!r} names group {rule.group_id!r}, "
                "which is not a group of the event"
            )

    for rule in event.rules:
        if (
            isinstance(rule, Rule)
            and rule.enabled
            and rule.hardness is Hardness.HARD
            and rule.kind is RuleKind.ADJACENT_SEAT
        ):
            raise EventValidationError(
                f"rule {rule.id!r} is a hard adjacent_seat rule, but seat "
                "positions are not configured, so it cannot be evaluated; a "
                "hard rule that cannot be evaluated is never treated as "
                "satisfied, so the solve is refused instead of running "
                "with the rule silently dropped"
            )
