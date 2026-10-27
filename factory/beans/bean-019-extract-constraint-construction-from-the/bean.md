# bean-019 — Extract constraint construction from the solver module

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 19 |
| Depends on | bean-018 |
| Size budget | 5 tasks · 5 files · 2800 diff lines |

## Intent

The solver module is split so that building the CP-SAT model is separate from running and interpreting it, with no change in behaviour whatsoever.

## Background

Beans 006 through 016 each added to the same solver module: hard constraints, an objective, results, determinism, locks, three modes, proposals. It now does several jobs at once. This bean separates model construction from solving and from result interpretation.
The defining property is that nothing observable changes. Every existing test must pass untouched — a refactor that needs its tests edited is not a refactor, it is a behaviour change wearing one as a disguise. If a test genuinely must move because the module it imports has moved, the import line may change and nothing else.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | The whole existing test suite passes with no change to any assertion. | `command` `pytest -q` |
| ac2 | Model construction, solving and result interpretation live in separate modules. | `manual` `Confirm the diff moves constraint-building, solve invocation and result interpretation into distinct modules, that no probe- or production-solve call (CpSolver) lives in the interpretation module, and that no assertion in any test file was modified -- only import paths may differ. A changed assertion means behaviour changed.` |
| ac3 | The public optimization entry point keeps its name and signature. | `test` `tests/solver/test_api_stability.py::test_public_entry_point_unchanged` |
| ac4 | Optimizing a fixed scenario produces the identical assignment it produced before the refactor. | `test` `tests/solver/test_determinism.py::test_repeat_run_is_identical` |

## Constraints

- no behaviour change of any kind
- no new dependencies  
  *checked, not judged:* `pyproject.toml`, `requirements*.txt`
- test assertions must not be edited

## Non-goals

- no new features
- no performance work

