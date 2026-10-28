"""Pre-flight structural feasibility checks, run before the solver (FR-041).

Four purely structural dead-ends are readable by set, dict and sum work over
an ``Event``'s own collections, before any search: hard rules that contradict
each other on one guest pair, a group that must stay together at no table,
more eligible guests than seats, and rules that name a table or zone the
event does not have. This module reports them as :class:`Finding` objects.
An empty result is an early explanation, not a certificate: it means nothing
structurally impossible was found, not that the event is solvable.

This is the task-1 stub: the public surface is final, the four checks land
in task-2. No solver import, ever.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from seating_planner.domain import Event

#: Zone names that exist without being declared. The domain has no zone
#: model; this is the zone the corpus names (the template's dance floor).
#: Callers widen the set via ``run_preflight(known_zones=...)``.
KNOWN_ZONE_NAMES: frozenset[str] = frozenset({"dance_floor"})


@dataclass(frozen=True)
class Finding:
    """One structural impossibility, with the names and numbers to act on."""

    kind: str
    message: str
    rule_ids: tuple[str, ...] = ()


def run_preflight(event: Event, known_zones: Iterable[str] = ()) -> list[Finding]:
    raise NotImplementedError("the four pre-flight checks land in task-2")


#: Shorter alias for callers that prefer the verb form.
preflight = run_preflight
