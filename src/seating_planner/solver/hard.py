"""Hard-constraint table assignment on OR-Tools CP-SAT (FR-045, FR-047).

Hard rules stay constraints, never large weights (bean-007, FR-046): among
the charts that honour every hard rule, the solver returns the one with the
highest weighted total of satisfied soft rules. A soft rule is scored when
it can be read off a table-level chart — the soft same-table and
different-table rules — and gets a satisfaction indicator whose constraints
only ever force it towards false; the objective maximises weight times
indicator, so at the optimum each indicator is true exactly when the chart
satisfies its rule, and no weight can trade against a single hard
constraint.

The result is either a complete chart
or a proven refutation, never a partial chart (FR-050/FR-051): "infeasible"
means CP-SAT proved no assignment exists. A status that is neither a proven
answer nor a proven refutation (UNKNOWN: the time limit ran out before either
was settled) is not an answer about the problem at all, so it is never
reported as "infeasible" — that would tell a satisfiable problem's caller it
is impossible. It raises SolverTimeout instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ortools.sat.python import cp_model

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind

from .result import SolveResult, participants_of, summarize

#: Default bound on the solver's wall time, in seconds.
DEFAULT_TIME_LIMIT_S: float = 10.0


@dataclass(frozen=True)
class SolverConfig:
    """Explicit, per-call solver limits (no hidden defaults at solve time)."""

    time_limit_s: float = DEFAULT_TIME_LIMIT_S
    seed: int = 0


class SolverTimeout(RuntimeError):
    """The time limit ran out before CP-SAT proved feasible or infeasible.

    Never silently reported as "infeasible": that status means a proof was
    found that no assignment exists, and an exhausted time limit proves
    nothing either way.
    """


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


def _soft_same_table_score(
    model: cp_model.CpModel,
    seat: dict[str, dict[str, Any]],
    rule: Rule,
    participants: list[str],
    weight: int,
) -> Any:
    """weight * sat, where sat may only be true once all of the rule's
    participants sit together at some one table. One auxiliary z(t) records
    "satisfied by everyone sitting at table t"; sat can only be true when
    one of them is possible, and the maximisation sets it to 1 exactly
    then.
    """
    sat = model.new_bool_var(f"soft-same-{rule.id}")
    per_table: list[Any] = []
    for table_id in seat[participants[0]]:
        z_t = model.new_bool_var(f"soft-same-{rule.id}-{table_id}")
        for participant in participants:
            model.add(z_t <= seat[participant][table_id])
        per_table.append(z_t)
    model.add(sat <= sum(per_table, 0))
    return weight * sat


def _soft_different_table_score(
    model: cp_model.CpModel,
    seat: dict[str, dict[str, Any]],
    rule: Rule,
    participants: list[str],
    weight: int,
) -> Any:
    """weight * sat, where sat may only be true when every pair of
    participants sits at different tables. Each pair gets its own
    separation indicator y(a, b) that any shared table forces to false;
    the rule indicator is the conjunction of the pairs, again set by the
    objective and never by a constraint.
    """
    sat = model.new_bool_var(f"soft-diff-{rule.id}")
    for i in range(len(participants)):
        for j in range(i + 1, len(participants)):
            apart = model.new_bool_var(
                f"soft-diff-{rule.id}-{participants[i]}-{participants[j]}"
            )
            for table_id in seat[participants[0]]:
                model.add(
                    apart
                    + seat[participants[i]][table_id]
                    + seat[participants[j]][table_id]
                    <= 2
                )
            model.add(sat <= apart)
    return weight * sat


def solve_hard(event: Event, config: SolverConfig | None = None) -> SolveResult:
    """Assign every eligible guest to exactly one table, or report infeasible.

    Raises SolverTimeout when the solver reports a status that is neither a
    settled answer (OPTIMAL/FEASIBLE) nor a settled refutation (INFEASIBLE) —
    the time limit ran out before CP-SAT proved either way.
    """
    cfg = config or SolverConfig()
    eligible = [guest.id for guest in event.guests if guest.eligible]
    if not eligible:
        return summarize("feasible", {}, event)
    if not event.tables:
        return summarize("infeasible", {}, event)

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
        participants = participants_of(rule, groups, eligible_ids)
        if len(participants) < 2:
            continue
        if rule.kind is RuleKind.SAME_TABLE:
            _add_same_table(model, seat, participants)
        else:
            _add_different_table(model, seat, participants)

    # Soft rules (FR-046): score, don't constrain. The objective is a sum of
    # weight * indicator terms — with hard rules still hard constraints, a
    # weight-100 soft rule can never trade against, let alone violate, one.
    objective_terms: list[Any] = []
    for rule in event.rules:
        if (
            not isinstance(rule, Rule)
            or not rule.enabled
            or rule.hardness is not Hardness.SOFT
            or rule.kind not in (RuleKind.SAME_TABLE, RuleKind.DIFFERENT_TABLE)
        ):
            continue
        participants = participants_of(rule, groups, eligible_ids)
        if len(participants) < 2 or rule.weight is None:
            continue
        if rule.kind is RuleKind.SAME_TABLE:
            objective_terms.append(
                _soft_same_table_score(model, seat, rule, participants, rule.weight)
            )
        else:
            objective_terms.append(
                _soft_different_table_score(
                    model, seat, rule, participants, rule.weight
                )
            )
    if objective_terms:
        model.maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit_s
    solver.parameters.random_seed = cfg.seed
    # CP-SAT is reproducible per seed only single-worker; inv-reproducible
    # runs this solve twice with the same seed and demands identical charts.
    solver.parameters.num_workers = 1
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return summarize("infeasible", {}, event)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverTimeout(
            f"no table-level assignment settled within {cfg.time_limit_s}s: "
            f"solver reported {status!r}"
        )
    assignments = {
        guest: table_id
        for guest, per_table in seat.items()
        for table_id, var in per_table.items()
        if solver.boolean_value(var)
    }
    return summarize("feasible", assignments, event)
