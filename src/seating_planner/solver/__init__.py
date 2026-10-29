"""Table-level hard-constraint solving on OR-Tools CP-SAT (FR-045/FR-047),
and the inspectable result every optimization returns (FR-049)."""

from .hard import (
    DEFAULT_TIME_LIMIT_S,
    SolverConfig,
    SolverTimeout,
    solve_hard,
)
from .report import (
    CORRECTIVE_KINDS,
    InfeasibilityReport,
    Recommendation,
    build_infeasibility_report,
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
    "CORRECTIVE_KINDS",
    "DEFAULT_TIME_LIMIT_S",
    "SATISFIED",
    "UNEVALUABLE",
    "VIOLATED",
    "InfeasibilityReport",
    "Recommendation",
    "RuleAssessment",
    "SolveResult",
    "SolverConfig",
    "SolverTimeout",
    "build_infeasibility_report",
    "solve_hard",
    "summarize",
]
