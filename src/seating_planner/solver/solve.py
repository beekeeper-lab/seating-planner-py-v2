"""Solve execution and conflict probing for the built CP-SAT model
(bean-019).

The production solve, and the deletion-minimising probes that find the
minimal conflicting assumption-literal set, live here. The module names
CpSolver and creates no variables — building the model is the job of
solver/model.py, and interpreting a settled status is the entry
point's. Unsettled statuses are reported up as RunOutcome, not raised:
only the entry point raises SolverTimeout.

This CP-SAT build carries the assumption set on the model: the main
solve sets its literals with model.add_assumptions (the solver's own
assumption API is not used) and clears them again afterwards, and a
solve with neither stays a plain solve. The pinned timeout test stubs
the solve method and expects exactly this call path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ortools.sat.python import cp_model

from .model import BuiltModel

if TYPE_CHECKING:
    # Runtime import would be a cycle: hard imports this module.
    from .hard import SolverConfig


@dataclass
class RunOutcome:
    """The outcome of one solve run.

    ``status`` is "feasible" (read back to ``assignments``: guest id to
    table id), "infeasible" (``kept`` holds the indices of the minimal
    conflicting assumption literals, in the combined list's order), or
    "unsettled" (nothing proven either way; the entry point, not this
    module, raises the timeout). ``raw_status`` carries CP-SAT's own
    status for the message and for replay."""

    status: str
    assignments: dict[str, str] = field(default_factory=dict)
    kept: list[int] = field(default_factory=list)
    raw_status: Any = None


def _probe_infeasible(
    model: cp_model.CpModel,
    assumption_literals: list[Any],
    cfg: SolverConfig,
) -> bool:
    """Re-solve the same model under the given literals, once, and report
    whether the probe proved infeasible. A fresh single-seed CpSolver with
    the main solve's configuration — same seed, same worker count, time
    limit no larger than the configured one — so a probe settles the same
    way the main solve did under identical configuration; a probe that does
    not settle in time reports not-proved-infeasible, and the caller keeps
    its literal rather than guessing.

    This CP-SAT build carries the assumption set on the model, so the
    probe sets its literals, solves, and clears them again — the model is
    never left holding assumptions of any one solve.
    """
    model.clear_assumptions()
    if assumption_literals:
        model.add_assumptions(assumption_literals)
    probe = cp_model.CpSolver()
    probe.parameters.max_time_in_seconds = cfg.time_limit_s
    probe.parameters.random_seed = cfg.seed
    probe.parameters.num_workers = cfg.num_workers
    status = probe.solve(model)
    model.clear_assumptions()
    return status == cp_model.INFEASIBLE


def _minimal_conflict(
    model: cp_model.CpModel,
    assumptions: list[Any],
    cfg: SolverConfig,
) -> list[int]:
    """The indices of the minimal conflicting assumption literals, by
    deletion minimisation.

    ``assumptions`` is the combined encoded assumption literals in the
    event's rule order first, then the event's guest order for locks, all
    of which the main solve proved infeasible together. If the refutation
    already holds with every assumption false, the failure is structural
    — capacity or shape, nothing named in it — and the conflict is empty.
    Otherwise literals are dropped one at a time, in that order: a literal
    is discarded only when the subset without it still proves infeasible,
    so each kept literal is load-bearing and the named set is minimal (and,
    by the same probe discipline, deterministic). The caller splits the
    kept indices back into rule ids and locked guests.
    """
    if not assumptions:
        return []
    if _probe_infeasible(model, [~a for a in assumptions], cfg):
        return []
    kept: list[int] = list(range(len(assumptions)))
    for index in range(len(assumptions)):
        if index not in kept:
            continue  # already shown not to be load-bearing
        without = [j for j in kept if j != index]
        if _probe_infeasible(model, [assumptions[j] for j in without], cfg):
            kept = without
    return kept


def run(built: BuiltModel, cfg: SolverConfig) -> RunOutcome:
    """Run one production solve of the built model and report the outcome.

    The assumption set — the movement-limit literal first in
    low_disruption, then the encoded hard rules, then the locks — is set
    on the model when non-empty (this CP-SAT build carries assumptions on
    the model, not on the solver), cleared before and after the solve, so
    the model is never left holding assumptions of any one solve. On
    INFEASIBLE the minimal conflicting subset is found by probe re-solves
    and reported as ``kept``; a status that is neither OPTIMAL nor
    FEASIBLE is reported as "unsettled" — the entry point, not this
    module, raises the timeout —; otherwise the settled chart is read
    back with ``solver.boolean_value`` over the builder's seat variables.
    """
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit_s
    solver.parameters.random_seed = cfg.seed
    # CP-SAT is reproducible per seed only single-worker; inv-reproducible
    # runs this solve twice with the same seed and demands identical charts.
    # The pinned default comes from the configuration, and the same
    # configuration is stamped onto the result so the run can be replayed.
    solver.parameters.num_workers = cfg.num_workers
    # This CP-SAT build carries the assumption set on the model: the main
    # solve asks for every rule assumption and every lock true (and, in
    # low_disruption, the movement limit first of all), and a solve with
    # neither stays a plain solve.
    model = built.model
    model.clear_assumptions()
    if built.assumption_literals:
        model.add_assumptions(built.assumption_literals)
    status = solver.solve(model)
    model.clear_assumptions()
    if status == cp_model.INFEASIBLE:
        kept = _minimal_conflict(model, built.assumption_literals, cfg)
        return RunOutcome("infeasible", kept=kept, raw_status=status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return RunOutcome("unsettled", raw_status=status)
    assignments = {
        guest: table_id
        for guest, per_table in built.seat.items()
        for table_id, var in per_table.items()
        if solver.boolean_value(var)
    }
    return RunOutcome("feasible", assignments=assignments)
