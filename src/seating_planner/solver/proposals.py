"""An optimization's result as a proposal the organizer can see and accept (FR-072).

A proposal is what an optimization produces before anything it found reaches
the saved chart: the full proposed chart, and a comparison listing every
guest whose table would change, with the old and the new table named. The
comparison is the set-union of the saved chart's guests and the proposed
chart's guests, so a guest the proposal unseats and a guest it seats for the
first time are both representable — with the missing side a plain ``None`` —
rather than silently absent.

The run-1 shape was the defect this module exists to close: a solve that is
genuinely infeasible and a solve that changed nothing both looked like an
empty proposal, and whatever applied the proposal had nothing to refuse.
Here the solve's status is a field on the value, never derived from whether
the comparison is empty, so "infeasible" and "feasible, nothing changes"
carry different data and a downstream check can tell them apart.

``optimize`` runs exactly one ``solve_hard`` and wraps it. The call is
read-only: it writes nothing, and this module imports nothing from the
store layer in any form — the write happens in a separate, deliberate act
somewhere else in the repository, not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from seating_planner.domain import Event

from .hard import PLANNING, SolverConfig, solve_hard

if TYPE_CHECKING:
    # The annotation alone needs the name; the import stays typing-level so
    # the solver layer imports nothing it does not already.
    from .report import InfeasibilityReport


@dataclass(frozen=True)
class Change:
    """One guest whose table a proposal would change, with both sides named."""

    guest_id: str
    old_table: str | None  # None when the guest was not in the saved chart
    new_table: str | None  # None when the proposal does not seat them


@dataclass(frozen=True)
class Proposal:
    """One optimization's result as a value that says what it would change.

    ``status`` is the solve's status — "feasible" | "infeasible" — and is
    what separates a proven no-chart from a feasible no-change solve whose
    shapes otherwise match; an empty proposal is never the whole story.
    ``assignments`` holds the proposed chart (``{}`` when infeasible), and
    ``comparison`` holds every change in guest-id order (``()`` when
    nothing moves). ``infeasibility_report`` is present exactly when
    infeasible, carrying why no chart exists.
    """

    event_id: str
    mode: str
    status: str
    assignments: dict[str, str]
    comparison: tuple[Change, ...]
    infeasibility_report: InfeasibilityReport | None = None


def optimize(
    event: Event,
    config: SolverConfig | None = None,
    *,
    mode: str,
    saved_chart: Mapping[str, str],
    move_limit: int | None = None,
) -> Proposal:
    """Run one ``solve_hard`` and hand its result back as a proposal.

    In ``PLANNING`` mode the solver's baseline is ``None`` — planning
    forbids baseline arguments — while the comparison still runs against
    the saved chart. In every other mode the baseline is the saved chart
    reduced to the event's eligible guests: a guest who declined used to
    sit is simply unpinned, a freed seat, not a pin (FR-071), and the
    reduction is what keeps ``solve_hard`` from rejecting a baseline that
    names an ineligible guest — while the comparison is always computed
    against the full saved chart, so that guest still appears in it as
    unseated (``old_table`` to ``None``).

    ``config``, ``mode``, the baseline and ``move_limit`` pass through to
    ``solve_hard`` untouched, and so do its ``ValueError`` and
    ``SolverTimeout`` — this wrapper adds no behaviour of its own. A
    feasible result becomes a proposal carrying a private copy of the
    assignments and the comparison: every guest in the union of both
    charts whose table differs, sorted by guest id. An infeasible result
    becomes one whose ``assignments`` is ``{}``, whose ``comparison`` is
    ``()``, and which carries the solve's infeasibility report — with
    ``status`` the field that keeps the two shapes apart.
    """
    eligible = frozenset(guest.id for guest in event.guests if guest.eligible)
    if mode == PLANNING:
        baseline: Mapping[str, str] | None = None
    else:
        baseline = {
            guest_id: table_id
            for guest_id, table_id in saved_chart.items()
            if guest_id in eligible
        }
    result = solve_hard(
        event,
        config,
        mode=mode,
        current_assignments=baseline,
        move_limit=move_limit,
    )
    if result.status == "infeasible":
        return Proposal(
            event_id=event.id,
            mode=mode,
            status=result.status,
            assignments={},
            comparison=(),
            infeasibility_report=result.infeasibility_report,
        )
    proposal = dict(result.assignments)
    comparison: tuple[Change, ...] = tuple(
        Change(guest_id, saved_chart.get(guest_id), proposal.get(guest_id))
        for guest_id in sorted(set(saved_chart) | set(proposal))
        if saved_chart.get(guest_id) != proposal.get(guest_id)
    )
    return Proposal(
        event_id=event.id,
        mode=mode,
        status=result.status,
        assignments=proposal,
        comparison=comparison,
    )
