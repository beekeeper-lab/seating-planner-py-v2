"""Pre-flight structural feasibility checks, run before the solver (FR-041).

Four structural dead-ends are readable as set/dict/sum work over an
``Event``'s collections, before any search. An empty result is an early
explanation, not a certificate: nothing structurally impossible was found.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind

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
    """Run all four structural checks in fixed section order; no search."""
    rules = [rule for rule in event.rules if isinstance(rule, Rule) and rule.enabled]
    zones = frozenset(known_zones) | KNOWN_ZONE_NAMES
    return [
        *_contradictions(rules),
        *_oversized_groups(event, rules),
        *_total_capacity(event),
        *_missing_targets(event, rules, zones),
    ]


def _contradictions(rules: list[Rule]) -> list[Finding]:
    """One finding per hard same/different-table rule pair sharing a pair."""
    findings: list[Finding] = []
    for pos, same in enumerate(rules):
        if not _is_hard(same, RuleKind.SAME_TABLE):
            continue
        for diff in rules[pos + 1 :]:
            if not _is_hard(diff, RuleKind.DIFFERENT_TABLE):
                continue
            pair = _shared_pair(same, diff)
            if pair is None:
                continue
            first, second = pair
            findings.append(
                Finding(
                    kind="contradictory_hard_rules",
                    message=(
                        f"hard rule {same.id} keeps {first} and {second} at "
                        f"the same table, but hard rule {diff.id} requires "
                        f"them at different tables"
                    ),
                    rule_ids=(same.id, diff.id),
                )
            )
    return findings


def _shared_pair(rule_a: Rule, rule_b: Rule) -> tuple[str, str] | None:
    """The shared pair from the smaller guest list, sorted, else ``None``."""
    small, large = sorted((rule_a, rule_b), key=lambda rule: len(rule.guests))
    pair = set(small.guests)
    if len(pair) != 2 or not pair <= set(large.guests):
        return None
    first, second = sorted(pair)
    return (first, second)


def _is_hard(rule: Rule, kind: RuleKind) -> bool:
    """Whether the rule is hard and of the given kind."""
    return rule.hardness is Hardness.HARD and rule.kind is kind


def _oversized_groups(event: Event, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    groups = {group.id: group for group in event.groups}
    largest = max((table.capacity for table in event.tables), default=0)
    for rule in rules:
        if not _is_hard(rule, RuleKind.SAME_TABLE) or rule.group_id is None:
            continue
        group = groups.get(rule.group_id)
        if group is None:
            continue
        # Distinct member ids, ineligible included: bean-022 changes that.
        size = len(set(group.member_ids))
        if size > largest:
            findings.append(
                Finding(
                    kind="group_larger_than_any_table",
                    message=(
                        f"group {group.id} ({group.name}) must stay together "
                        f"at {size}, but the largest table seats {largest}"
                    ),
                    rule_ids=(rule.id,),
                )
            )
    return findings


def _total_capacity(event: Event) -> list[Finding]:
    eligible = sum(1 for guest in event.guests if guest.eligible)
    seats = sum(table.capacity for table in event.tables)
    if eligible <= seats:
        return []
    return [
        Finding(
            kind="insufficient_capacity",
            message=f"{eligible} eligible guests but only {seats} seats in total",
        )
    ]


def _missing_targets(
    event: Event, rules: list[Rule], zones: frozenset[str]
) -> list[Finding]:
    """Enabled rules whose ``target`` is no table id/name and no zone."""
    table_ids = {table.id for table in event.tables}
    table_names = {table.name for table in event.tables}
    findings: list[Finding] = []
    for rule in rules:
        if (
            rule.target is not None
            and rule.target not in table_ids
            and rule.target not in table_names
            and rule.target not in zones
        ):
            findings.append(
                Finding(
                    kind="missing_target",
                    message=(
                        f"rule {rule.id} names a table or zone that does "
                        f"not exist: {rule.target}"
                    ),
                    rule_ids=(rule.id,),
                )
            )
    return findings


#: Shorter alias for callers that prefer the verb form.
preflight = run_preflight
