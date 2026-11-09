"""Regression pins for soft keep-apart scoring (bean-021, v2 pin 2026-11-09).

On this tree a soft different-table rule's satisfaction indicator is bounded
from above by the chart: every table its participants share forces the pair's
separation indicator to 0, and the rule's indicator may only be 1 when every
pair sits apart (src/seating_planner/solver/model.py,
``_soft_different_table_score``) — so the objective rewards a chart exactly
when the keep-apart holds. The original build had it the other way around
(bounded from below, free when the guests were apart), and a maximizer set
such an indicator true either way, so keep-apart rules never influenced which
chart was returned. These two tests pin the encoding against that regression
and both pass against the existing source unchanged; they change nothing in
src/.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Mapping

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)

#: Fixed seed for the scenario generator: the events are a fixture, so the
#: pin must be reproducible run to run, exactly like a hand-written fixture.
SEED = 20261109
#: How many generated events to check, and how many to draw before failing:
#: with the rejection filter below an acceptance rate near zero means the
#: scenario has degenerated, which is a defect in this test, not the solver.
TARGET_EVENTS = 30
MAX_ATTEMPTS = 20_000


def guest(guest_id: str) -> Guest:
    return Guest(
        id=guest_id,
        name=f"Guest {guest_id}",
        rsvp_status=RsvpStatus.CONFIRMED,
    )


def table(table_id: str, capacity: int) -> Table:
    return Table(
        id=table_id,
        name=f"Table {table_id}",
        capacity=capacity,
        shape="round",
        position=(0.0, 0.0),
    )


def rule(
    rule_id: str,
    kind: RuleKind,
    hardness: Hardness,
    guests: tuple[str, ...],
    weight: int | None = None,
) -> Rule:
    return Rule(id=rule_id, kind=kind, hardness=hardness, guests=guests, weight=weight)


def chart_soft_score(chart: Mapping[str, str], rules: tuple[Rule, ...]) -> int:
    """A chart's soft score recomputed from the chart itself, with the
    result report's own semantics: a soft same-table rule counts when every
    participant shares one table, a soft different-table rule counts only
    when every pair sits at a different table, nothing else counts."""
    total = 0
    for one in rules:
        if one.hardness is not Hardness.SOFT or one.weight is None:
            continue
        participants = one.guests
        if len(participants) < 2:
            continue
        tables = [chart.get(participant) for participant in participants]
        if any(t is None for t in tables):
            continue
        if one.kind is RuleKind.SAME_TABLE:
            satisfied = len(set(tables)) == 1
        else:
            satisfied = len(set(tables)) == len(tables)
        if satisfied:
            total += one.weight
    return total


def valid_charts(
    guests: list[Guest], tables: list[Table], hard_rules: list[Rule]
) -> list[dict[str, str]]:
    """Every chart that seats each guest at exactly one table within capacity
    and honours every hard rule — the complete valid-chart set, since the
    events are small enough to enumerate them all."""
    table_ids = [one.id for one in tables]
    capacities = {one.id: one.capacity for one in tables}
    charts: list[dict[str, str]] = []
    for combo in itertools.product(table_ids, repeat=len(guests)):
        chart = {g.id: c for g, c in zip(guests, combo)}
        counts: dict[str, int] = {}
        for table_id in chart.values():
            counts[table_id] = counts.get(table_id, 0) + 1
        if any(count > capacities[table_id] for table_id, count in counts.items()):
            continue
        valid = True
        for one in hard_rules:
            tables_in = [chart[participant] for participant in one.guests]
            if one.kind is RuleKind.SAME_TABLE:
                if len(set(tables_in)) != 1:
                    valid = False
                    break
            else:
                if len(set(tables_in)) != len(tables_in):
                    valid = False
                    break
        if valid:
            charts.append(chart)
    return charts


def next_event(rng: random.Random) -> tuple[Event, list[dict[str, str]]] | None:
    """One random small event (2–4 guests, 2–3 tables of capacity 1–3, 2–4
    same/different rules, hard or soft, weights 1–100) plus its complete
    valid-chart set. ``None`` when the draw is unusable: total capacity below
    the guest count, fewer than two valid charts at all, or fewer than two
    distinct soft scores among the valid charts — that last filter is what
    keeps the optimality comparison below non-vacuous on every single
    event, so a wrong scenario fails this test instead of hiding behind a
    tie."""
    n_guests = rng.randint(2, 4)
    capacities = [rng.randint(1, 3) for _ in range(rng.randint(2, 3))]
    if sum(capacities) < n_guests:
        return None
    guests = [guest(f"g{i}") for i in range(n_guests)]
    tables = [table(f"t{i}", c) for i, c in enumerate(capacities)]
    guest_ids = [g.id for g in guests]
    rules: list[Rule] = []
    for k in range(rng.randint(2, 4)):
        size = min(rng.choice([2, 2, 3]), n_guests)
        participants = tuple(rng.sample(guest_ids, size))
        kind = rng.choice([RuleKind.SAME_TABLE, RuleKind.DIFFERENT_TABLE])
        hardness = rng.choice([Hardness.HARD, Hardness.SOFT])
        weight = rng.randint(1, 100) if hardness is Hardness.SOFT else None
        rules.append(
            Rule(
                id=f"r{k}",
                kind=kind,
                hardness=hardness,
                guests=participants,
                weight=weight,
            )
        )
    event = Event(
        id="e",
        name="Generated",
        guests=guests,
        tables=tables,
        rules=rules,
    )
    hard_rules = [r for r in rules if r.hardness is Hardness.HARD]
    charts = valid_charts(guests, tables, hard_rules)
    scores = {chart_soft_score(chart, tuple(rules)) for chart in charts}
    if len(charts) < 2 or len(scores) < 2:
        return None
    return event, charts


def test_heavier_keep_apart_wins() -> None:
    """ac1: a weight-100 soft different-table rule and a weight-1 soft
    same-table rule name the same two guests, and both candidate charts are
    valid (two tables of two seats each). The keep-apart must win: if the
    different-table indicator ever scores as satisfied whatever the chart
    does, a weight-1 sit-together wins the objective and the pair is seated
    together."""
    event = Event(
        id="e1",
        name="Keeping apart",
        guests=[guest("g1"), guest("g2")],
        tables=[table("t1", 2), table("t2", 2)],
        rules=[
            rule(
                "r-apart",
                RuleKind.DIFFERENT_TABLE,
                Hardness.SOFT,
                ("g1", "g2"),
                weight=100,
            ),
            rule("r-same", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), weight=1),
        ],
    )
    result = solve_hard(event, CONFIG, mode="planning")
    assignments = result.assignments
    assert result.status == "feasible", result.status
    assert len(assignments) == 2
    assert assignments["g1"] != assignments["g2"], (
        f"the weight-100 keep-apart lost to the weight-1 sit-together: {assignments}"
    )
    assert result.soft_score == 100, (
        f"the apart chart scores the keep-apart's weight and nothing of the "
        f"sit-together's (chart score is recomputed from the chart by the "
        f"report): {result.soft_score}"
    )


def test_returned_chart_is_optimal() -> None:
    """ac2: on small random events, no valid chart has a higher reported soft
    score than the chart the solver returns — checked against the complete
    enumeration of valid charts (capacity plus hard rules), not a sample.
    The events are generated with a fixed seed and filtered to ones whose
    valid charts actually span at least two soft scores, so on every event
    the comparison can discriminate a solver that does not really maximise
    the soft score."""
    rng = random.Random(SEED)
    events: list[tuple[Event, list[dict[str, str]]]] = []
    for _ in range(MAX_ATTEMPTS):
        if len(events) == TARGET_EVENTS:
            break
        candidate = next_event(rng)
        if candidate is not None:
            events.append(candidate)
    assert len(events) == TARGET_EVENTS, (
        "the scenario generator drew fewer than 30 usable events; the "
        "generation parameters, not the solver, are at fault"
    )
    for index, (event, charts) in enumerate(events):
        result = solve_hard(event, CONFIG, mode="planning")
        assert result.status == "feasible", (
            f"event {index} has valid charts but the solver returned {result.status}"
        )
        best = max(chart_soft_score(chart, tuple(event.rules)) for chart in charts)
        assert result.soft_score == chart_soft_score(
            result.assignments, tuple(event.rules)
        ), f"event {index}: reported score does not match the returned chart"
        assert best <= result.soft_score, (
            f"event {index}: an enumerated valid chart scores {best}, the "
            f"solver's chart scores {result.soft_score}"
        )
