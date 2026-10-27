# bean-012 — Planning mode as an explicit named mode

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 12 |
| Depends on | bean-011 |
| Size budget | 4 tasks · 10 files · 550 diff lines |

## Intent

Optimization is invoked under a named mode, and Planning mode reoptimizes every guest whose assignment is not locked.

## Background

Until now the solver has had one behaviour. The product has three, distinguished only by how they treat assignments that already exist (PRD §12). This bean introduces the mode parameter and implements the least restrictive of the three, which is what the solver already does — so the behaviour is unchanged and the value is the seam. Getting the seam right here is what lets beans 013 and 014 add the other two modes without reshaping the solver each time.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`
- `src/seating_planner/invariant_api.py`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Optimization requires an explicit mode; omitting it is rejected rather than defaulted. | `test` `tests/solver/test_modes.py::test_mode_is_required` |
| ac2 | In Planning mode an unlocked guest may be moved to improve the score. | `test` `tests/solver/test_modes.py::test_planning_moves_unlocked_guest` |
| ac3 | In Planning mode a locked guest is still never moved. | `test` `tests/solver/test_modes.py::test_planning_respects_locks` |
| ac4 | The mode used is recorded on the result. | `test` `tests/solver/test_modes.py::test_result_records_mode` |
| ac5 | All existing solver tests still pass. | `command` `pytest -q tests/solver` |

## Constraints

- mode is an explicit argument with no default

## Non-goals

- no low-disruption or event-day behaviour (beans 013, 014)

