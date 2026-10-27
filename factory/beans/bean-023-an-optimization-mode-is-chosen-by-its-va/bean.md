# bean-023 — An optimization mode is chosen by its value, not by which string object names it

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly) |
| Run order | 23 |
| Depends on | bean-013 |
| Size budget | 3 tasks · 3 files · 300 diff lines |

## Intent

solve_event dispatches on the mode's value, so a mode string read from a file, a request or a join behaves exactly as the same literal does.

## Background

A defect found on 2026-09-28 in the code bean-013 shipped. solve_event validates the mode with `mode not in (PLANNING, LOW_DISRUPTION)`, which compares by equality, and then dispatches with `if mode is LOW_DISRUPTION:`, which compares object identity. Python happens to share one object for identical string literals in source, so every test passes; a mode string that arrives any other way (read from JSON, joined, taken from a request) is equal but not identical.
Measured on the main branch: `json.loads('"low_disruption"')` as the mode raises "current does not apply to the planning mode", and `"".join(["low_", "disruption"])` with no current chart and no movement limit is accepted and runs a planning solve labelled low_disruption, with no movement limit at all.
Every comparison of a mode, in every mode the solver has when this bean runs, compares by value.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A low-disruption solve given its mode as a string built at run time respects the movement limit exactly as the literal does. | `test` `tests/solver/test_mode_values.py::test_runtime_mode_string_is_the_same_mode` |
| ac2 | A mode string built at run time that needs a current chart is refused without one, exactly as the literal is. | `test` `tests/solver/test_mode_values.py::test_runtime_mode_string_is_validated_the_same` |
| ac3 | Every existing solver test still passes unchanged. | `command` `pytest -q tests/solver` |

## Constraints

- the solve_event signature and the set of accepted modes are unchanged

## Non-goals

- no new modes
- no change to what any mode optimizes

