"""Acceptance tests for reproducible optimization (bean-009, FR-048).

Repeated optimization over identical inputs and configuration must produce
the same assignment, and the result must carry the solver configuration
that actually made it — seed, time limit, worker count — so any stored
chart can be replayed from its own receipt. Each fixture is small enough
to work out by hand (optimum 11: g1+g2 together, g3 apart).
"""

from __future__ import annotations

import json
from typing import Any

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import SolverConfig, SolveResult, solve_hard

CONFIG = SolverConfig(time_limit_s=5.0, seed=7)


def guest(gid: str) -> Guest:
    return Guest(id=gid, name=f"Guest {gid}", rsvp_status=RsvpStatus.CONFIRMED)


def table(tid: str, cap: int) -> Table:
    return Table(tid, f"Table {tid}", cap, "round", (0.0, 0.0))


def rule(rid, kind, hardness, guests, w=None, **kw):
    return Rule(id=rid, kind=kind, hardness=hardness, guests=guests, weight=w, **kw)


def wedding(guests: list[Guest], tables: list[Table], rules: list[Rule]) -> Event:
    return Event(id="e1", name="Wedding", guests=guests, tables=tables, rules=rules)


def scenario() -> Event:
    """The shared hand-workable event: two seats per table, the pair at
    weight 10 sits together (capacity forces g3 aside) and g3 staying
    apart from g1 scores 1 for free — optimum 11, unique up to swap."""
    return wedding(
        [guest("g1"), guest("g2"), guest("g3")],
        [table("t1", 2), table("t2", 2)],
        [
            rule("r-together", RuleKind.SAME_TABLE, Hardness.SOFT, ("g1", "g2"), 10),
            rule("r-apart", RuleKind.DIFFERENT_TABLE, Hardness.SOFT, ("g1", "g3"), 1),
        ],
    )


def stored_config(result: SolveResult) -> dict[str, Any]:
    """The result's recorded configuration, read only through the JSON-safe
    surface with a default, so a result that records nothing reads empty
    instead of raising."""
    return json.loads(json.dumps(result.to_dict())).get("solver_config") or {}


def test_repeat_run_is_identical() -> None:
    """ac1: two solves of identically built events under one config give
    byte-identical charts — the comparison is on sorted-key JSON, so key
    order or object identity cannot mask a real difference."""
    first = solve_hard(scenario(), CONFIG, mode="planning")
    second = solve_hard(scenario(), CONFIG, mode="planning")
    assert first.status == "feasible" == second.status
    for result in (first, second):
        at = result.assignments
        assert at["g1"] == at["g2"], f"the weight-10 pairing was lost: {at}"
        assert at["g3"] != at["g1"], f"capacity forces g3 to the other table: {at}"
        assert result.soft_score == 11, (result.soft_score, at)
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    ), "same inputs and configuration must give a byte-identical result"


def test_result_records_configuration() -> None:
    """ac2: the result carries the seed, time limit and worker count
    actually used — the pinned single-worker default included — and the
    infeasible early return records it too, not only the happy path."""
    result = solve_hard(scenario(), CONFIG, mode="planning")
    assert result.status == "feasible"
    saved = stored_config(result)
    assert saved.get("seed") == 7, saved
    assert saved.get("time_limit_s") == 5.0, saved
    assert saved.get("num_workers") == 1, saved
    # A hard pairing against a hard separation on the same pair proves
    # infeasible on the early return; its receipt must say how it got there.
    dead = wedding(
        [guest("g1"), guest("g2")],
        [table("t1", 2), table("t2", 2)],
        [
            rule("r-hard-together", RuleKind.SAME_TABLE, Hardness.HARD, ("g1", "g2")),
            rule("r-hard-apart", RuleKind.DIFFERENT_TABLE, Hardness.HARD, ("g1", "g2")),
        ],
    )
    dead_result = solve_hard(dead, CONFIG, mode="planning")
    assert dead_result.status == "infeasible"
    dead_saved = stored_config(dead_result)
    assert dead_saved.get("seed") == 7, dead_saved
    assert dead_saved.get("time_limit_s") == 5.0, dead_saved
    assert dead_saved.get("num_workers") == 1, dead_saved


def test_stored_config_reproduces_result() -> None:
    """ac3: rebuilding the configuration from the values the result itself
    recorded reproduces the stored assignment, so a receipt is enough to
    replay its own chart."""
    event = scenario()
    result = solve_hard(event, CONFIG, mode="planning")
    assert result.status == "feasible"
    saved = stored_config(result)
    assert saved.get("seed", 0) == 7, saved
    assert saved.get("time_limit_s", 5.0) == 5.0, saved
    assert saved.get("num_workers", 1) == 1, saved
    # Replay with exactly what the result recorded; the worker count is
    # left to its default, which is the 1 this test asserted.
    replay = solve_hard(
        scenario(),
        SolverConfig(
            time_limit_s=saved.get("time_limit_s", 5.0),
            seed=saved.get("seed", 0),
        ),
        mode="planning",
    )
    assert replay.assignments == result.assignments, (
        replay.assignments,
        result.assignments,
    )


def test_seed_change_is_visible() -> None:
    """ac4: each result names the seed that made it, so a chart is always
    attributable to its run — the assignment may change with the seed, but
    a single worker may legitimately return the same chart for two, so
    divergence is never required, only reportability."""
    for seed in (0, 1):
        config = SolverConfig(time_limit_s=5.0, seed=seed)
        result = solve_hard(scenario(), config, mode="planning")
        assert result.status == "feasible"
        at = result.assignments
        assert at["g1"] == at["g2"], f"the weight-10 pairing was lost: {at}"
        assert at["g3"] != at["g1"], f"capacity forces g3 to the other table: {at}"
        assert result.soft_score == 11, (result.soft_score, at)
        saved = stored_config(result)
        assert saved.get("seed") == seed, (
            f"the result must report the seed {seed} that made it: {saved}"
        )
        # Replaying with this run's own stored seed reproduces this chart.
        replay = solve_hard(
            scenario(),
            SolverConfig(
                time_limit_s=saved.get("time_limit_s", 5.0),
                seed=saved.get("seed", 0),
            ),
            mode="planning",
        )
        assert replay.assignments == at, (replay.assignments, at)
