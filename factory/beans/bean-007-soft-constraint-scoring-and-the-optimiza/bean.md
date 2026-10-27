# bean-007 — Soft-constraint scoring and the optimization objective

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 7 |
| Depends on | bean-006 |
| Independent invariants | `factory/invariants/seating.yaml` — authored outside this bean, not editable by the line |
| Size budget | 5 tasks · 4 files · 350 diff lines |

## Intent

Among assignments that satisfy every hard constraint, the solver returns the one with the highest weighted total of satisfied soft constraints.

## Background

bean-006 finds any valid answer. This bean makes it find a good one. Each soft rule gets an indicator variable that is true when the rule is satisfied, and the solver maximizes the sum of weight times indicator. The ordering matters and is not negotiable: hard constraints remain constraints, not heavily-weighted preferences — a soft rule with weight 100 must never be able to buy its way past a hard rule. This bean modifies the model that bean-006 built rather than adding a separate path.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Given two valid arrangements, the one with the higher weighted soft score is returned. | `test` `tests/solver/test_objective.py::test_higher_score_preferred` |
| ac2 | A weight-100 soft rule never causes a hard rule to be violated. | `test` `tests/solver/test_objective.py::test_soft_never_overrides_hard` |
| ac3 | Soft rules are honoured in weight order when they conflict with each other. | `test` `tests/solver/test_objective.py::test_conflicting_soft_rules_follow_weight` |
| ac4 | Every hard-constraint test from bean-006 still passes unchanged. | `command` `pytest -q tests/solver/test_hard_constraints.py` |

## Constraints

- hard constraints stay constraints, never large weights
- the bean-006 public entry point keeps its signature

## Non-goals

- no reporting of which rules were violated (bean-008)

