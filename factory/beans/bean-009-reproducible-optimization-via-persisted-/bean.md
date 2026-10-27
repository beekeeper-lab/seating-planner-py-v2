# bean-009 — Reproducible optimization via persisted solver configuration

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 9 |
| Depends on | bean-008 |
| Independent invariants | `factory/invariants/seating.yaml` — authored outside this bean, not editable by the line |
| Size budget | 5 tasks · 4 files · 450 diff lines |

## Intent

Re-running an optimization over identical inputs produces an identical assignment, and the configuration needed to reproduce it is stored with the result.

## Background

CP-SAT searches in parallel by default, and parallel search is not deterministic: whichever worker finds an optimal answer first decides which of several equally-good answers you get. Determinism therefore requires pinning the worker count and the random seed, and storing both with the result so a later run can be reproduced exactly. There is a real tension with NFR-001's 15-second target, because pinning workers costs wall-clock — the manifest records this as an open owner decision, and this bean's job is to make the configuration explicit rather than to resolve it.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Two runs over identical inputs and configuration produce byte-identical assignments. | `test` `tests/solver/test_determinism.py::test_repeat_run_is_identical` |
| ac2 | The result carries the solver seed, worker count and time limit actually used. | `test` `tests/solver/test_determinism.py::test_result_records_configuration` |
| ac3 | Replaying a stored configuration against the same inputs reproduces the stored assignment. | `test` `tests/solver/test_determinism.py::test_stored_config_reproduces_result` |
| ac4 | Changing only the seed may change the assignment, and that is reported rather than hidden. | `test` `tests/solver/test_determinism.py::test_seed_change_is_visible` |

## Constraints

- determinism is achieved by configuration, not by sorting the output afterwards

## Non-goals

- no performance tuning against NFR-001 in this bean

