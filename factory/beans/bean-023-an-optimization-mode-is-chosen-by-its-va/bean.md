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
v2 rebuild note (2026-11-09): the defect above is the ORIGINAL build's. On the v2 rebuild, solve_hard already validates and dispatches the mode by value, and the hidden suite for this bean passes on v2 main (a mode string from json.loads or a join behaves exactly as the literal does, including the refusal without a current chart). So here this bean is REGRESSION-PINNING: add tests/solver/test_mode_values.py with the two tests named in ac1 and ac2, which pass immediately against the existing code, and leave the source alone. Check by reading hard.py that no mode comparison uses `is` / `is not`; if one does, or if either test fails, fix it by comparing by value. Do not invent a source change to match the description above.

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

- on a tree where the behaviour is already correct, the change is tests only and touches no source file
- the solve_event signature and the set of accepted modes are unchanged

## Non-goals

- no new modes
- no change to what any mode optimizes

