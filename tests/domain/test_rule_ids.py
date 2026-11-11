"""Acceptance tests: an event's rule ids are unique (bean-027, ac2).

The domain already refuses duplicate guest, table and group
identifiers; rule ids get the same treatment, in the same style,
without the domain learning anything about the rule model: an entry
of ``Event.rules`` is checked exactly when it carries a string
``id`` attribute, and a bare object without one is not checked at
all.
"""

from __future__ import annotations

import pytest

from seating_planner.domain import Event
from seating_planner.rules import Hardness, Rule, RuleKind


def soft(rid: str, weight: int, *, enabled: bool = True) -> Rule:
    """A real soft same-table rule: an id, two guests, a weight in 1..100."""
    return Rule(
        id=rid,
        kind=RuleKind.SAME_TABLE,
        hardness=Hardness.SOFT,
        guests=("g1", "g2"),
        weight=weight,
        enabled=enabled,
    )


def test_duplicate_rule_id_is_refused() -> None:
    """ac2: two rules sharing an id are refused — an event built with
    the pair, and an event the second rule was added to afterwards —
    with a message that names the id, whether or not either rule is
    enabled."""
    first = soft("dup", 10)
    second = soft("dup", 1)
    with pytest.raises(ValueError) as exc:
        Event(id="e1", name="Wedding", rules=[first, second])
    assert "dup" in str(exc.value)

    built = Event(id="e2", name="Wedding", rules=[first])
    with pytest.raises(ValueError) as exc:
        built.add_rule(second)
    assert "dup" in str(exc.value)

    off_first = soft("dup", 10, enabled=False)
    off_second = soft("dup", 1, enabled=False)
    with pytest.raises(ValueError) as exc:
        Event(id="e3", name="Wedding", rules=[off_first, off_second])
    assert "dup" in str(exc.value)


def test_unique_rule_ids_still_accepted() -> None:
    """Control: distinct ids are accepted, by construction and through
    ``add_rule``, exactly as before."""
    event = Event(id="e1", name="Wedding", rules=[soft("a", 10)])
    event.add_rule(soft("b", 1))
    event.add_rule(soft("c", 50, enabled=False))
    assert [rule.id for rule in event.rules] == ["a", "b", "c"]
    event_two = Event(
        id="e2",
        name="Wedding",
        rules=[soft("x", 1), soft("y", 2, enabled=False)],
    )
    assert [rule.id for rule in event_two.rules] == ["x", "y"]


def test_entries_without_an_id_are_not_checked() -> None:
    """Constraint: ``Event.rules`` stays a list of objects, and an entry
    without an id carries no domain check at all."""
    event = Event(id="e1", name="Wedding", rules=[object(), object()])
    event.add_rule(object())
    assert len(event.rules) == 3
