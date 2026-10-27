# bean-006 — CP-SAT table assignment satisfying hard constraints

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 6 |
| Depends on | bean-005 |
| Independent invariants | `factory/invariants/seating.yaml` — authored outside this bean, not editable by the line |
| Size budget | 6 tasks · 5 files · 550 diff lines |

## Intent

Eligible guests are assigned to tables such that no hard constraint and no table capacity is violated, or the problem is reported infeasible.

## Background

CP-SAT is a constraint solver: you declare boolean variables and the relationships that must hold between them, and it searches for an assignment satisfying all of them. Here the variable is "guest g sits at table t". Each guest needs exactly one true value across tables; each table's true values must not exceed its capacity; a same-table rule forces two guests' variables to agree; a different-table rule forces them to differ. This bean handles hard constraints only — it either returns a valid assignment or reports infeasible, with no notion yet of a better or worse answer among valid ones.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`
- `src/seating_planner/invariant_api.py`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | With sufficient capacity and satisfiable rules, every eligible guest is assigned to exactly one table. | `test` `tests/solver/test_hard_constraints.py::test_all_eligible_guests_assigned` |
| ac2 | No table is assigned more guests than its capacity. | `test` `tests/solver/test_hard_constraints.py::test_capacity_never_exceeded` |
| ac3 | A same-table hard rule places both guests at one table; a different-table hard rule separates them. | `test` `tests/solver/test_hard_constraints.py::test_same_and_different_table_rules` |
| ac4 | Ineligible guests are never assigned. | `test` `tests/solver/test_hard_constraints.py::test_ineligible_guests_unassigned` |
| ac5 | An unsatisfiable hard-constraint set returns an infeasible result rather than a partial assignment. | `test` `tests/solver/test_hard_constraints.py::test_infeasible_returns_no_assignment` |

## Constraints

- OR-Tools CP-SAT only; no hand-rolled heuristic fallback  
  *checked, not judged:* import `pulp`, import `mip`, import `cvxpy`, import `gurobipy`, import `pyomo`, import `networkx`
- table-level assignment only
- solve time bounded by an explicit configurable limit

## Non-goals

- no soft constraints or scoring (bean-007)
- no seat-level assignment
- no locks (bean-011)

