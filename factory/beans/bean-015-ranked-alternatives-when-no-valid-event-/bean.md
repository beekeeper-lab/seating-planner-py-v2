# bean-015 — Ranked alternatives when no valid event-day seat exists

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 15 |
| Depends on | bean-014 |
| Size budget | 6 tasks · 4 files · 900 diff lines |

## Intent

When a late guest cannot be seated without breaking something, they are left unassigned and the organizer is offered concrete options ranked by how much they cost.

## Background

This is the moment the product exists for: a guest arrives, the room is full, and the organizer has thirty seconds. Refusing to seat them is correct — Principle 5 forbids silently breaking a hard rule — but refusing without options is useless. Each alternative is a hypothetical: if you unlocked this guest, or added a table, or authorized this exception, here is what it would cost. Ranking is by disruption count first, then by the weight of any rule the option would violate, so the cheapest honest option is at the top.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | With no valid seat the guest is left unassigned and no existing assignment changes. | `test` `tests/solver/test_event_day_alternatives.py::test_guest_unassigned_nothing_moves` |
| ac2 | At least one alternative is offered, drawn from adding a table, changing capacity, unlocking, or authorizing an exception. | `test` `tests/solver/test_event_day_alternatives.py::test_alternatives_are_offered` |
| ac3 | Alternatives are ordered by disruption count, then by violated-rule weight. | `test` `tests/solver/test_event_day_alternatives.py::test_alternatives_ranked_correctly` |
| ac4 | Each alternative states its disruption count and any rule it would violate. | `test` `tests/solver/test_event_day_alternatives.py::test_alternative_states_its_cost` |
| ac5 | Generating alternatives changes no saved state. | `test` `tests/solver/test_event_day_alternatives.py::test_alternatives_are_read_only` |

## Constraints

- alternatives are proposals; none is applied automatically

## Non-goals

- no automatic selection of an alternative

