# bean-024 — The worker count a caller asks for is the one the solver runs with

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly) |
| Run order | 24 |
| Depends on | bean-009 |
| Size budget | 3 tasks · 3 files · 300 diff lines |

## Intent

A num_search_workers value passed to solve_event is applied to every CP-SAT solve it runs and recorded on the result, rather than accepted, validated and replaced by one.

## Background

A defect found on 2026-09-28 in the code bean-009 shipped. solve_event takes num_search_workers, checks that it is at least 1 and stores it on the early-return paths, but every CP-SAT solver it builds sets `solver.parameters.num_search_workers = 1`. The recorded configuration is read back from the solver, so it is honest about the 1; the caller who asked for 4 is simply ignored, and two results for the same request can record different worker counts depending on which path returned. bean-009's spec asked for both the keyword and the hard-coded line, so the build did what it was told.
Determinism across runs still holds for any fixed worker count, which is what bean-009's replay guarantee needs: the configuration recorded is the one to replay.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A feasible solve asked for two workers records two workers in its solver configuration. | `test` `tests/solver/test_worker_count.py::test_requested_workers_are_used` |
| ac2 | Every result, whichever path produced it, records the worker count that was requested. | `test` `tests/solver/test_worker_count.py::test_every_path_records_the_request` |
| ac3 | Every existing solver test still passes unchanged. | `command` `pytest -q tests/solver` |

## Constraints

- the default stays one worker
- the solve_event signature is unchanged
- the solves that diagnose an infeasible event may stay at one worker, because an infeasible core is only reliable with one; the result still records the request

## Non-goals

- no claim that a multi-worker solve is reproducible across worker counts

