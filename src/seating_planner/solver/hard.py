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
from typing import Any

from ortools.sat.python import cp_model

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind

from .report import Recommendation, build_infeasibility_report
from .result import SolveResult, participants_of, summarize

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


def _add_same_table(
    model: cp_model.CpModel,
    seat: dict[str, dict[str, Any]],
    participants: list[str],
    assumption: Any,
) -> None:
    """Pin every participant to the first participant's table, per table
    var — only while the rule's assumption literal is true, so the rule's
    constraints can be switched off by the probe solves."""
    first = participants[0]
    for table_id, anchor in seat[first].items():
        for other in participants[1:]:
            model.add(seat[other][table_id] == anchor).only_enforce_if(assumption)


def _add_different_table(
    model: cp_model.CpModel,
    seat: dict[str, dict[str, Any]],
    participants: list[str],
    assumption: Any,
) -> None:
    """No two participants share a table: x_a + x_b <= 1 per pair per
    table — only while the rule's assumption literal is true."""
    for table_id in seat[participants[0]]:
        for i in range(len(participants)):
            for j in range(i + 1, len(participants)):
                model.add(
                    seat[participants[i]][table_id] + seat[participants[j]][table_id]
                    <= 1
                ).only_enforce_if(assumption)


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
    the event does not have), and SolverTimeout when the solver reports a
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

    # Locks (FR-058): the organizer's decision, carried as a fixed variable
    # in the model, never as a post-solve correction of the returned chart.
    # The domain guarantees the locked table exists in the event, so the
    # locked guest's seat variable at that table exists. Each lock rides
    # its own assumption literal, exactly as a hard rule does: the main
    # solve carries it true, and only a probe solve of the refutation may
    # switch it off, so a proven clash can name the lock it found.
    locks: list[tuple[str, str, Any]] = []
    for candidate in event.guests:
        if candidate.eligible and candidate.locked_to_table is not None:
            lock_table = candidate.locked_to_table
            assumption = model.new_bool_var(f"lock-{candidate.id}")
            model.add(seat[candidate.id][lock_table] == 1).only_enforce_if(assumption)
            locks.append((candidate.id, lock_table, assumption))

    # Implicit pins (FR-067), event_day only: every baseline guest is
    # treated as locked to their current table unless the caller named
    # them in unlocked_guest_ids, and each pin is an entry of the same
    # locks list — so it rides its own assumption literal, can be named
    # in a proven refutation, and surfaces as an "unlock" recommendation
    # if it ever proves load-bearing. A guest already explicitly locked
    # carries one lock, not two; a freed seat (a guest absent from the
    # re-read event) simply has no pin (FR-071), and the planning
    # objective below is the one that maximises the soft score with
    # everything existing held — no opportunistic re-plan of a pinned chart.
    unlocked = frozenset() if unlocked_guest_ids is None else unlocked_guest_ids
    if event_day:
        pinned = {guest_id for guest_id, _, _ in locks}
        for guest_id, lock in baseline.items():
            if guest_id in unlocked or guest_id in pinned:
                continue
            assumption = model.new_bool_var(f"lock-{guest_id}")
            model.add(seat[guest_id][lock] == 1).only_enforce_if(assumption)
            locks.append((guest_id, lock, assumption))

    # Movement (FR-066), low_disruption only: one moved flag per eligible
    # guest records whether the chart puts them anywhere but their current
    # table, and one hard constraint — riding its own assumption literal,
    # a third kind alongside the rules' and the locks' — caps how many
    # guests may move, so a proven refutation that keeps the literal can
    # name the limit as its cause.
    moved_vars: dict[str, Any] = {}
    limit_assumption: Any = None
    if low_disruption:
        for guest in eligible:
            moved = model.new_bool_var(f"moved-{guest}")
            moved_vars[guest] = moved
            current_table = baseline.get(guest)
            if current_table is not None:
                # Every table other than the guest's current one implies
                # moved, so the variable is forced true exactly when the
                # guest is anywhere but their current table; the objective
                # pushes it down, which is what keeps it a faithful record.
                # A guest the baseline does not know (a new arrival) gets
                # no such constraints — they are not moving from anywhere.
                for other in seat[guest]:
                    if other != current_table:
                        model.add(seat[guest][other] <= moved)
        limit_assumption = model.new_bool_var("move-limit")
        model.add(sum(moved_vars.values(), 0) <= limit).only_enforce_if(
            limit_assumption
        )

    groups = {group.id: group for group in event.groups}
    eligible_ids = frozenset(eligible)
    hard_rules: list[tuple[Rule, Any]] = []
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
        # The rule's constraints are conditional on its own assumption
        # literal: the main solve carries it true, and on a refutation the
        # probe solves switch literals off to find the conflict.
        assumption = model.new_bool_var(f"hard-rule-{rule.id}")
        if rule.kind is RuleKind.SAME_TABLE:
            _add_same_table(model, seat, participants, assumption)
        else:
            _add_different_table(model, seat, participants, assumption)
        hard_rules.append((rule, assumption))

    # Soft rules (FR-046): score, don't constrain. The objective is a sum of
    # weight * indicator terms — with hard rules still hard constraints, a
    # weight-100 soft rule can never trade against, let alone violate, one.
    objective_terms: list[Any] = []
    # The sum of the weights of exactly the rules that build score terms;
    # low_disruption's objective is built from this same filtered set.
    scored_weight_sum = 0
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
        scored_weight_sum += rule.weight
    if low_disruption:
        # Big-B objective: one extra table change costs B, where
        # B = 1 + the total weight of the scored soft rules. Every chart's
        # soft score is in 0..B-1, so one extra move costs more than the
        # most score any chart could earn — a score can never buy a
        # disruption — and among charts that move equally many guests the
        # higher score wins. That is the lexicographic order FR-066
        # requires, not a weighted sum; with no scored rules B is 1 and
        # the objective reduces to minimising the number of moves.
        big_b = 1 + scored_weight_sum
        objective = big_b * sum(moved_vars.values(), 0)
        if objective_terms:
            objective = objective - sum(objective_terms)
        model.minimize(objective)
    elif objective_terms:
        model.maximize(sum(objective_terms))

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
    assumption_literals: list[Any] = []
    if limit_assumption is not None:
        assumption_literals.append(limit_assumption)
    assumption_literals.extend(assumption for _, assumption in hard_rules)
    assumption_literals.extend(assumption for _, _, assumption in locks)
    if assumption_literals:
        model.add_assumptions(assumption_literals)
    status = solver.solve(model)
    model.clear_assumptions()
    if status == cp_model.INFEASIBLE:
        kept = _minimal_conflict(model, assumption_literals, cfg)
        # The combined list is — low_disruption only — the movement-limit
        # literal first, then the rules, then the locks: split the kept
        # indices back into rule ids and (guest, table) lock pairs,
        # without any stringly-typed ids.
        limit_index = 1 if limit_assumption is not None else 0
        kept_rule_ids = [
            hard_rules[i - limit_index][0].id
            for i in kept
            if limit_index <= i < limit_index + len(hard_rules)
        ]
        kept_locks = [
            (
                locks[i - limit_index - len(hard_rules)][0],
                locks[i - limit_index - len(hard_rules)][1],
            )
            for i in kept
            if i >= limit_index + len(hard_rules)
        ]
        # The limit is named as a cause only when the minimisation kept its
        # literal: a rule conflict, or a conflict of pure capacity shape,
        # in this mode is still reported as one.
        limit_kept = limit_assumption is not None and 0 in kept
        report = build_infeasibility_report(
            event, kept_rule_ids, movement_limit=limit if limit_kept else None
        )
        if kept_locks:
            # Each lock the minimisation kept appends one unlock
            # recommendation, in the combined list's order.
            report = replace(
                report,
                recommendations=tuple(
                    Recommendation(
                        kind="unlock",
                        detail=f"guest {guest_id} is locked to table {lock_table}; unlock them",
                    )
                    for guest_id, lock_table in kept_locks
                )
                + report.recommendations,
            )
        return summarize("infeasible", {}, event, cfg, report, mode=mode)
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
    return summarize("feasible", assignments, event, cfg, mode=mode)
