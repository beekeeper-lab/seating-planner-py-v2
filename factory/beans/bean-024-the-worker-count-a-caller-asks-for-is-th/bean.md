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
v2 rebuild note (2026-11-09): the defect above is the ORIGINAL build's. On the v2 rebuild, the requested worker count already reaches the CP-SAT solve and is recorded on every result path (SolverConfig.num_workers, including infeasible and low-disruption solves), and the hidden suite for this bean passes on v2 main. So here this bean is REGRESSION-PINNING: add tests/solver/test_worker_count.py with the two tests named in ac1 and ac2, which pass immediately against the existing code, and leave the source alone. If, and only if, either test fails, fix the worker count so the request is applied and recorded on every path. Do not invent a source change to match the description above.
Run 2 (v2 rebuild, PR #26, closed on its pre-merge review) pinned this only for the planning mode: its spy that reads the worker count each solve actually ran with was exercised in planning alone, and the low_disruption and event_day cases checked only the recorded field. The reviewer re-introduced the original defect for those two modes (the production solve ignores the request but the result still records it) and both tests still passed. So the pin must cover all three modes: with a requested count above 1, spy on the num_search_workers each production solve actually sets in planning, low_disruption and event_day, and also check the recorded count on an infeasible low_disruption and an infeasible event_day result.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A feasible solve asked for two workers records two workers in its solver configuration, and the CP-SAT solve itself runs with two workers, in each of the planning, low_disruption and event_day modes. | `test` `tests/solver/test_worker_count.py::test_requested_workers_are_used` |
| ac2 | Every result, whichever path produced it (including an infeasible low_disruption and an infeasible event_day result), records the worker count that was requested. | `test` `tests/solver/test_worker_count.py::test_every_path_records_the_request` |
| ac3 | Every existing solver test still passes unchanged. | `command` `pytest -q tests/solver` |

## Constraints

- on a tree where the behaviour is already correct, the change is tests only and touches no source file
- the default stays one worker
- the solve_event signature is unchanged
- the solves that diagnose an infeasible event may stay at one worker, because an infeasible core is only reliable with one; the result still records the request

## Non-goals

- no claim that a multi-worker solve is reproducible across worker counts

