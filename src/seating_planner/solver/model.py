"""CP-SAT model construction for table-level assignment (bean-019).

The whole model — the per-guest seat variables and per-guest/per-table
constraints, the lock assumption literals, the event-day implicit pins,
the low-disruption moved variables and movement-limit cap, the hard rule
encodings, the soft rule objective terms, the objective, and the combined
assumption-literal list — is built here, in the exact statement order the
old inline construction used, so that the pinned single-worker seeded run
reproduces its answer. The module creates variables and never names
CpSolver; running the model someone else's job (solver/solve.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind

from .result import participants_of


@dataclass
class BuiltModel:
    """The built CP-SAT model plus the bookkeeping the run and the report
    need: the seat variables, the encoded hard rules with their assumption
    literals, the locks (explicit and, in event_day, implicit pins), the
    moved-record variables and the movement-limit literal, and the combined
    assumption-literal list (limit first in low_disruption, then the rules
    in the event's rule order, then the locks in insertion order)."""

    model: cp_model.CpModel
    seat: dict[str, dict[str, Any]]
    hard_rules: list[tuple[Rule, Any]] = field(default_factory=list)
    locks: list[tuple[str, str, Any]] = field(default_factory=list)
    moved_vars: dict[str, Any] = field(default_factory=dict)
    limit_assumption: Any = None
    assumption_literals: list[Any] = field(default_factory=list)


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


def build_model(
    event: Event,
    *,
    low_disruption: bool,
    event_day: bool,
    baseline: Mapping[str, str],
    limit: int,
    unlocked: frozenset[str],
) -> BuiltModel:
    """Build every variable and constraint of the assignment model.

    The mode flags are the ones the caller already validates: in
    ``low_disruption`` the baseline chart and the movement limit are
    always given; in ``event_day`` every baseline guest not in
    ``unlocked`` is implicitly pinned; otherwise both are vacuous. The
    model is returned un-solved and carrying no assumptions of any one
    solve.
    """
    eligible = [guest.id for guest in event.guests if guest.eligible]

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
    # them in unlocked, and each pin is an entry of the same
    # locks list — so it rides its own assumption literal, can be named
    # in a proven refutation, and surfaces as an "unlock" recommendation
    # if it ever proves load-bearing. A guest already explicitly locked
    # carries one lock, not two; a freed seat (a guest absent from the
    # re-read event) simply has no pin (FR-071), and the planning
    # objective below is the one that maximises the soft score with
    # everything existing held — no opportunistic re-plan of a pinned chart.
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

    # The combined assumption-literal list: low_disruption only, the
    # movement-limit literal first of all, then the hard rules in the
    # event's rule order, then the locks in insertion order. The list is
    # returned, not set: setting assumptions on the model is the run's
    # job, and the model is never left holding assumptions of any one solve.
    assumption_literals: list[Any] = []
    if limit_assumption is not None:
        assumption_literals.append(limit_assumption)
    assumption_literals.extend(assumption for _, assumption in hard_rules)
    assumption_literals.extend(assumption for _, _, assumption in locks)

    return BuiltModel(
        model=model,
        seat=seat,
        hard_rules=hard_rules,
        locks=locks,
        moved_vars=moved_vars,
        limit_assumption=limit_assumption,
        assumption_literals=assumption_literals,
    )
