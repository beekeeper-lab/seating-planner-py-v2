"""Hard-constraint table assignment entry point on OR-Tools CP-SAT
(FR-045, FR-047).

The production entry point validates the mode and its arguments, builds
the CP-SAT model (src/seating_planner/solver/model.py), runs the solver
(src/seating_planner/solver/solve.py), and interprets the settled status:
a proven refutation is named by deletion-minimising the assumption
literals and reported as an infeasibility report; an unsettled status
raises SolverTimeout.

Hard rules stay constraints, never large weights (bean-007, FR-046): among
the charts that honour every hard rule, the solver returns the one with the
highest weighted total of satisfied soft rules. A soft rule is scored when
it can be read off a table-level chart — the soft same-table and
different-table rules — and gets a satisfaction indicator whose constraints
only ever force it towards false; the objective maximises weight times
indicator, so at the optimum each indicator is true exactly when the chart
satisfies its rule, and no weight can trade against a single hard
constraint.

Three optimization modes are implemented. ``PLANNING`` returns the
highest-scoring chart among those that honour every hard rule, exactly as
above. ``LOW_DISRUPTION`` re-plans around a baseline chart under one added
hard limit: at most a given number of guests may change tables. Its
objective is the lexicographic order FR-066 requires — fewer table changes
always beat a higher soft score, and the score breaks ties among equally
small movements — expressed as a single big-``B`` linear objective, so a
score can never buy a disruption, and the limit can make the problem
infeasible in a way that only capacity-shape infeasibility cannot.
``EVENT_DAY`` serves the day the event is already running (FR-067):
the caller supplies the current chart, and every baseline guest is
pinned to their current table — encoded as an implicit lock on the same
locks list, so it rides an assumption literal and can be named in a
refutation — with one exception: a guest the caller names in
``unlocked_guest_ids`` is a free variable. The objective is the highest
soft score with everything existing still pinned (FR-066's modes never
re-plan opportunistically): a freed seat, for instance, stays empty
rather than inviting a neighbour in, and a cancellation moves no one
(FR-071).

The result is either a complete chart
or a proven refutation, never a partial chart (FR-050/FR-051): "infeasible"
means CP-SAT proved no assignment exists. A status that is neither a proven
answer nor a proven refutation (UNKNOWN: the time limit ran out before either
was settled) is not an answer about the problem at all, so it is never
reported as "infeasible" — that would tell a satisfiable problem's caller it
is impossible. It raises SolverTimeout instead.

Every encoded hard rule and every locked guest rides its own assumption
literal, so when the refutation is proven the solver can say which rules
and which locks it proved impossible: the conflict is found by
deletion-minimising the assumption set with cheap probe re-solves — a
probe that does not settle keeps its literal, so the named set is a minimal
conflicting subset, never an under-wide one, and the same configuration
always names the same subset. The report built from it is carried on the
result (src/seating_planner/solver/report.py); a kept lock names itself
there as an "unlock" recommendation alongside the conflicting rule ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from ortools.sat.python import cp_model

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind

from .model import build_model
from .report import Recommendation, build_infeasibility_report
from .result import SolveResult, summarize
from .solve import run

__all__ = [
    "DEFAULT_TIME_LIMIT_S",
    "EVENT_DAY",
    "LOW_DISRUPTION",
    "PLANNING",
    "SolverConfig",
    "SolverTimeout",
    "cp_model",
    "solve_hard",
]

#: Default bound on the solver's wall time, in seconds.
DEFAULT_TIME_LIMIT_S: float = 10.0

#: One of the three optimization modes implemented in this bean: plan from
#: scratch for the highest soft score among the non-conflicting charts.
PLANNING: str = "planning"

#: The re-planning mode: keep a baseline chart as intact as possible —
#: at most ``move_limit`` guests may change tables (hard), and the soft
#: score breaks ties among the least-disruptive charts (FR-066).
LOW_DISRUPTION: str = "low_disruption"

#: The day-of mode (FR-067, FR-071): the current chart is served, every
#: baseline guest pinned to their table unless the caller explicitly
#: unlocks them, and no one is moved to fill a freed seat.
EVENT_DAY: str = "event_day"


@dataclass(frozen=True)
class SolverConfig:
    """Explicit, per-call solver limits (no hidden defaults at solve time)."""

    time_limit_s: float = DEFAULT_TIME_LIMIT_S
    seed: int = 0
    # Parallel CP-SAT search is not deterministic — which worker finds the
    # optimum first decides among equally good answers — so the default
    # keeps today's pinned single-worker behaviour; a larger value is an
    # explicit, recorded trade against wall-clock time, not a constant.
    num_workers: int = 1


class SolverTimeout(RuntimeError):
    """The time limit ran out before CP-SAT proved feasible or infeasible.

    Never silently reported as "infeasible": that status means a proof was
    found that no assignment exists, and an exhausted time limit proves
    nothing either way.
    """


def solve_hard(
    event: Event,
    config: SolverConfig | None = None,
    *,
    mode: str,
    current_assignments: Mapping[str, str] | None = None,
    move_limit: int | None = None,
    unlocked_guest_ids: frozenset[str] | None = None,
) -> SolveResult:
    """Assign every eligible guest to exactly one table, or report infeasible.

    The optimization mode is explicit and required: it is a keyword-only
    argument with no default. The implemented modes are ``PLANNING``,
    ``LOW_DISRUPTION`` and ``EVENT_DAY``. ``LOW_DISRUPTION`` takes a
    baseline chart (``current_assignments``) and a hard cap (``move_limit``)
    on how many guests may change tables, and optimises fewer changes first,
    score second (FR-066). ``EVENT_DAY`` takes the same baseline chart and
    pins every baseline guest to their current table until the caller
    names an explicit exception in ``unlocked_guest_ids`` (FR-067); a
    freed seat stays empty rather than inviting a neighbour in (FR-071).

    Raises ValueError for an unsupported mode or for mode-inconsistent
    baseline arguments (planning with baseline inputs, a low-disruption
    solve missing its baseline or limit, a non-int or negative limit, an
    event-day solve missing its baseline or given a move_limit, an
    unlocked id that is not in the baseline, or a baseline naming an id
    the event does not have), and for a hard ``adjacent_seat`` rule, which
    cannot be evaluated because seat positions are not configured — a
    hard rule that cannot be evaluated is never treated as satisfied, so
    the solve is refused instead of running with the rule silently dropped
    — and SolverTimeout when the solver reports a
    status that is neither a settled answer (OPTIMAL/FEASIBLE) nor a
    settled refutation (INFEASIBLE) — the time limit ran out before CP-SAT
    proved either way.
    """
    cfg = config or SolverConfig()
    if mode not in (PLANNING, LOW_DISRUPTION, EVENT_DAY):
        raise ValueError(
            f"unsupported mode {mode!r}; the implemented modes are "
            f"{PLANNING!r}, {LOW_DISRUPTION!r} and {EVENT_DAY!r}"
        )
    low_disruption = mode == LOW_DISRUPTION
    event_day = mode == EVENT_DAY
    baseline: Mapping[str, str]
    limit: int
    if low_disruption:
        if current_assignments is None or move_limit is None:
            raise ValueError(
                f"{LOW_DISRUPTION!r} mode requires both current_assignments "
                "and move_limit"
            )
        # type() rather than isinstance: a bool is not a move limit.
        if type(move_limit) is not int or move_limit < 0:
            raise ValueError(f"move_limit must be an int >= 0, got {move_limit!r}")
        baseline = current_assignments
        limit = move_limit
    elif event_day:
        if current_assignments is None:
            raise ValueError(f"{EVENT_DAY!r} mode requires current_assignments")
        if move_limit is not None:
            raise ValueError(
                f"{EVENT_DAY!r} mode does not accept move_limit, got {move_limit!r}"
            )
        if unlocked_guest_ids is not None:
            for guest_id in unlocked_guest_ids:
                if guest_id not in current_assignments:
                    raise ValueError(
                        f"unlocked_guest_ids names {guest_id!r}, "
                        "which is not a guest of the baseline chart"
                    )
        baseline = current_assignments
        limit = 0
    else:
        if (
            current_assignments is not None
            or move_limit is not None
            or unlocked_guest_ids is not None
        ):
            raise ValueError(
                "current_assignments, move_limit and unlocked_guest_ids "
                f"are only accepted in {LOW_DISRUPTION!r} and {EVENT_DAY!r} modes"
            )
        baseline = {}
        limit = 0
    eligible = [guest.id for guest in event.guests if guest.eligible]
    if low_disruption or event_day:
        # The baseline must name ids the event has: an eligible guest for
        # every key, an event table for every value. A missing key is a new
        # arrival — no current table, no movement cost — and never an error.
        table_ids = frozenset(table.id for table in event.tables)
        for guest_id, table_id in baseline.items():
            if guest_id not in eligible:
                raise ValueError(
                    f"current_assignments names {guest_id!r}, "
                    "which is not an eligible guest of this event"
                )
            if table_id not in table_ids:
                raise ValueError(
                    f"current_assignments seats a guest at {table_id!r}, "
                    "which is not a table of this event"
                )
    for rule in event.rules:
        if (
            isinstance(rule, Rule)
            and rule.enabled
            and rule.hardness is Hardness.HARD
            and rule.kind is RuleKind.ADJACENT_SEAT
        ):
            raise ValueError(
                f"rule {rule.id!r} is a hard adjacent_seat rule, but seat "
                "positions are not configured, so it cannot be evaluated; a "
                "hard rule that cannot be evaluated is never treated as "
                "satisfied, so the solve is refused instead of running "
                "with the rule silently dropped"
            )
    if not eligible:
        return summarize("feasible", {}, event, cfg, mode=mode)
    if not event.tables:
        # No tables, no chart, no probe: the failure is named and the
        # recommendation built, and the save is never touched.
        return summarize(
            "infeasible",
            {},
            event,
            cfg,
            build_infeasibility_report(event, []),
            mode=mode,
        )

    unlocked = frozenset() if unlocked_guest_ids is None else unlocked_guest_ids
    built = build_model(
        event,
        low_disruption=low_disruption,
        event_day=event_day,
        baseline=baseline,
        limit=limit,
        unlocked=unlocked,
    )
    outcome = run(built, cfg)
    if outcome.status == "infeasible":
        kept = outcome.kept
        # The combined list is — low_disruption only — the movement-limit
        # literal first, then the rules, then the locks: split the kept
        # indices back into rule ids and (guest, table) lock pairs,
        # without any stringly-typed ids.
        limit_index = 1 if built.limit_assumption is not None else 0
        kept_rule_ids = [
            built.hard_rules[i - limit_index][0].id
            for i in kept
            if limit_index <= i < limit_index + len(built.hard_rules)
        ]
        kept_locks = [
            (
                built.locks[i - limit_index - len(built.hard_rules)][0],
                built.locks[i - limit_index - len(built.hard_rules)][1],
            )
            for i in kept
            if i >= limit_index + len(built.hard_rules)
        ]
        # The limit is named as a cause only when the minimisation kept its
        # literal: a rule conflict, or a conflict of pure capacity shape,
        # in this mode is still reported as one.
        limit_kept = built.limit_assumption is not None and 0 in kept
        report = build_infeasibility_report(
            event, kept_rule_ids, movement_limit=limit if limit_kept else None
        )
        if kept_locks:
            # One unlock recommendation per guest the refutation named,
            # first kept literal's table: a contradicted guest rides two
            # kept literals and is named once.
            seen: set[str] = set()
            unlocks: list[Recommendation] = []
            for guest_id, lock_table in kept_locks:
                if guest_id in seen:
                    continue
                seen.add(guest_id)
                unlocks.append(
                    Recommendation(
                        kind="unlock",
                        detail=f"guest {guest_id} is locked to table {lock_table}; unlock them",
                    )
                )
            if event_day and not kept_rule_ids:
                # Locks alone ride the conflict. A seat shortage refutes
                # with every literal off and keeps nothing, so no capacity
                # remedy is legitimate in this branch, and the report
                # builder's only remaining offer — its generic add-a-table
                # fallback — is a remedy that cannot work while the locks
                # hold.
                report = replace(report, recommendations=tuple(unlocks))
            else:
                report = replace(
                    report,
                    recommendations=tuple(unlocks) + report.recommendations,
                )
        return summarize("infeasible", {}, event, cfg, report, mode=mode)
    if outcome.status == "unsettled":
        raise SolverTimeout(
            f"no table-level assignment settled within {cfg.time_limit_s}s: "
            f"solver reported {outcome.raw_status!r}"
        )
    return summarize("feasible", outcome.assignments, event, cfg, mode=mode)
