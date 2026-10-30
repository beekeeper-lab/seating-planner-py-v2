"""Ranked, costed alternatives for an event-day arrival with no valid seat.

The moment this module exists for is FR-067's refutation: a new guest has
arrived, and ``solve_hard`` in the event-day mode proved no table can take
them without breaking a hard rule. Refusing to seat them is correct — a hard
rule is a constraint, never a cost — but refusing without options is not
enough (FR-069): the guest is left unassigned, the baseline chart is handed
back unchanged, and the caller is shown alternatives ranked by disruption
count, then by violated-rule weight.

The alternatives are drawn from the FR-070 menu, probed in a fixed order:
adding one capacity-one table, raising one existing table's capacity by one
(per table, in the event's table order), unlocking one pinned baseline guest
(per baseline guest, in baseline order), and disabling one enabled hard
same-table or different-table rule (per rule, in the event's rule order —
the same filter hard.py's hard encoding applies). Each candidate is priced by
re-solving the actual event-day model on a copy of the event, never by
estimating: the disruption count is read off the candidate's own chart,
counting baseline guests only, and a candidate is offered only when its
re-solve is feasible. A probe that does not settle in its time limit
proves nothing — hard.py's probe discipline — so its candidate is simply
not offered, and a pathologically slow input can come back with an empty
menu rather than a hung call.

Every alternative states its cost: the disruption count, and for an
exception the id and weight of the rule it would disable (hard rules carry
no weight in the rules model, so ``None`` is the honest value today,
sorting as 0). The detail is one human sentence built from ids, numbers and
counts only — never a guest name or any personal text, because the payload
rides out to whatever persists it.

The whole call is read-only: every hypothetical rides on a copy of the
``Event``, the input event, its tables, rules and locked guests, and the
baseline mapping survive the call unchanged, and this module imports nothing
from the store layer. Alternatives are proposals; none is applied or
selected automatically — the organizer decides.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from seating_planner.domain import Event, Table
from seating_planner.rules import Hardness, Rule, RuleKind

from .hard import EVENT_DAY, SolverConfig, SolverTimeout, solve_hard
from .result import participants_of

#: The closed vocabulary the alternatives are drawn from, in report.py's
#: CORRECTIVE_KINDS style — the FR-070 menu.
ALTERNATIVE_KINDS: tuple[str, ...] = (
    "add_table",
    "change_capacity",
    "unlock",
    "exception",
)


@dataclass(frozen=True)
class Alternative:
    """One FR-070 option that a fresh event-day re-solve actually proved.

    ``kind`` is one of :data:`ALTERNATIVE_KINDS`; ``disruption_count``
    counts baseline guests whose table the candidate chart moves; the rule
    fields are set only by an :data:`exception` candidate, which is the
    one option that breaks a hard rule at all.
    """

    kind: str
    detail: str
    disruption_count: int
    violated_rule_id: str | None = None
    violated_rule_weight: int | None = None

    def sort_key(self) -> tuple[int, int, str, str]:
        """FR-069's rank: disruption count, then violated-rule weight
        (``None`` counting as 0), then kind and detail, so two alternatives
        never compare unequal on the same inputs."""
        return (
            self.disruption_count,
            0 if self.violated_rule_weight is None else self.violated_rule_weight,
            self.kind,
            self.detail,
        )


@dataclass(frozen=True)
class AdmissionResult:
    """The answer to "this guest has just arrived".

    ``seated`` carries the complete chart and no alternatives; ``unassigned``
    carries a private copy of the baseline — the new guest appears nowhere
    in it — plus the ranked alternatives.
    """

    status: str
    assignments: dict[str, str]
    alternatives: tuple[Alternative, ...] = ()


def _disruption(chart: Mapping[str, str], baseline: Mapping[str, str]) -> int:
    """Baseline guests whose table in ``chart`` differs from their
    baseline table. The new guest has no baseline and never counts."""
    return sum(
        1 for guest_id, table_id in baseline.items() if chart.get(guest_id) != table_id
    )


def _resettle(
    event: Event,
    cfg: SolverConfig,
    baseline: Mapping[str, str],
    *,
    unlocked_guest_ids: frozenset[str] | None = None,
) -> dict[str, str] | None:
    """One fresh event-day re-solve on a copy of the event, returning the
    candidate chart — or ``None``. A SolverTimeout is swallowed: a probe
    that does not settle proves nothing, so its candidate is not offered
    (the discipline hard.py states for its probe solves), and an infeasible
    re-solve offers nothing either."""
    try:
        result = solve_hard(
            event,
            cfg,
            mode=EVENT_DAY,
            current_assignments=baseline,
            unlocked_guest_ids=unlocked_guest_ids,
        )
    except SolverTimeout:
        return None
    if result.status != "feasible":
        return None
    return dict(result.assignments)


def _add_table_probe(
    event: Event, cfg: SolverConfig, baseline: Mapping[str, str]
) -> Alternative | None:
    """One extra Table of capacity 1 — the minimal honest addition, fixture-
    style name, shape and position, and an id built from the event's own id
    so it cannot collide with one of the event's tables."""
    extra = Table(
        id=f"{event.id}-alternative-table",
        name="Alternative table",
        capacity=1,
        shape="round",
        position=(0.0, 0.0),
    )
    copy = replace(event, tables=[*event.tables, extra])
    chart = _resettle(copy, cfg, baseline)
    if chart is None:
        return None
    moves = _disruption(chart, baseline)
    return Alternative(
        kind="add_table",
        detail=f"add table {extra.id} of capacity 1; {moves} seated guest(s) move",
        disruption_count=moves,
    )


def _change_capacity_probe(
    event: Event,
    cfg: SolverConfig,
    baseline: Mapping[str, str],
    table: Table,
) -> Alternative | None:
    """A copy of the event with this table's capacity raised by one."""
    copy = replace(
        event,
        tables=[
            replace(t, capacity=t.capacity + 1) if t.id == table.id else t
            for t in event.tables
        ],
    )
    chart = _resettle(copy, cfg, baseline)
    if chart is None:
        return None
    moves = _disruption(chart, baseline)
    return Alternative(
        kind="change_capacity",
        detail=(
            f"raise table {table.id}'s capacity from {table.capacity} to "
            f"{table.capacity + 1}; {moves} seated guest(s) move"
        ),
        disruption_count=moves,
    )


def _unlock_probe(
    event: Event,
    cfg: SolverConfig,
    baseline: Mapping[str, str],
    guest_id: str,
) -> Alternative | None:
    """The same event and baseline re-solved with this baseline guest named
    in unlocked_guest_ids. solve_hard's existing semantics keep an explicit
    lock explicit, so a pin that cannot help simply yields no feasible
    re-solve and needs no special-casing here."""
    chart = _resettle(event, cfg, baseline, unlocked_guest_ids=frozenset({guest_id}))
    if chart is None:
        return None
    moves = _disruption(chart, baseline)
    return Alternative(
        kind="unlock",
        detail=(
            f"unlock guest {guest_id} from their pinned table {baseline[guest_id]}; "
            f"{moves} seated guest(s) move"
        ),
        disruption_count=moves,
    )


def _exception_probe(
    event: Event,
    cfg: SolverConfig,
    baseline: Mapping[str, str],
    rule: Rule,
) -> Alternative | None:
    """A copy of the event with exactly this hard rule disabled, its id and
    weight carried on the alternative — hard rules carry no weight in the
    rules model, so None is the honest value, sorting as 0."""
    copy = replace(
        event,
        rules=[
            replace(r, enabled=False) if r.id == rule.id else r for r in event.rules
        ],
    )
    chart = _resettle(copy, cfg, baseline)
    if chart is None:
        return None
    moves = _disruption(chart, baseline)
    return Alternative(
        kind="exception",
        detail=(
            f"disable rule {rule.id} ({rule.kind.value}, {rule.hardness.value}); "
            f"{moves} seated guest(s) move"
        ),
        disruption_count=moves,
        violated_rule_id=rule.id,
        violated_rule_weight=rule.weight,
    )


def _generate_alternatives(
    event: Event, cfg: SolverConfig, baseline: Mapping[str, str]
) -> list[Alternative]:
    """Probe the FR-070 menu in its fixed order — one add_table, then each
    table's capacity, then each baseline guest's pin, then each candidate
    hard rule — and keep every candidate whose re-solve is feasible. The
    order is fixed so the ranking's tie-break is deterministic."""
    groups = {group.id: group for group in event.groups}
    eligible_ids = frozenset(guest.id for guest in event.guests if guest.eligible)
    generated: list[Alternative] = []
    offered = _add_table_probe(event, cfg, baseline)
    if offered is not None:
        generated.append(offered)
    for table in event.tables:
        offered = _change_capacity_probe(event, cfg, baseline, table)
        if offered is not None:
            generated.append(offered)
    for guest_id in baseline:
        offered = _unlock_probe(event, cfg, baseline, guest_id)
        if offered is not None:
            generated.append(offered)
    for rule in event.rules:
        if (
            not isinstance(rule, Rule)
            or not rule.enabled
            or rule.hardness is not Hardness.HARD
            or rule.kind not in (RuleKind.SAME_TABLE, RuleKind.DIFFERENT_TABLE)
        ):
            continue
        if len(participants_of(rule, groups, eligible_ids)) < 2:
            continue
        offered = _exception_probe(event, cfg, baseline, rule)
        if offered is not None:
            generated.append(offered)
    return generated


def admit_new_guest(
    event: Event,
    config: SolverConfig | None,
    *,
    current_assignments: Mapping[str, str],
    new_guest_id: str,
) -> AdmissionResult:
    """Admit one just-arrived guest to an event whose chart is running.

    The main solve is ``solve_hard`` in the event-day mode on the unchanged
    baseline: the new guest is absent from it, which is exactly how
    ``solve_hard`` reads a new arrival. If that solve is feasible the guest
    is seated and no alternatives are offered; if it is a proven refutation
    the alternatives are generated and the result is unassigned, carrying a
    private copy of the baseline with the alternatives sorted by their
    FR-069 key (a stable sort, so equal keys keep the fixed generation
    order). A SolverTimeout from the main solve propagates untouched. Raises
    ValueError naming the id when it is not an eligible guest of the event
    or is already seated in the baseline — a seated guest is not a new
    guest. The call is read-only: every hypothetical rides on a copy of the
    event, and neither the event nor the baseline survives it altered.
    """
    eligible = [guest.id for guest in event.guests if guest.eligible]
    if new_guest_id not in eligible:
        raise ValueError(
            f"new_guest_id {new_guest_id!r} is not an eligible guest of this event"
        )
    if new_guest_id in current_assignments:
        raise ValueError(
            f"new_guest_id {new_guest_id!r} is already seated in the baseline chart; "
            "a guest already seated is not a new guest"
        )
    baseline = dict(current_assignments)
    cfg = config or SolverConfig()
    result = solve_hard(event, cfg, mode=EVENT_DAY, current_assignments=baseline)
    if result.status == "feasible":
        return AdmissionResult("seated", dict(result.assignments))
    alternatives = sorted(
        _generate_alternatives(event, cfg, baseline), key=Alternative.sort_key
    )
    return AdmissionResult("unassigned", dict(baseline), tuple(alternatives))
