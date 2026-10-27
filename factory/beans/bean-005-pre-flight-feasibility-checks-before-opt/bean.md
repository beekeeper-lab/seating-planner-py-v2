# bean-005 — Pre-flight feasibility checks before optimization

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 5 |
| Depends on | bean-003 |
| Size budget | 6 tasks · 5 files · 400 diff lines |

## Intent

Structurally impossible seating problems are identified and explained before the solver is ever invoked, rather than surfacing as an opaque failure.

## Background

This is the first bean that reads code written by earlier beans rather than creating its own world. Four failures can be detected by inspection, with no search at all: two hard rules that directly contradict (same-table and different-table for the same pair), a group that must stay together but is larger than the largest table, a rule referring to a table or zone that does not exist, and more eligible guests than total seats. Catching these here means the solver's own "infeasible" answer is reserved for genuinely hard cases, which makes FR-050's conflict report meaningful.

## May write

- `src/seating_planner/feasibility/**`
- `tests/feasibility/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A same-table and a different-table hard rule over the same guest pair is reported as a contradiction naming both rules. | `test` `tests/feasibility/test_preflight.py::test_contradictory_hard_rules` |
| ac2 | A group that must stay together and exceeds every table capacity is reported with the group and the largest capacity. | `test` `tests/feasibility/test_preflight.py::test_group_larger_than_any_table` |
| ac3 | Eligible guests exceeding total capacity is reported with both counts. | `test` `tests/feasibility/test_preflight.py::test_insufficient_capacity` |
| ac4 | A rule naming a table or zone that does not exist is reported. | `test` `tests/feasibility/test_preflight.py::test_rule_references_missing_target` |
| ac5 | A satisfiable problem reports no findings. | `test` `tests/feasibility/test_preflight.py::test_feasible_problem_is_clean` |

## Constraints

- no solver imports; this bean must not call CP-SAT  
  *checked, not judged:* import `ortools`
- checks are structural only, never a search

## Non-goals

- no attempt to prove general infeasibility (that is the solver's job)
- no corrective recommendations (bean-010)

