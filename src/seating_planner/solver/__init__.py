"""Table-level hard-constraint solving on OR-Tools CP-SAT (FR-045/FR-047)."""

from .hard import (
    DEFAULT_TIME_LIMIT_S,
    SolverConfig,
    SolveResult,
    SolverTimeout,
    solve_hard,
)

__all__ = [
    "DEFAULT_TIME_LIMIT_S",
    "SolveResult",
    "SolverConfig",
    "SolverTimeout",
    "solve_hard",
]
