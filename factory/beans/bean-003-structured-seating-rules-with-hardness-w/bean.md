# bean-003 — Structured seating rules with hardness, weight and the wedding template

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 3 |
| Depends on | bean-002 |
| Size budget | 6 tasks · 5 files · 450 diff lines |

## Intent

Every seating rule exists as inspectable structured data with an explicit type, hardness and weight — never as prose and never only inside a prompt.

## Background

A rule says something like "these two guests must sit at the same table" or "keep this guest away from the dance floor". Each one needs a type, the guests or groups it applies to, whether it is hard (may not be violated) or soft (a preference with a weight from 1 to 100), and any parameters such as a distance. FR-035 is the sharp edge: a minimum-distance rule must carry a number, so a vague phrase like "far apart" cannot be stored as something the solver will later pretend to enforce. FR-028/029 require a new wedding event to start with an editable default rule template covering couples, households, immediate family, wedding party, children, vendors and accessible seating.

## May write

- `src/seating_planner/rules/**`
- `tests/rules/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Every rule type named in FR-034 can be constructed and round-trips through serialization unchanged. | `test` `tests/rules/test_rule_model.py::test_all_rule_types_roundtrip` |
| ac2 | A soft rule requires an integer weight in 1..100 and rejects values outside it. | `test` `tests/rules/test_rule_model.py::test_soft_weight_bounds` |
| ac3 | A hard rule carries no weight, and constructing one with a weight is rejected. | `test` `tests/rules/test_rule_model.py::test_hard_rule_has_no_weight` |
| ac4 | A minimum-distance rule without a numeric distance or zone count is rejected. | `test` `tests/rules/test_rule_model.py::test_min_distance_requires_measure` |
| ac5 | The default wedding template yields rules for couples, households, immediate family, wedding party, children, vendors and accessible seating, each independently enable-able. | `test` `tests/rules/test_template.py::test_default_wedding_template` |

## Constraints

- rules are data only; no evaluation logic in this bean
- no solver imports  
  *checked, not judged:* import `ortools`

## Non-goals

- no rule evaluation or scoring (bean-005, bean-007)  
  *checked, not judged:* `src/seating_planner/feasibility/**`, `src/seating_planner/solver/**`
- no adjacent-seat evaluation (deferred; see PRD §18.3 assumption)
- no natural-language rule parsing

