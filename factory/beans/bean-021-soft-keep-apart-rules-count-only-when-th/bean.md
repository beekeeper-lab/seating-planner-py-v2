# bean-021 — Soft keep-apart rules count only when their guests sit apart

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly) |
| Run order | 21 |
| Depends on | bean-007 |
| Size budget | 3 tasks · 3 files · 300 diff lines |

## Intent

A soft different-table rule adds its weight to the optimization objective only in a chart where its guests are at different tables, so a heavier keep-apart preference outweighs a lighter sit-together one.

## Background

A defect found on 2026-09-28 in the code bean-007 shipped. Each soft rule has an indicator in the CP-SAT model that is meant to be true only while the rule is satisfied, and the objective maximizes the weighted sum of those indicators. For same-table rules the indicator is bounded from above, so it can only be true when the guests share a table. For different-table rules it is only bounded from below: it is forced true when the guests are together and left free when they are apart. A maximizer sets it true either way, so every soft keep-apart rule scores as satisfied whatever the chart does, and never influences which chart is returned.
Measured on the main branch: two guests, two tables of two, a weight-100 soft different-table rule and a weight-1 soft same-table rule between the same pair. The solver seats them together, and the result's own report lists the weight-100 rule as violated with a score of 1. bean-007's tests did not see it because its only keep-apart case is one where table capacity forces the separation anyway.
The result reporting from bean-008 recomputes satisfaction from the chart and is right; the defect is only in what the solver optimizes.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | When a weight-100 soft different-table rule and a weight-1 soft same-table rule name the same two guests and both charts are valid, the guests are seated at different tables. | `test` `tests/solver/test_soft_keep_apart.py::test_heavier_keep_apart_wins` |
| ac2 | On small events, no valid chart has a higher reported soft score than the chart the solver returns, checked by enumerating every valid chart. | `test` `tests/solver/test_soft_keep_apart.py::test_returned_chart_is_optimal` |
| ac3 | Every existing solver test still passes unchanged. | `command` `pytest -q tests/solver` |

## Constraints

- the fix is in how soft rules enter the objective; hard constraints and their encoding are unchanged
- the solve_event signature and the result shape are unchanged

## Non-goals

- no new rule kinds
- no change to result reporting or score computation (bean-008)

