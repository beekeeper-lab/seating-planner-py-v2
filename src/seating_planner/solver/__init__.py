"""Table-level hard-constraint solving on OR-Tools CP-SAT (FR-045/FR-047),
and the inspectable result every optimization returns (FR-049)."""

from .alternatives import (
    ALTERNATIVE_KINDS,
    AdmissionResult,
    Alternative,
    admit_new_guest,
)
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
    "ALTERNATIVE_KINDS",
    "CORRECTIVE_KINDS",
    "DEFAULT_TIME_LIMIT_S",
    "SATISFIED",
    "UNEVALUABLE",
    "VIOLATED",
    "AdmissionResult",
    "Alternative",
    "InfeasibilityReport",
    "Recommendation",
    "RuleAssessment",
    "SolveResult",
    "SolverConfig",
    "SolverTimeout",
    "admit_new_guest",
    "build_infeasibility_report",
    "solve_hard",
    "summarize",
]
