"""What a proven refutation means, and the first move that could unblock it.

CP-SAT can prove no assignment exists, but "no answer" is not an answer a
caller can act on (FR-050). This module turns a proven refutation plus the
subset of hard rules CP-SAT implicates in it into a small deterministic
report: the exact rule ids that cannot all hold, and at least one concrete
corrective action — and there is never an empty list of actions. The
recommendation walk is fixed: the capacity-shaped failures first, then each
conflicting rule in the event's rule order, then a fallback. The report is
rule ids and counts only — a guest's name or private text must never leak
into it, because it rides inside the result and out to whatever persists it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from seating_planner.domain import Event
from seating_planner.rules import Rule, RuleKind

from .result import participants_of

#: The closed vocabulary of corrective actions the report may recommend.
CORRECTIVE_KINDS: tuple[str, ...] = (
    "add_capacity",
    "add_table",
    "unlock",
    "change_hard_rule",
    "raise_movement_limit",
)


@dataclass(frozen=True)
class Recommendation:
    """One concrete move that could get the event out of the conflict.

    ``kind`` is one of :data:`CORRECTIVE_KINDS`; ``detail`` is a
    human-readable string built from rule ids and counts only, never from
    any guest-personal text.
    """

    kind: str
    detail: str


@dataclass(frozen=True)
class InfeasibilityReport:
    """The hard rules CP-SAT implies in a refutation, and the first fixes."""

    conflict_rule_ids: tuple[str, ...]
    recommendations: tuple[Recommendation, ...]


def build_infeasibility_report(
    event: Event,
    conflicting_rule_ids: Sequence[str],
    *,
    movement_limit: int | None = None,
) -> InfeasibilityReport:
    """Name the conflicting hard rules and recommend at least one fix.

    The logic is fixed and deterministic, in this order: (1) an event with
    no tables gets one add-a-table recommendation; (2) otherwise, when
    total table capacity is below the number of eligible guests, one
    add-capacity recommendation naming the seat and guest counts; (3) for
    each conflicting rule in the event's rule order, a
    change-the-hard-rule recommendation naming the rule id, its kind and
    its affected guests, and for a conflicting different_table rule a
    further add-a-table recommendation whenever the number of tables is
    below that rule's participant count — such a rule needs one distinct
    table per participant; when a low-disruption movement limit is
    provided, exactly one raise-the-movement-limit recommendation naming
    the numeric limit (and counts only, never guest names); (4) if
    nothing so far produced a recommendation, one add-a-table
    recommendation so the list is never empty. Existing callers pass no
    limit and keep today's behaviour exactly.
    """
    eligible_ids = frozenset(guest.id for guest in event.guests if guest.eligible)
    groups = {group.id: group for group in event.groups}
    total_capacity = sum(table.capacity for table in event.tables)
    table_count = len(event.tables)
    eligible_count = len(eligible_ids)

    recommendations: list[Recommendation] = []

    if table_count == 0:
        recommendations.append(
            Recommendation(
                kind="add_table",
                detail=(
                    f"the event has {eligible_count} eligible guests but no "
                    "tables at all; add a table"
                ),
            )
        )
    elif total_capacity < eligible_count:
        recommendations.append(
            Recommendation(
                kind="add_capacity",
                detail=(
                    f"the event's {table_count} tables provide "
                    f"{total_capacity} seats for {eligible_count} eligible "
                    "guests; add capacity"
                ),
            )
        )

    conflicts = set(conflicting_rule_ids)
    for rule in event.rules:
        if not isinstance(rule, Rule) or rule.id not in conflicts:
            continue
        participant_count = len(participants_of(rule, groups, eligible_ids))
        recommendations.append(
            Recommendation(
                kind="change_hard_rule",
                detail=(
                    f"hard {rule.kind.value} rule {rule.id} binds "
                    f"{participant_count} guests; relax or remove it"
                ),
            )
        )
        if rule.kind is RuleKind.DIFFERENT_TABLE and table_count < participant_count:
            recommendations.append(
                Recommendation(
                    kind="add_table",
                    detail=(
                        f"hard different_table rule {rule.id} needs one "
                        f"distinct table per participant "
                        f"({participant_count} participants, "
                        f"{table_count} tables); add a table"
                    ),
                )
            )

    if movement_limit is not None:
        # The limit's own cause, named with the numeric limit and counts
        # only — the limit is the cause only because the deletion
        # minimisation kept its literal, so no move count this low can
        # honour the rest, and capacity and rules are not to blame.
        recommendations.append(
            Recommendation(
                kind="raise_movement_limit",
                detail=(
                    f"keeping at most {movement_limit} of "
                    f"{eligible_count} eligible guests at their current "
                    "table leaves no valid chart; raise the movement limit"
                ),
            )
        )

    if not recommendations:
        recommendations.append(
            Recommendation(
                kind="add_table",
                detail=(
                    f"the event's {table_count} tables cannot hold the "
                    f"conflicting rules simultaneously; add a table"
                ),
            )
        )

    return InfeasibilityReport(
        conflict_rule_ids=tuple(conflicting_rule_ids),
        recommendations=tuple(recommendations),
    )
