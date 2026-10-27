# bean-026 — The default wedding template's accessible-seating rule starts disabled, so a template event can be solved

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly: the rule starts disabled) |
| Run order | 26 |
| Depends on | bean-003 |
| Size budget | 3 tasks · 3 files · 350 diff lines |

## Intent

An event that starts from the default wedding template can be solved as it stands: the template still carries its hard accessible-seating rule, created disabled until seat positions are configured, so enabling it later is one field.

## Background

A defect found by the retroactive review of 2026-09-28 in the code bean-003 shipped. default_wedding_rules() returns seven rules, all enabled. Six are soft same-table or different-table rules. The seventh, template-accessible_seating, is a HARD min_distance rule (target dance_floor, two zones). The solver has no table-level meaning for min_distance and refuses any enabled hard rule it cannot express, so every event built from the template raises instead of solving, and the pre-flight check reports nothing.
Measured on the main branch: an event with three tables of eight, fourteen confirmed guests, one group per template category and the template's rules as they come. run_preflight returns no findings, and solve_event in planning mode raises "hard rule 'template-accessible_seating' of kind 'min_distance' has no table-level interpretation".
The owner's decision: the template creates the rule disabled until seat positions are configured. It stays a hard min_distance rule with the same target and zone count, so turning it on is setting enabled to true. Disabled rules are already ignored by the solver and the pre-flight check. bean-003's own template test asserts that every template rule starts enabled; that one expectation changes with this bean.

## May write

- `src/seating_planner/rules/template.py`
- `tests/rules/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | An event whose rules are exactly default_wedding_rules(), with one group per template category and enough seats for every guest, solves in planning mode with every guest seated. | `test` `tests/rules/test_template_defaults.py::test_template_event_solves` |
| ac2 | The template's template-accessible_seating rule is present with enabled false and is otherwise the same rule as before (hard, min_distance, no weight, group accessible_seating, target dance_floor, two zones), so setting enabled to true alone restores it; it stays disabled through to_dict and from_dict. | `test` `tests/rules/test_template_defaults.py::test_accessible_rule_starts_disabled` |
| ac3 | The other six template rules are unchanged, and each starts enabled. | `test` `tests/rules/test_template_defaults.py::test_other_template_rules_unchanged` |
| ac4 | Every existing test passes; the existing template test changes only where it expects every template rule to start enabled. | `command` `pytest -q` |

## Constraints

- the template still returns seven rules, one per category, fresh on every call
- the default_wedding_rules signature and TEMPLATE_CATEGORIES are unchanged

## Non-goals

- no change to how the solver treats min_distance rules; an enabled hard min_distance rule is still refused
- no pre-flight warning about rules the solver cannot express
- no change to what happens when a template rule names a group the event does not have

