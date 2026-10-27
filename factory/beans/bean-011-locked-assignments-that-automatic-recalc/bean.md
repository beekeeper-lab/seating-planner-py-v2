# bean-011 — Locked assignments that automatic recalculation cannot move

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 11 |
| Depends on | bean-010 |
| Size budget | 6 tasks · 5 files · 600 diff lines |

## Intent

A guest locked to a table stays at that table through every optimization mode, and only an explicit unlock releases them.

## Background

A lock is the organizer overriding the optimizer, and Product Principle 3 puts it above every automatic decision. Guardrail #5 is the design constraint: a lock is stored domain data, not a flag living in a screen, so it survives a restart and binds the solver rather than merely greying out a control. In the model a lock becomes a fixed variable — the guest's table is decided before the search begins. This touches the domain model, the store and the solver, all written by earlier beans.

## May write

- `src/seating_planner/domain/**`
- `src/seating_planner/solver/**`
- `src/seating_planner/store/**`
- `tests/solver/**`
- `tests/domain/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A guest locked to a table remains at that table after optimization. | `test` `tests/solver/test_locks.py::test_locked_guest_does_not_move` |
| ac2 | Locking every guest at a table holds all of them through optimization. | `test` `tests/solver/test_locks.py::test_table_level_lock_holds` |
| ac3 | Locks survive a save and load cycle. | `test` `tests/domain/test_locks.py::test_locks_persist` |
| ac4 | Unlocking a guest allows a later optimization to move them. | `test` `tests/solver/test_locks.py::test_unlock_allows_move` |
| ac5 | Locks that contradict a hard rule produce an infeasibility report naming both. | `test` `tests/solver/test_locks.py::test_lock_versus_hard_rule_conflict` |

## Constraints

- locks are persisted domain data, never interface state
- a lock is a fixed variable in the model, not a post-solve correction

## Non-goals

- no seat-level locks (seats are deferred; see PRD §18.3 assumption)

