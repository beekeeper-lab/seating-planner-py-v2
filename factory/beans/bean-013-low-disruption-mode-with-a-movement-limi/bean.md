# bean-013 — Low-disruption mode with a movement limit as a hard constraint

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 13 |
| Depends on | bean-012 |
| Independent invariants | `factory/invariants/seating.yaml` — authored outside this bean, not editable by the line |
| Size budget | 6 tasks · 4 files · 550 diff lines |

## Intent

Recalculation shortly before the event improves the chart while moving no more guests between tables than the organizer permits.

## Background

This mode has a two-level objective and the order is specified, not a preference: minimize table changes first, then maximize the soft score among the arrangements that tie. Implementing it as a single weighted sum would let a high enough soft score buy an extra disruption, which FR-066 forbids. A disruption is specifically a change of table (per the §5 definition); a seat change at the same table is counted separately and does not exist yet. The movement limit being a hard constraint means a low-disruption run can be infeasible for a reason unrelated to capacity, and the report must say which.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | No more guests change tables than the configured limit permits. | `test` `tests/solver/test_low_disruption.py::test_movement_limit_respected` |
| ac2 | Given two arrangements within the limit, the one with fewer table changes wins even when the other scores higher. | `test` `tests/solver/test_low_disruption.py::test_fewer_moves_beats_higher_score` |
| ac3 | Among arrangements with equally few moves, the higher soft score is chosen. | `test` `tests/solver/test_low_disruption.py::test_score_breaks_tie_on_moves` |
| ac4 | A limit too small to admit any valid arrangement is reported infeasible and names the movement limit as the cause, distinct from capacity. | `test` `tests/solver/test_low_disruption.py::test_limit_infeasibility_names_its_cause` |
| ac5 | A limit of zero produces no table changes at all. | `test` `tests/solver/test_low_disruption.py::test_zero_limit_changes_nothing` |

## Constraints

- lexicographic objective, not a weighted sum
- a disruption is a table change, per the PRD §5 definition

## Non-goals

- no seat-change accounting (seats are deferred)

