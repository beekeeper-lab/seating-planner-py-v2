"""The inspectable result of an optimization (FR-049; Principle 2).

Who sat down, who did not, why the soft score is what it is, and for
every active rule whether the chart satisfies it, breaks it, or gives it
nothing to read — all questions the result must answer from the chart
itself. Principle 6 gives it one hard rule: a rule the chart cannot
decide is `unevaluable` — a third state alongside `satisfied` and
`violated`, never reported as `satisfied`. A table-level chart cannot
read min_distance or adjacent_seat (no seats, no geometry), and cannot
decide a rule whose participants are not all seated — every rule on an
infeasible event, which has no chart at all.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from seating_planner.domain import Event, Group
from seating_planner.rules import Hardness, Rule, RuleKind

if TYPE_CHECKING:
    # Avoids the import cycle: hard.py imports this module at runtime.
    from .hard import SolverConfig

    # Avoids the import cycle: report.py imports participants_of at runtime.
    from .report import InfeasibilityReport

# Three states; what a chart cannot decide is `unevaluable`, never `satisfied`.
SATISFIED = "satisfied"
VIOLATED = "violated"
UNEVALUABLE = "unevaluable"

#: Rule kinds a table-level chart can hold a verdict on; the rest need seats.
_TABLE_LEVEL_KINDS: frozenset[RuleKind] = frozenset(
    {RuleKind.SAME_TABLE, RuleKind.DIFFERENT_TABLE}
)


@dataclass(frozen=True)
class RuleAssessment:
    """One active rule's state in one chart, with the guests it concerns.

    ``affected_guest_ids`` are the participants reduced to unique eligible
    guest ids (the solver's same reduction), in the order the rule named
    them.
    """

    rule_id: str
    kind: str  # RuleKind value, so an unreadable rule keeps its kind visible
    hardness: str  # Hardness value; soft rules are the only ones scored
    status: str  # "satisfied" | "violated" | "unevaluable"
    weight: int | None  # present exactly when hardness is soft
    affected_guest_ids: tuple[str, ...]


@dataclass(frozen=True)
class SolveResult:
    """A complete chart or a proven refutation — never a partial one — plus
    the report that makes the chart explainable (FR-049).

    Every report field is computed from the chart, and the payload is ids
    and numbers only — no field may carry private guest notes.

    ``infeasibility_report`` is present only when the status is
    "infeasible" — it is why no chart exists, and what could be changed —
    and absent everywhere else, exactly like its default ``None``.
    """

    status: str  # "feasible" | "infeasible"
    mode: str  # the optimization mode the result was produced under
    solver_config: SolverConfig  # the configuration that actually made this result
    assignments: dict[str, str] = dataclasses.field(default_factory=dict)
    assigned_count: int = 0
    unassigned_count: int = 0
    soft_score: int = 0
    rule_states: tuple[RuleAssessment, ...] = ()
    infeasibility_report: InfeasibilityReport | None = None

    @property
    def violations(self) -> tuple[RuleAssessment, ...]:
        """The rule states the chart breaks, one entry per rule."""
        return tuple(a for a in self.rule_states if a.status == VIOLATED)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe mapping of the whole result, ids and numbers only."""
        return dataclasses.asdict(self)


def participants_of(
    rule: Rule, groups: dict[str, Group], eligible_ids: frozenset[str]
) -> list[str]:
    """The rule's binders, reduced to unique, eligible guest ids in order:
    its named guests, or its group's members, with ineligible and unknown
    ids dropped.
    """
    raw: list[str] | tuple[str, ...] = rule.guests
    if rule.group_id is not None:
        group = groups.get(rule.group_id)
        raw = group.member_ids if group is not None else []
    seen: set[str] = set()
    participants: list[str] = []
    for guest_id in raw:
        if guest_id in eligible_ids and guest_id not in seen:
            seen.add(guest_id)
            participants.append(guest_id)
    return participants


def assess_rules(
    event: Event, assignments: Mapping[str, str]
) -> tuple[RuleAssessment, ...]:
    """Every active rule's state in one chart, in the event's rule order.

    "Active" means an enabled ``Rule``; disabled rules and non-Rule items
    are in no state at all. A verdict needs the kind readable at table
    level and every participant seated; anything less is `unevaluable`.
    """
    groups = {group.id: group for group in event.groups}
    eligible_ids = frozenset(guest.id for guest in event.guests if guest.eligible)
    assessments: list[RuleAssessment] = []
    for rule in event.rules:
        if not isinstance(rule, Rule) or not rule.enabled:
            continue
        participants = participants_of(rule, groups, eligible_ids)
        seated = [
            t for t in (assignments.get(p) for p in participants) if t is not None
        ]
        if (
            rule.kind in _TABLE_LEVEL_KINDS
            and len(participants) >= 2
            and len(seated) == len(participants)
        ):
            distinct = len(set(seated))
            if rule.kind is RuleKind.SAME_TABLE:
                satisfied = distinct == 1
            else:
                satisfied = distinct == len(participants)
            status = SATISFIED if satisfied else VIOLATED
        else:
            status = UNEVALUABLE
        assessments.append(
            RuleAssessment(
                rule_id=rule.id,
                kind=rule.kind.value,
                hardness=rule.hardness.value,
                status=status,
                weight=rule.weight,
                affected_guest_ids=tuple(participants),
            )
        )
    return tuple(assessments)


def summarize(
    status: str,
    assignments: Mapping[str, str],
    event: Event,
    config: SolverConfig,
    infeasibility_report: InfeasibilityReport | None = None,
    *,
    mode: str,
) -> SolveResult:
    """A chart's assignments plus its whole report, every field computed
    from the chart itself, so there is no second source to drift from.

    The configuration and the optimization mode are stamped on too, so a
    replay of this result — feasible or a proven refutation — rebuilds the
    solver exactly as it ran when the result was made, in the mode that
    produced it. A refutation may additionally carry its infeasibility
    report; an optional argument, so the report's callers keep working
    unchanged.
    """
    rule_states = assess_rules(event, assignments)
    eligible = [guest.id for guest in event.guests if guest.eligible]
    unassigned = sum(1 for guest_id in eligible if guest_id not in assignments)
    soft_score = 0
    for assessment in rule_states:
        if (
            assessment.hardness == Hardness.SOFT.value
            and assessment.status == SATISFIED
        ):
            soft_score += assessment.weight or 0
    return SolveResult(
        status=status,
        mode=mode,
        solver_config=config,
        assignments=dict(assignments),
        assigned_count=len(assignments),
        unassigned_count=unassigned,
        soft_score=soft_score,
        rule_states=rule_states,
        infeasibility_report=infeasibility_report,
    )
