"""Pre-flight structural feasibility checks, run before the solver (FR-041)."""

from .preflight import KNOWN_ZONE_NAMES, Finding, preflight, run_preflight

__all__ = ["KNOWN_ZONE_NAMES", "Finding", "preflight", "run_preflight"]
