"""Hard-constraint table assignment on OR-Tools CP-SAT (FR-045, FR-047).

Each eligible guest is assigned to exactly one table: one boolean variable
per (guest, table) pair, a per-guest sum of exactly one, per-table capacity
bounds, and — for each enabled hard same/different-table rule — pairwise
agreement or separation constraints. The result is either a complete chart
or nothing; a solver status that is not a proven answer is reported
infeasible with an empty assignment, never a partial chart (FR-050/FR-051).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from seating_planner.domain import Event, Group
from seating_planner.rules import Hardness, Rule, RuleKind

#: Default bound on the solver's wall time, in seconds.
DEFAULT_TIME_LIMIT_S: float = 10.0


@dataclass(frozen=True)
class SolverConfig:
    """Explicit, per-call solver limits (no hidden defaults at solve time)."""

    time_limit_s: float = DEFAULT_TIME_LIMIT_S
    seed: int = 0


@dataclass(frozen=True)
class SolveResult:
    """Either a complete chart or nothing — never a partial one."""

    status: str  # "feasible" | "infeasible"
    assignments: dict[str, str] = field(default_factory=dict)


def _participants(
    rule: Rule, groups: dict[str, Group], eligible_ids: frozenset[str]
) -> list[str]:
    """The rule's binders reduced to unique, eligible guest ids in order.

    A rule names either its guests or one group (never both); an absent
    group binds nobody. Ineligible or unknown ids drop out, so a rule about
    a guest who never sits adds no constraint.
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


def _add_same_table(
    model: cp_model.CpModel, seat: dict[str, dict[str, Any]], participants: list[str]
) -> None:
    """Pin every participant to the first participant's table, per table var."""
    first = participants[0]
    for table_id, anchor in seat[first].items():
        for other in participants[1:]:
            model.add(seat[other][table_id] == anchor)


def _add_different_table(
    model: cp_model.CpModel, seat: dict[str, dict[str, Any]], participants: list[str]
) -> None:
    """No two participants share a table: x_a + x_b <= 1 per pair per table."""
    for table_id in seat[participants[0]]:
        for i in range(len(participants)):
            for j in range(i + 1, len(participants)):
                model.add(
                    seat[participants[i]][table_id] + seat[participants[j]][table_id]
                    <= 1
                )


def solve_hard(event: Event, config: SolverConfig | None = None) -> SolveResult:
    """Assign every eligible guest to exactly one table, or report infeasible."""
    cfg = config or SolverConfig()
    eligible = [guest.id for guest in event.guests if guest.eligible]
    if not eligible:
        return SolveResult(status="feasible", assignments={})
    if not event.tables:
        return SolveResult(status="infeasible", assignments={})

    model = cp_model.CpModel()
    seat: dict[str, dict[str, Any]] = {
        guest: {
            table.id: model.new_bool_var(f"seat-{guest}-{table.id}")
            for table in event.tables
        }
        for guest in eligible
    }

    for guest in eligible:
        model.add(sum(seat[guest].values()) == 1)
    for table in event.tables:
        model.add(sum(seat[guest][table.id] for guest in eligible) <= table.capacity)

    groups = {group.id: group for group in event.groups}
    eligible_ids = frozenset(eligible)
    for rule in event.rules:
        if (
            not isinstance(rule, Rule)
            or not rule.enabled
            or rule.hardness is not Hardness.HARD
            or rule.kind not in (RuleKind.SAME_TABLE, RuleKind.DIFFERENT_TABLE)
        ):
            continue
        participants = _participants(rule, groups, eligible_ids)
        if len(participants) < 2:
            continue
        if rule.kind is RuleKind.SAME_TABLE:
            _add_same_table(model, seat, participants)
        else:
            _add_different_table(model, seat, participants)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit_s
    solver.parameters.random_seed = cfg.seed
    # CP-SAT is reproducible per seed only single-worker; inv-reproducible
    # runs this solve twice with the same seed and demands identical charts.
    solver.parameters.num_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(status="infeasible", assignments={})
    assignments = {
        guest: table_id
        for guest, per_table in seat.items()
        for table_id, var in per_table.items()
        if solver.boolean_value(var)
    }
    return SolveResult(status="feasible", assignments=assignments)
