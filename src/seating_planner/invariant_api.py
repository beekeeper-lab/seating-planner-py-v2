"""The conformance seam declared by factory/invariants/seating.yaml.

`seating.yaml` pins exactly one public surface an independently authored check
may see: module ``seating_planner.invariant_api``, callable ``solve_from_spec``.
That is this whole module — one mapping from the spec's plain dictionaries to
the domain, one hard-constraint solve, and the pinned result shape back. It is
not a test helper: it ships with the package, and the invariant suite verifies
behaviour against it, not against tests this line wrote.
"""

from __future__ import annotations

from typing import Any

from seating_planner.domain import Event, Guest, RsvpStatus, Table
from seating_planner.rules import Hardness, Rule, RuleKind
from seating_planner.solver import DEFAULT_TIME_LIMIT_S, SolverConfig, solve_hard
from seating_planner.solver.hard import PLANNING

_DEFAULT_SEED: int = 0


def _guest(d: dict[str, Any]) -> Guest:
    # The domain has no "ineligible" status; declined is simply not eligible,
    # so the seam's boolean becomes a domain fact the same way the domain
    # derives eligibility.
    status = RsvpStatus.CONFIRMED if d.get("eligible") else RsvpStatus.DECLINED
    return Guest(id=d["id"], name=d["id"], rsvp_status=status)


def _table(d: dict[str, Any]) -> Table:
    # A table-level solve reads nothing from shape or position.
    return Table(
        id=d["id"],
        name=d.get("name", d["id"]),
        capacity=d["capacity"],
        shape="round",
        position=(0.0, 0.0),
    )


def _rule(index: int, d: dict[str, Any]) -> Rule:
    hardness = Hardness(d["hardness"])
    # The seam's spec shape carries no weight field at all, while the rule
    # model requires a 1..100 weight on soft rules. The hard-constraint
    # solver encodes no soft rule (that is bean-007), so the minimum weight
    # is a documented placeholder, not a preference.
    weight = None if hardness is Hardness.HARD else 1
    return Rule(
        id=f"spec-rule-{index}",
        kind=RuleKind(d["kind"]),
        hardness=hardness,
        guests=tuple(d["guests"]),
        weight=weight,
    )


def solve_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Solve the spec's hard-constraint seating and return the pinned shape."""
    config = spec.get("config") or {}
    event = Event(
        id="spec-event",
        name="spec event",
        guests=[_guest(guest) for guest in spec.get("guests", [])],
        tables=[_table(table) for table in spec.get("tables", [])],
        rules=[_rule(index, rule) for index, rule in enumerate(spec.get("rules", []))],
    )
    result = solve_hard(
        event,
        SolverConfig(
            time_limit_s=float(config.get("time_limit_s", DEFAULT_TIME_LIMIT_S)),
            seed=int(config.get("seed", _DEFAULT_SEED)),
        ),
        # The seam's spec shape carries no mode field: a plain
        # hard-constraint solve is a planning solve.
        mode=PLANNING,
    )
    return {"status": result.status, "assignments": dict(result.assignments)}
