"""Table-level hard-constraint solving on OR-Tools CP-SAT (FR-045/FR-047),
and the inspectable result every optimization returns (FR-049)."""

from .hard import (
    DEFAULT_TIME_LIMIT_S,
    SolverConfig,
    SolverTimeout,
    solve_hard,
)
from .result import (
    SATISFIED,
    UNEVALUABLE,
    VIOLATED,
    RuleAssessment,
    SolveResult,
    summarize,
)

__all__ = [
    "DEFAULT_TIME_LIMIT_S",
    "SATISFIED",
    "UNEVALUABLE",
    "VIOLATED",
    "RuleAssessment",
    "SolveResult",
    "SolverConfig",
    "SolverTimeout",
    "solve_hard",
    "summarize",
]
