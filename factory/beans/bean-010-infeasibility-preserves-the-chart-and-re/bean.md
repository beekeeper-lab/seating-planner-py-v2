# bean-010 — Infeasibility preserves the chart and recommends corrective action

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 10 |
| Depends on | bean-009 |
| Size budget | 6 tasks · 5 files · 650 diff lines |

## Intent

When no valid assignment exists, the saved seating chart is untouched, the conflicting hard constraints are named, and at least one concrete fix is offered.

## Background

Three different ways of failing must all leave the same footprint: infeasible, timed out, and cancelled. In every case the previously saved chart stays exactly as it was — the temptation to write a partial assignment "so the user can see progress" is precisely what FR-052 forbids. CP-SAT can report an assumption subset that made the model infeasible, which is what turns "no answer" into "these two rules and this lock cannot all hold".

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | An infeasible optimization leaves the previously saved chart byte-identical. | `test` `tests/solver/test_infeasible.py::test_saved_chart_unchanged_on_infeasible` |
| ac2 | A timed-out optimization leaves the previously saved chart byte-identical. | `test` `tests/solver/test_infeasible.py::test_saved_chart_unchanged_on_timeout` |
| ac3 | The infeasibility report names the specific hard constraints in the conflict, not merely that one exists. | `test` `tests/solver/test_infeasible.py::test_conflict_names_hard_constraints` |
| ac4 | At least one corrective action is recommended, drawn from adding capacity, unlocking, changing a hard rule, or adding a table. | `test` `tests/solver/test_infeasible.py::test_recommends_corrective_action` |

## Constraints

- no partial assignment is ever persisted

## Non-goals

- no automatic application of a recommended fix

