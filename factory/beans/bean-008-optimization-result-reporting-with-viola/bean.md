# bean-008 — Optimization result reporting with violations and affected guests

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 8 |
| Depends on | bean-007 |
| Size budget | 5 tasks · 4 files · 450 diff lines |

## Intent

Every optimization returns an inspectable result naming what was assigned, what was not, the score, and every rule it failed to satisfy along with the guests involved.

## Background

Product Principle 2 says results must be explainable, and this is where that is earned. The solver knows which soft-rule indicators came out false; the result must carry them outward as named violations with the guests each one concerns, not as a bare score. Principle 6 ("no false success") has a specific consequence here: a rule the system could not evaluate must never be reported as satisfied — it is a distinct third state alongside satisfied and violated.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | The result reports assigned count, unassigned count and total soft score consistent with the assignment. | `test` `tests/solver/test_result.py::test_counts_and_score_consistent` |
| ac2 | Each violated soft constraint appears once with its rule id, weight and affected guest ids. | `test` `tests/solver/test_result.py::test_violations_name_rule_and_guests` |
| ac3 | A rule that could not be evaluated is reported as unevaluable, never as satisfied. | `test` `tests/solver/test_result.py::test_unevaluable_is_not_satisfied` |
| ac4 | Satisfied, violated and unevaluable rule counts together equal the number of active rules. | `test` `tests/solver/test_result.py::test_rule_accounting_is_complete` |

## Constraints

- the result object is serializable
- no private guest notes in the result payload

## Non-goals

- no corrective recommendations (bean-010)

