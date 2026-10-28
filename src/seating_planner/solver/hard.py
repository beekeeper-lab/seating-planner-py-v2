"""Hard-constraint table assignment on OR-Tools CP-SAT (FR-045, FR-047).

Stub: the encoding and the solve land in task-2. The public surface is
final so that the acceptance tests import the real names from day one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from seating_planner.domain import Event

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


def solve_hard(event: Event, config: SolverConfig | None = None) -> SolveResult:
    raise NotImplementedError("the CP-SAT encoding and solve land in task-2")
